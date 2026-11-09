"""Errors raised by the procedural generators."""
from __future__ import annotations


class ProcgenError(ValueError):
    """A generator was asked for something it cannot produce deterministically."""
