"""Local AI seam 020. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_20(data: dict) -> dict:
    return apply(20, data)
