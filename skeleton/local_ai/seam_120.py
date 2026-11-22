"""Local AI seam 120. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_120(data: dict) -> dict:
    return apply(120, data)
