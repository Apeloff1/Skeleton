"""Parse-pointer facade (GB-42)."""

from __future__ import annotations

from skeleton.parse.capabilities import capabilities
from skeleton.parse.law import N_CAP, PACKET, VERSION
from skeleton.parse.split import split

__all__ = ["N_CAP", "PACKET", "VERSION", "capabilities", "split"]
