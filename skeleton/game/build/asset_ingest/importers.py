"""Format sniffing and metadata extraction for textures, meshes and audio.

Pure-stdlib parsers that read headers only (plus a full OBJ/glTF parse, which
is cheap and needed to validate face indices). Every parser fails closed with
``AssetImportError`` so broken assets are reported rather than imported.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable

from skeleton.game.build.flgb_build_runtime import AssetImportReceipt, dig

IMPORTER_ID = "skeleton.asset_ingest"
IMPORTER_VERSION = "1"
MAX_ASSET_BYTES = 256 * 1024 * 1024
MAX_TEXTURE_SIDE = 16384

TEXTURE, MESH, AUDIO = "texture", "mesh", "audio"
_EXT = {".png": TEXTURE, ".jpg": TEXTURE, ".jpeg": TEXTURE, ".bmp": TEXTURE, ".tga": TEXTURE,
        ".obj": MESH, ".gltf": MESH, ".glb": MESH, ".wav": AUDIO, ".ogg": AUDIO}


class AssetImportError(ValueError):
    """Missing, unsupported, truncated or malformed asset."""


@dataclass(frozen=True)
class ImportedAsset:
    path: str
    kind: str
    format: str
    size: int
    sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def receipt(self) -> AssetImportReceipt:
        return AssetImportReceipt(
            asset_id=self.path, source_digest=self.sha256, importer_id=f"{IMPORTER_ID}.{self.format}",
            importer_version=IMPORTER_VERSION, output_digest=dig(self.metadata),
            provenance_digest=dig({"path": self.path, "sha256": self.sha256, "importer": IMPORTER_ID}))


def detect_kind(path: str) -> str:
    dot = path.rfind(".")
    kind = _EXT.get(path[dot:].lower()) if dot >= 0 else None
    if kind is None:
        raise AssetImportError(f"unsupported asset type: {path}")
    return kind


def _need(data: bytes, n: int, what: str) -> None:
    if len(data) < n:
        raise AssetImportError(f"truncated {what}")


def _texture_dims(w: int, h: int, what: str) -> None:
    if not (1 <= w <= MAX_TEXTURE_SIDE and 1 <= h <= MAX_TEXTURE_SIDE):
        raise AssetImportError(f"{what} has invalid dimensions {w}x{h}")


def _png(data: bytes) -> dict[str, Any]:
    _need(data, 33, "png")
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssetImportError("bad png signature")
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    _texture_dims(w, h, "png")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None or depth not in (1, 2, 4, 8, 16):
        raise AssetImportError("bad png color type or bit depth")
    if b"IEND" not in data[-12:]:
        raise AssetImportError("truncated png (no IEND)")
    return {"width": w, "height": h, "bit_depth": depth, "channels": channels,
            "has_alpha": ctype in (4, 6) or b"tRNS" in data, "power_of_two": _pot(w) and _pot(h)}


def _jpeg(data: bytes) -> dict[str, Any]:
    _need(data, 4, "jpeg")
    if data[:2] != b"\xff\xd8":
        raise AssetImportError("bad jpeg signature")
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            raise AssetImportError("corrupt jpeg marker stream")
        marker = data[i + 1]
        seg = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            _texture_dims(w, h, "jpeg")
            return {"width": w, "height": h, "channels": data[i + 9] if i + 9 < len(data) else 0,
                    "has_alpha": False, "power_of_two": _pot(w) and _pot(h)}
        i += 2 + seg
    raise AssetImportError("jpeg has no frame header")


def _bmp(data: bytes) -> dict[str, Any]:
    _need(data, 30, "bmp")
    if data[:2] != b"BM":
        raise AssetImportError("bad bmp signature")
    w, h = struct.unpack("<ii", data[18:26])
    bpp = struct.unpack("<H", data[28:30])[0]
    _texture_dims(w, abs(h), "bmp")
    return {"width": w, "height": abs(h), "bit_depth": bpp, "has_alpha": bpp == 32,
            "power_of_two": _pot(w) and _pot(abs(h))}


def _tga(data: bytes) -> dict[str, Any]:
    _need(data, 18, "tga")
    if data[2] not in (1, 2, 3, 9, 10, 11):
        raise AssetImportError("bad tga image type")
    w, h = struct.unpack("<HH", data[12:16])
    _texture_dims(w, h, "tga")
    return {"width": w, "height": h, "bit_depth": data[16], "has_alpha": data[16] == 32,
            "power_of_two": _pot(w) and _pot(h)}


def _pot(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def _bounds(points: list[tuple[float, float, float]]) -> dict[str, list[float]]:
    if not points:
        return {"min": [0.0] * 3, "max": [0.0] * 3}
    return {"min": [min(p[i] for p in points) for i in range(3)],
            "max": [max(p[i] for p in points) for i in range(3)]}


def _obj(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssetImportError("obj is not utf-8") from exc
    verts: list[tuple[float, float, float]] = []
    faces = tris = uvs = normals = 0
    groups, materials = set(), set()
    for n, line in enumerate(text.splitlines(), 1):
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        tag, args = parts[0], parts[1:]
        try:
            if tag == "v":
                verts.append((float(args[0]), float(args[1]), float(args[2])))
            elif tag == "vt":
                uvs += 1
            elif tag == "vn":
                normals += 1
            elif tag == "f":
                if len(args) < 3:
                    raise AssetImportError(f"obj line {n}: face needs 3+ vertices")
                for a in args:
                    idx = int(a.split("/")[0])
                    real = idx if idx > 0 else len(verts) + idx + 1
                    if not 1 <= real <= len(verts):
                        raise AssetImportError(f"obj line {n}: vertex index {idx} out of range")
                faces += 1
                tris += len(args) - 2
            elif tag in ("g", "o"):
                groups.update(args)
            elif tag == "usemtl":
                materials.update(args)
        except AssetImportError:
            raise
        except (IndexError, ValueError) as exc:
            raise AssetImportError(f"obj line {n}: malformed '{tag}'") from exc
    if not verts or not faces:
        raise AssetImportError("obj has no geometry")
    return {"vertices": len(verts), "faces": faces, "triangles": tris, "uvs": uvs, "normals": normals,
            "groups": sorted(groups), "materials": sorted(materials), "bounds": _bounds(verts),
            "external_refs": sorted({ln.split(None, 1)[1].strip() for ln in text.splitlines()
                                     if ln.startswith("mtllib ") and len(ln.split()) > 1})}


def _gltf_doc(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or not str(doc.get("asset", {}).get("version", "")).startswith("2"):
        raise AssetImportError("gltf missing asset.version 2.x")
    meshes = doc.get("meshes", [])
    accessors = doc.get("accessors", [])
    prims = 0
    for m in meshes:
        for p in m.get("primitives", []):
            prims += 1
            for ref in [*p.get("attributes", {}).values(), p.get("indices")]:
                if ref is not None and not (isinstance(ref, int) and 0 <= ref < len(accessors)):
                    raise AssetImportError(f"gltf accessor reference {ref!r} out of range")
    uris = sorted({b["uri"] for b in doc.get("buffers", []) + doc.get("images", [])
                   if isinstance(b, dict) and isinstance(b.get("uri"), str) and not b["uri"].startswith("data:")})
    return {"meshes": len(meshes), "primitives": prims, "materials": len(doc.get("materials", [])),
            "nodes": len(doc.get("nodes", [])), "animations": len(doc.get("animations", [])),
            "external_refs": uris}


def _gltf(data: bytes) -> dict[str, Any]:
    try:
        return _gltf_doc(json.loads(data))
    except (ValueError, AttributeError, TypeError) as exc:
        if isinstance(exc, AssetImportError):
            raise
        raise AssetImportError("gltf is not valid json") from exc


def _glb(data: bytes) -> dict[str, Any]:
    _need(data, 20, "glb")
    magic, version, length = struct.unpack("<4sII", data[:12])
    if magic != b"glTF" or version != 2:
        raise AssetImportError("bad glb header")
    if length != len(data):
        raise AssetImportError("glb length mismatch (truncated)")
    clen, ctype = struct.unpack("<I4s", data[12:20])
    if ctype != b"JSON" or 20 + clen > len(data):
        raise AssetImportError("glb missing JSON chunk")
    try:
        return _gltf_doc(json.loads(data[20:20 + clen]))
    except (ValueError, AttributeError, TypeError) as exc:
        if isinstance(exc, AssetImportError):
            raise
        raise AssetImportError("glb JSON chunk invalid") from exc


def _wav(data: bytes) -> dict[str, Any]:
    _need(data, 12, "wav")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AssetImportError("bad wav header")
    i, fmt, frames = 12, None, None
    while i + 8 <= len(data):
        cid, size = struct.unpack("<4sI", data[i:i + 8])
        body = data[i + 8:i + 8 + size]
        if cid == b"fmt ":
            _need(body, 16, "wav fmt chunk")
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            if len(body) < size:
                raise AssetImportError("truncated wav data chunk")
            frames = size
        i += 8 + size + (size & 1)
    if fmt is None or frames is None:
        raise AssetImportError("wav missing fmt or data chunk")
    codec, ch, rate, _, align, bits = fmt
    if ch < 1 or rate < 1 or align < 1:
        raise AssetImportError("wav has invalid format")
    count = frames // align
    return {"codec": "pcm" if codec == 1 else f"wav:{codec}", "channels": ch, "sample_rate": rate,
            "bits_per_sample": bits, "frames": count, "duration_s": round(count / rate, 6)}


def _ogg(data: bytes) -> dict[str, Any]:
    _need(data, 58, "ogg")
    if data[:4] != b"OggS":
        raise AssetImportError("bad ogg capture pattern")
    seg = data[26]
    pkt = data[27 + seg:]
    if pkt[:7] == b"\x01vorbis":
        ch, rate = pkt[11], struct.unpack("<I", pkt[12:16])[0]
        codec, pre = "vorbis", 0
    elif pkt[:8] == b"OpusHead":
        ch, pre = pkt[9], struct.unpack("<H", pkt[10:12])[0]
        codec, rate = "opus", 48000
    else:
        raise AssetImportError("ogg stream is neither vorbis nor opus")
    last = data.rfind(b"OggS")
    if ch < 1 or rate < 1 or last + 14 > len(data):
        raise AssetImportError("ogg has invalid stream header")
    granule = struct.unpack("<q", data[last + 6:last + 14])[0]
    samples = max(0, granule - pre)
    return {"codec": codec, "channels": ch, "sample_rate": rate, "duration_s": round(samples / rate, 6)}


_PARSERS: dict[str, Callable[[bytes], dict[str, Any]]] = {
    ".png": _png, ".jpg": _jpeg, ".jpeg": _jpeg, ".bmp": _bmp, ".tga": _tga,
    ".obj": _obj, ".gltf": _gltf, ".glb": _glb, ".wav": _wav, ".ogg": _ogg}


def import_bytes(path: str, data: bytes) -> ImportedAsset:
    """Validate ``data`` as the asset named ``path`` and extract its metadata."""
    kind = detect_kind(path)
    if not isinstance(data, bytes | bytearray):
        raise AssetImportError("asset data must be bytes")
    if not data:
        raise AssetImportError("empty asset")
    if len(data) > MAX_ASSET_BYTES:
        raise AssetImportError("asset exceeds size limit")
    ext = path[path.rfind("."):].lower()
    meta = _PARSERS[ext](bytes(data))
    return ImportedAsset(path=path, kind=kind, format=ext[1:].replace("jpeg", "jpg"), size=len(data),
                         sha256=sha256(data).hexdigest(), metadata=meta)
