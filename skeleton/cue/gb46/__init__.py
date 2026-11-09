"""GB-46 cue completion. 2560 organs. law.py not forked. Lazy index."""

from __future__ import annotations

from skeleton.cue.gb46.law import CAPABILITY_COUNT, PACKET, VERSION
from skeleton.cue.gb46.registry import capabilities, index

__all__ = ["CAPABILITY_COUNT", "PACKET", "VERSION", "capabilities", "index"]
