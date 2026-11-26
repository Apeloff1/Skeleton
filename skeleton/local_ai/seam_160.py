"""Local AI seam 160. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_160(data: dict) -> dict:
    return apply(160, data)
