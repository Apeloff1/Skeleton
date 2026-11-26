"""Local AI seam 096. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_96(data: dict) -> dict:
    return apply(96, data)
