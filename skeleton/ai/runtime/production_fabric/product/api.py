"""Compatibility export of the canonical, local-only production dispatcher.

No additional command authority, model, provider, or network adapter is created.
"""
from __future__ import annotations

from .dispatcher import LocalAPI

__all__ = ["LocalAPI"]
