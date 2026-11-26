"""Local AI seam 170. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_170(data: dict) -> dict:
    return apply(170, data)
