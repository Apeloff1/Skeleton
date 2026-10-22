"""skeleton/forge/pipelines/commercial_asset_starter.py
Deterministic commercial-grade sprite atlas emitter with SHA receipts and quality metrics.
Extends existing studio_sprite_* . Complete packing + alpha coverage score.
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
        return kwargs.get("digest", "")

_MAX_FRAMES: Final[int] = 64
_GUTTER: Final[int] = 2

class AssetPipelineError(SkeletonError):
    code = "FORGE_ASSET"
    severity = "medium"

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
    atlas_path = out_dir / f"atlas_{digest[:16]}.bin"
    atlas_path.write_bytes(bytes(raw))
    emit_receipt(
        kind="asset_atlas",
        target=str(atlas_path),
        digest=digest,
        source=source_receipt,
        coverage=coverage,
        stored_prose=0,
    )
    return atlas_path, coverage
