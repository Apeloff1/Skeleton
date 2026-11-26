"""Local AI seam 100. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_100(data: dict) -> dict:
    return apply(100, data)
