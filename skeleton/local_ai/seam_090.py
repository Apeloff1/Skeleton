"""Local AI seam 090. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_90(data: dict) -> dict:
    return apply(90, data)
