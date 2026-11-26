"""Local AI seam 012. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_12(data: dict) -> dict:
    return apply(12, data)
