"""Compatibility facade for the canonical pure offline production dispatcher.

Import the one canonical implementation rather than defining a second class:
identity-sensitive callers and the offline CLI must share the same local API.
This facade does not grant network, provider or persistence authority.
"""
from __future__ import annotations

from .dispatcher import LocalAPI

__all__ = ["LocalAPI"]
