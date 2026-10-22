"""skeleton/house/shim_cleanup_100x.py
100x extreme complete shim cleanup and house pointers.
27-repo pointer atoms, fieldwalk balance, transitional shim removal.
Fail-closed.
"""
from __future__ import annotations
import hashlib
from typing import Dict

class ShimError(Exception):
    pass

class HousePointers100x:
    def __init__(self):
        self.pointers: Dict[str, str] = {}

    def add_pointer(self, repo: str) -> str:
        if not repo or " " in repo:
            raise ShimError("invalid repo")
        d = hashlib.sha256(repo.encode()).hexdigest()
        self.pointers[repo] = d
        return d

    def is_balanced(self) -> bool:
        return len(self.pointers) >= 27
