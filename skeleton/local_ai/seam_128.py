"""Local AI seam 128. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_128(data: dict) -> dict:
    return apply(128, data)
