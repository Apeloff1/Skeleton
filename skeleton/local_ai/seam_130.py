"""Local AI seam 130. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_130(data: dict) -> dict:
    return apply(130, data)
