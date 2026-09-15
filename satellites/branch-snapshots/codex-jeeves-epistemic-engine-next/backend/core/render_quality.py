"""
🖼️ RENDER QUALITY — global photoreal + extreme-pixel-count policy (2026-06).

Single source of truth so EVERY render in the app (Worldforge maps/posters, playable
covers, asset-genesis art) is photorealistic and hard-floored to an extreme pixel count.

- AI image gen (Nano-Banana / GPT-Image): append PHOTOREAL_SUFFIX to the prompt, then
  LANCZOS-upscale the returned image to EXTREME_PX on the long edge.
- Procedural PIL/numpy renders: pass their final PNG bytes through upscale_png_bytes.

EXTREME_PX is capped at 4096 — true 8K base64 (~30-60 MB) overflows the ingress payload,
so 4096 is the safe "extreme" ceiling while still being a 4K master.
"""
from __future__ import annotations

import base64
import io

# Hard floor for the long edge of every render in the product.
EXTREME_PX = 4096

# Appended to every AI image prompt to force maximum photoreal fidelity + detail.
PHOTOREAL_SUFFIX = (
    " Ultra-photorealistic, extreme detail, 4K/8K ultra-high-resolution master, razor-sharp "
    "focus, physically-based lighting, natural global illumination, crisp micro-detail and "
    "fine texture, high dynamic range, cinematic color grading, no blur, no noise, no "
    "compression artifacts, professional photography quality."
)


def upscale_png_bytes(png: bytes, target: int = EXTREME_PX) -> bytes:
    """LANCZOS-upscale (never downscale) a PNG's long edge to `target` px. Returns PNG bytes.
    Best-effort: returns the original bytes unchanged on any failure."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("RGB")
        long_edge = max(im.size)
        if long_edge >= target:
            return png
        scale = target / long_edge
        new = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
        im = im.resize(new, Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return png


def upscale_b64(b64: str, target: int = EXTREME_PX) -> str:
    """Upscale a base64 PNG (no data: prefix) to `target` px long-edge. Returns base64
    (no prefix). Best-effort: returns the input unchanged on failure."""
    if not b64:
        return b64
    try:
        raw = base64.b64decode(b64)
        out = upscale_png_bytes(raw, target)
        return base64.b64encode(out).decode("ascii")
    except Exception:
        return b64
