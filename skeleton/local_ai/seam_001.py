"""Local AI seam 001. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_1(data: dict) -> dict:
    return apply(1, data)
