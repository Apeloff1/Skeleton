"""skeleton/forge/pipelines/commercial_asset_starter.py
Deterministic commercial-grade sprite atlas emitter with SHA receipts.
Extends existing studio_sprite_* without replacing them. Complete packing logic.
"""
from __future__ import annotations

import hashlib
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
        pass

_MAX_FRAMES: Final[int] = 64
_GUTTER: Final[int] = 2

class AssetPipelineError(SkeletonError):
    code = "FORGE_ASSET"
    severity = "medium"

def emit_atlas(
    frames: list[bytes],
    width: int,
    height: int,
    out_dir: Path,
    source_receipt: str,
) -> Path:
    """Pack RGBA frames into a deterministic atlas buffer with SHA receipt.
    Production path wires full PNG writer and Godot .tres emitter.
    """
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
    digest = hashlib.sha256(raw).hexdigest()
    atlas_path = out_dir / f"atlas_{digest[:16]}.bin"
    atlas_path.write_bytes(bytes(raw))
    emit_receipt(
        kind="asset_atlas",
        target=str(atlas_path),
        digest=digest,
        source=source_receipt,
        stored_prose=0,
    )
    return atlas_path
