"""Format sniffing and metadata extraction for textures, meshes and audio.

Pure-stdlib parsers that read headers only (plus a full OBJ/glTF parse, which
is cheap and needed to validate face indices). Every parser fails closed with
``AssetImportError`` so broken assets are reported rather than imported.
"""
from __future__ import annotations

import json
import math
import struct
import zlib
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
    """Inspect PNG chunks with bounded framing, CRC and critical-order checks.

    Metadata extraction does not claim full pixel decompression; a renderer
    must still decode IDAT under its own bounded image policy.
    """
    _need(data, 33, "png")
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssetImportError("bad png signature")
    offset = 8
    chunks = 0
    seen_idat = seen_iend = seen_plte = seen_trns = False
    idat_closed = False
    has_alpha = False
    w = h = depth = ctype = 0
    view = memoryview(data)
    while offset < len(data):
        chunks += 1
        if chunks > 8192 or len(data) - offset < 12:
            raise AssetImportError("truncated or excessive png chunks")
        length = struct.unpack_from(">I", data, offset)[0]
        if length > len(data) - offset - 12:
            raise AssetImportError("truncated png chunk payload")
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if any(not (65 <= byte <= 90 or 97 <= byte <= 122) for byte in kind):
            raise AssetImportError("invalid png chunk type")
        expected_crc = struct.unpack_from(">I", data, end - 4)[0]
        actual_crc = zlib.crc32(view[offset + 4:end - 4]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise AssetImportError("png chunk CRC mismatch")
        payload = view[offset + 8:end - 4]
        if chunks == 1:
            if kind != b"IHDR" or length != 13:
                raise AssetImportError("png must begin with 13-byte IHDR")
            w, h, depth, ctype, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            _texture_dims(w, h, "png")
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8),
                      4: (8, 16), 6: (8, 16)}
            if depth not in depths.get(ctype, ()) or compression != 0 or filtering != 0 or interlace not in (0, 1):
                raise AssetImportError("bad png color type or bit depth")
        elif kind == b"IHDR":
            raise AssetImportError("duplicate png IHDR")
        elif kind == b"PLTE":
            if seen_plte or seen_idat or length == 0 or length > 768 or length % 3:
                raise AssetImportError("invalid png palette")
            seen_plte = True
        elif kind == b"tRNS":
            if seen_trns or seen_idat or ctype not in (0, 2, 3):
                raise AssetImportError("invalid png transparency chunk")
            seen_trns = True
            has_alpha = True
        elif kind == b"IDAT":
            if idat_closed or (ctype == 3 and not seen_plte):
                raise AssetImportError("invalid png IDAT order")
            seen_idat = True
        elif kind == b"IEND":
            if length or not seen_idat or end != len(data):
                raise AssetImportError("invalid png IEND or trailing data")
            seen_iend = True
            break
        elif 65 <= kind[0] <= 90:
            raise AssetImportError("unsupported critical png chunk")
        if seen_idat and kind != b"IDAT":
            idat_closed = True
        offset = end
    if not seen_iend:
        raise AssetImportError("truncated png (no IEND)")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    return {"width": w, "height": h, "bit_depth": depth, "channels": channels,
            "has_alpha": ctype in (4, 6) or has_alpha, "power_of_two": _pot(w) and _pot(h)}


