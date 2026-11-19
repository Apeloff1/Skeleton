"""Local AI seam 018. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_18(data: dict) -> dict:
    return apply(18, data)
