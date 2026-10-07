"""Skeleton Memory — Dream module alias (canonical home).

DreamEngine lives in skeleton.intelligence.dream; this alias keeps
`skeleton.memory.dream` importable for tooling that looks there.
"""

from __future__ import annotations

from skeleton.intelligence.dream import DreamEngine

__all__ = ["DreamEngine"]
