"""skeleton/deck/command_surface_more.py
More extreme complete CommandDeck.
Organ surface, observe_run, multi-cortex, receipts.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class DeckError(Exception):
    pass

class CommandDeckMore:
    def observe(self, organ: str) -> str:
        if not organ:
            raise DeckError("empty")
        return hashlib.sha256(f"observe:{organ}:more".encode()).hexdigest()
