"""Local AI seam 008. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_8(data: dict) -> dict:
    return apply(8, data)
