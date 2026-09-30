"""Persist 1.0 facade (GB-27). One core. Two gates."""

from __future__ import annotations

from skeleton.persistence.core.capabilities import capabilities
from skeleton.persistence.core.cards import persist_card
from skeleton.persistence.core.engine import PersistEngine
from skeleton.persistence.core.law import OWN_ENV, PACKET, VERSION
from skeleton.persistence.core.store import Persist

__all__ = [
    "OWN_ENV",
    "PACKET",
    "VERSION",
    "Persist",
    "PersistEngine",
    "capabilities",
    "persist_card",
]
