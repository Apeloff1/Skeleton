"""Local AI seam 005. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_5(data: dict) -> dict:
    return apply(5, data)