def _jpeg(data: bytes) -> dict[str, Any]:
    """Read a framed SOF marker, never scan through a malformed segment."""
    _need(data, 4, "jpeg")
    if data[:2] != b"\xff\xd8":
        raise AssetImportError("bad jpeg signature")
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise AssetImportError("corrupt jpeg marker stream")
        # JPEG permits fill FF bytes between markers, but not arbitrary
        # stuffed data before the first start-of-frame segment.
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            raise AssetImportError("truncated jpeg marker")
        marker = data[i]
        i += 1
        if marker in (0x00, 0x01, 0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            raise AssetImportError("unexpected jpeg marker before frame")
        if i + 2 > len(data):
            raise AssetImportError("truncated jpeg segment")
        seg = struct.unpack_from(">H", data, i)[0]
        if seg < 2 or i + seg > len(data):
            raise AssetImportError("invalid jpeg segment length")
        if marker in (0xC0, 0xC1, 0xC2):
            if seg < 8:
                raise AssetImportError("truncated jpeg frame header")
            precision = data[i + 2]
            h, w = struct.unpack_from(">HH", data, i + 3)
            channels = data[i + 7]
            if precision not in (8, 12) or not 1 <= channels <= 4 or seg != 8 + 3 * channels:
                raise AssetImportError("invalid jpeg frame layout")
            _texture_dims(w, h, "jpeg")
            return {"width": w, "height": h, "channels": channels,
                    "has_alpha": False, "power_of_two": _pot(w) and _pot(h)}
        if marker == 0xDA:
            raise AssetImportError("jpeg scan precedes frame header")
        i += seg
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
    if (type(doc) is not dict or type(doc.get("asset")) is not dict
            or doc["asset"].get("version") != "2.0"):
        raise AssetImportError("gltf missing asset.version 2.x")
    meshes = doc.get("meshes", [])
    accessors = doc.get("accessors", [])
    prims = 0
    for m in meshes:
        for p in m.get("primitives", []):
            prims += 1
            for ref in [*p.get("attributes", {}).values(), p.get("indices")]:
                if ref is not None and not (type(ref) is int and 0 <= ref < len(accessors)):
                    raise AssetImportError(f"gltf accessor reference {ref!r} out of range")
    uris = sorted({b["uri"] for b in doc.get("buffers", []) + doc.get("images", [])
                   if isinstance(b, dict) and isinstance(b.get("uri"), str) and not b["uri"].startswith("data:")})
    return {"meshes": len(meshes), "primitives": prims, "materials": len(doc.get("materials", [])),
            "nodes": len(doc.get("nodes", [])), "animations": len(doc.get("animations", [])),
            "external_refs": uris}


def _gltf_unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous nested JSON keys rather than last-wins data."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AssetImportError("gltf duplicate JSON key")
        result[key] = value
    return result


def _gltf_reject_constant(token: str) -> Any:
    raise AssetImportError(f"gltf nonfinite JSON number: {token}")


def _gltf_parse_float(token: str) -> float:
    """Reject unrepresentable JSON numbers before metadata is trusted."""
    if len(token) > 128:
        raise AssetImportError("gltf floating-point token exceeds bound")
    value = float(token)
    if not math.isfinite(value):
        raise AssetImportError("gltf nonfinite JSON number")
    return value


def _gltf_parse_int(token: str) -> int:
    """Cap JSON integer digits independently of Python's process defaults."""
    if len(token) > 128:
        raise AssetImportError("gltf integer token exceeds bound")
    return int(token)


def _gltf_json(raw: bytes) -> dict[str, Any]:
    """Decode bounded, unambiguous JSON before interpreting glTF references."""
    try:
        doc = json.loads(raw, object_pairs_hook=_gltf_unique_object,
                         parse_constant=_gltf_reject_constant,
                         parse_float=_gltf_parse_float, parse_int=_gltf_parse_int)
    except AssetImportError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise AssetImportError("gltf is not strict JSON") from exc

    pending = [(doc, 0)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        if depth > 64 or visited > 131072:
            raise AssetImportError("gltf JSON structure exceeds bound")
        if type(value) is dict or type(value) is list:
            children = value.values() if type(value) is dict else value
            if len(value) + len(pending) + visited > 131072:
                raise AssetImportError("gltf JSON node count exceeds bound")
            pending.extend((child, depth + 1) for child in children)
    try:
        return _gltf_doc(doc)
    except AssetImportError:
        raise
    except (ValueError, AttributeError, TypeError, RecursionError) as exc:
        raise AssetImportError("gltf has invalid structure") from exc


def _gltf(data: bytes) -> dict[str, Any]:
    return _gltf_json(data)


def _glb(data: bytes) -> dict[str, Any]:
    """Validate every GLB chunk boundary, not only the first JSON chunk."""
    _need(data, 20, "glb")
    magic, version, length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2:
        raise AssetImportError("bad glb header")
    if length != len(data) or length % 4:
        raise AssetImportError("glb length mismatch or misalignment")
    offset = 12
    json_chunk: bytes | None = None
    bin_seen = False
    while offset < length:
        if length - offset < 8:
            raise AssetImportError("truncated glb chunk header")
        chunk_size, chunk_type = struct.unpack_from("<I4s", data, offset)
        if chunk_size % 4 or chunk_size > length - offset - 8:
            raise AssetImportError("invalid glb chunk length or alignment")
        payload_start = offset + 8
        if json_chunk is None:
            if chunk_type != b"JSON":
                raise AssetImportError("glb must begin with JSON chunk")
            json_chunk = data[payload_start:payload_start + chunk_size]
        elif chunk_type == b"BIN\x00" and not bin_seen:
            bin_seen = True
        else:
            raise AssetImportError("duplicate or unsupported glb chunk")
        offset = payload_start + chunk_size
    if json_chunk is None:
        raise AssetImportError("glb missing JSON chunk")
    return _gltf_json(json_chunk)

def _wav(data: bytes) -> dict[str, Any]:
    """Validate the entire RIFF/WAVE envelope before accepting metadata.

    A forged length, truncated ancillary chunk, or duplicate fmt/data chunk
    cannot hide trailing bytes or change which sample payload a renderer uses.
    """
    _need(data, 12, "wav")
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AssetImportError("bad wav header")
    if struct.unpack_from("<I", data, 4)[0] != len(data) - 8:
        raise AssetImportError("wav RIFF length mismatch")
    i, fmt, frames, chunks = 12, None, None, 0
    while i < len(data):
        chunks += 1
        if chunks > 8192:
            raise AssetImportError("wav chunk count exceeds bound")
        if len(data) - i < 8:
            raise AssetImportError("truncated wav chunk header")
        cid, size = struct.unpack_from("<4sI", data, i)
        start = i + 8
        end = start + size
        next_i = end + (size & 1)
        if next_i > len(data):
            raise AssetImportError("truncated wav chunk")
        if cid == b"fmt ":
            if fmt is not None:
                raise AssetImportError("duplicate wav fmt chunk")
            if size < 16:
                raise AssetImportError("truncated wav fmt chunk")
            fmt = struct.unpack_from("<HHIIHH", data, start)
        elif cid == b"data":
            if frames is not None:
                raise AssetImportError("duplicate wav data chunk")
            frames = size
        i = next_i
    if fmt is None or frames is None:
        raise AssetImportError("wav missing fmt or data chunk")
    codec, ch, rate, byte_rate, align, bits = fmt
    if ch < 1 or rate < 1 or byte_rate < 1 or align < 1:
        raise AssetImportError("wav has invalid format")
    if frames % align:
        raise AssetImportError("wav data is not block aligned")
    if codec == 1 and (
        bits not in (8, 16, 24, 32)
        or align != ch * (bits // 8)
        or byte_rate != rate * align
    ):
        raise AssetImportError("wav PCM layout mismatch")
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
    # Bind validation, size and receipt digest to one immutable byte snapshot.
    # Caller-owned bytearrays may otherwise change between parser and hash.
    payload = bytes(data)
    if not payload:
        raise AssetImportError("empty asset")
    if len(payload) > MAX_ASSET_BYTES:
        raise AssetImportError("asset exceeds size limit")
    ext = path[path.rfind("."):].lower()
    meta = _PARSERS[ext](payload)
    return ImportedAsset(path=path, kind=kind, format=ext[1:].replace("jpeg", "jpg"), size=len(payload),
                         sha256=sha256(payload).hexdigest(), metadata=meta)
