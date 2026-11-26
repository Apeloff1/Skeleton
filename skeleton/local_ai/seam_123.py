"""Local AI seam 123. The payload gate is seam_runtime."""
from __future__ import annotations

from .seam_runtime import apply


def process_123(data: dict) -> dict:
    return apply(123, data)
