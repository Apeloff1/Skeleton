"""Local AI seam 080. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_80(data: dict) -> dict:
    return apply(80, data)
