"""Local AI seam 028. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_28(data: dict) -> dict:
    return apply(28, data)
