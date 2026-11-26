"""Local AI seam 025. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_25(data: dict) -> dict:
    return apply(25, data)
