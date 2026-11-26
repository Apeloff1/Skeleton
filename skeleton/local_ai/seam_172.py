"""Local AI seam 172. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_172(data: dict) -> dict:
    return apply(172, data)
