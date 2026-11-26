"""Local AI seam 138. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_138(data: dict) -> dict:
    return apply(138, data)
