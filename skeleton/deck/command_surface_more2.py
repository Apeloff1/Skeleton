"""skeleton/deck/command_surface_more2.py
More2 extreme complete CommandDeck.
Organ surface, observe_run, multi-cortex, receipts.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class DeckError(Exception):
    pass

class CommandDeckMore2:
    def observe(self, organ: str) -> str:
        if not organ:
            raise DeckError("empty")
        return hashlib.sha256(f"observe:{organ}:more2".encode()).hexdigest()
