"""Local AI seam 002. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_2(data: dict) -> dict:
    return apply(2, data)
