"""Per-platform export preset and artifact validators."""
from __future__ import annotations

from .base import PlatformSpec
from .registry import REGISTRY, get, known

__all__ = ["PlatformSpec", "REGISTRY", "get", "known"]
