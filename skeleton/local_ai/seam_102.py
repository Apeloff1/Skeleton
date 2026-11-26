"""Local AI seam 102. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_102(data: dict) -> dict:
    return apply(102, data)
