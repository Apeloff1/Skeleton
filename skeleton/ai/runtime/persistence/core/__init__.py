"""Persist 1.0 facade (GB-27). One core. Two gates."""

from __future__ import annotations

from skeleton.persist.capabilities import capabilities
from skeleton.persist.cards import persist_card
from skeleton.persist.engine import PersistEngine
from skeleton.persist.law import OWN_ENV, PACKET, VERSION
from skeleton.persist.store import Persist

__all__ = [
    "OWN_ENV",
    "PACKET",
    "VERSION",
    "Persist",
    "PersistEngine",
    "capabilities",
    "persist_card",
]
