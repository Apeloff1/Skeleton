"""Local AI seam 175. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_175(data: dict) -> dict:
    return apply(175, data)
