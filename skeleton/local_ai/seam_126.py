"""Local AI seam 126. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_126(data: dict) -> dict:
    return apply(126, data)
