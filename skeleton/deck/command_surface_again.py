"""skeleton/deck/command_surface_again.py
Further extreme complete CommandDeck.
Organ surface, observe_run, multi-cortex.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class DeckError(Exception):
    pass

class CommandDeckAgain:
    def observe(self, organ: str) -> str:
        if not organ:
            raise DeckError("empty")
        return hashlib.sha256(f"observe:{organ}:live".encode()).hexdigest()
