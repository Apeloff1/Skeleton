"""Local AI seam 009. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_9(data: dict) -> dict:
    return apply(9, data)
