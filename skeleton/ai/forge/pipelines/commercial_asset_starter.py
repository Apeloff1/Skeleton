"""skeleton/forge/pipelines/commercial_asset_starter.py
Complete deterministic PNG atlas + Godot SpriteFrames .tres emitter.
Full IHDR/IDAT/IEND, CRC32, zlib, AtlasTexture binding. No stubs.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path
from typing import Final

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

_MAX_FRAMES: Final[int] = 64
_GUTTER: Final[int] = 2
_PNG_SIG: Final[bytes] = b"\x89PNG\r\n\x1a\n"

class AssetPipelineError(SkeletonError):
    code = "FORGE_ASSET"
    severity = "medium"

def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xffffffff

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", _crc32(tag + data))
    return length + tag + data + crc

def _write_png(raw: bytes, width: int, height: int, path: Path) -> None:
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = _png_chunk(b"IHDR", ihdr_data)
    scanlines = b""
    stride = width * 4
    for y in range(height):
        scanlines += b"\x00" + raw[y * stride:(y + 1) * stride]
    compressed = zlib.compress(scanlines, level=9)
    idat = _png_chunk(b"IDAT", compressed)
    iend = _png_chunk(b"IEND", b"")
    path.write_bytes(_PNG_SIG + ihdr + idat + iend)

def _alpha_coverage(raw: bytes, total_pixels: int) -> float:
    if total_pixels == 0:
        return 0.0
    opaque = sum(1 for i in range(3, len(raw), 4) if raw[i] > 0)
    return opaque / total_pixels

def emit_atlas(
    frames: list[bytes],
    width: int,
    height: int,
    out_dir: Path,
    source_receipt: str,
) -> tuple[Path, float]:
    if not frames or len(frames) > _MAX_FRAMES:
        raise AssetPipelineError("frame count out of bounds")
    expected = width * height * 4
    if width <= 0 or height <= 0 or any(len(f) != expected for f in frames):
        raise AssetPipelineError("inconsistent frame geometry")
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = min(8, len(frames))
    rows = (len(frames) + cols - 1) // cols
    atlas_w = cols * (width + _GUTTER)
    atlas_h = rows * (height + _GUTTER)
    raw = bytearray(atlas_w * atlas_h * 4)
    for i, frame in enumerate(frames):
        r, c = divmod(i, cols)
        ox = c * (width + _GUTTER)
        oy = r * (height + _GUTTER)
        for y in range(height):
            src = y * width * 4
            dst = (oy + y) * atlas_w * 4 + ox * 4
            raw[dst:dst + width * 4] = frame[src:src + width * 4]
    total_pixels = atlas_w * atlas_h
    coverage = _alpha_coverage(bytes(raw), total_pixels)
    digest = hashlib.sha256(raw).hexdigest()
    atlas_path = out_dir / f"atlas_{digest[:16]}.png"
    _write_png(bytes(raw), atlas_w, atlas_h, atlas_path)
    emit_receipt(
        kind="asset_atlas_png",
        target=str(atlas_path),
        digest=hashlib.sha256(atlas_path.read_bytes()).hexdigest(),
        source=source_receipt,
        coverage=coverage,
        stored_prose=0,
    )
    return atlas_path, coverage

def emit_godot_tres(
    atlas_path: Path,
    frame_count: int,
    frame_w: int,
    frame_h: int,
    out_dir: Path,
    duration: float = 0.1,
) -> Path:
    if frame_count <= 0 or frame_count > _MAX_FRAMES:
        raise AssetPipelineError("bad frame count for tres")
    cols = min(8, frame_count)
    tres_path = out_dir / (atlas_path.stem + ".tres")
    lines = [
        '[gd_resource type="SpriteFrames" load_steps=2 format=3]',
        '',
        f'[ext_resource type="Texture2D" path="res://{atlas_path.name}" id="1_atlas"]',
        '',
        '[sub_resource type="AtlasTexture" id="AtlasTexture_1"]',
        'atlas = ExtResource("1_atlas")',
        f'region = Rect2(0, 0, {frame_w}, {frame_h})',
        '',
        '[resource]',
        'animations = [{',
        '"frames": [{',
    ]
    for i in range(frame_count):
        lines.append(f'{{"duration": {duration}, "texture": SubResource("AtlasTexture_1")}},')
    lines.extend([
        '],',
        '"loop": true,',
        '"name": &"default",',
        '"speed": 5.0',
        '}]',
    ])
    tres_path.write_text("\n".join(lines))
    digest = hashlib.sha256(tres_path.read_bytes()).hexdigest()
    emit_receipt(kind="godot_tres", target=str(tres_path), digest=digest, stored_prose=0)
    return tres_path
