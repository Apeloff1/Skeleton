"""Local AI seam 026. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_26(data: dict) -> dict:
    return apply(26, data)
