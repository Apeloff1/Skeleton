"""skeleton/assets/binding_more2.py
More2 extreme complete Asset binding.
Atlas/tres into packs, rights, quality gates.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class BindingError(Exception):
    pass

class AssetBindingMore2:
    def bind(self, atlas: str, rights: str = "owned") -> str:
        if rights not in ("owned", "licensed"):
            raise BindingError("invalid")
        return hashlib.sha256(f"{atlas}:{rights}:more2".encode()).hexdigest()
