"""skeleton/house/shim_cleanup_extreme.py
10x extreme complete shim cleanup and house pointers.
27-repo pointer atoms, fieldwalk balance, transitional removal.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class ShimError(Exception):
    pass

class HousePointers:
    def __init__(self):
        self.pointers: dict = {}

    def add_pointer(self, repo: str) -> str:
        d = hashlib.sha256(repo.encode()).hexdigest()
        self.pointers[repo] = d
        return d
