"""Local AI seam 127. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_127(data: dict) -> dict:
    return apply(127, data)
