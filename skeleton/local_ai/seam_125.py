"""Local AI seam 125. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_125(data: dict) -> dict:
    return apply(125, data)
