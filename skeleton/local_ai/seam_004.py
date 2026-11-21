"""Local AI seam 004. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_4(data: dict) -> dict:
    return apply(4, data)
