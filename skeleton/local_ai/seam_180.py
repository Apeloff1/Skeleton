"""Local AI seam 180. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_180(data: dict) -> dict:
    return apply(180, data)
