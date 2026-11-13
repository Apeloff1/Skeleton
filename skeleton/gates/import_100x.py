"""skeleton/gates/import_100x.py
100x extreme complete import gate & boundary.
Stored_prose=0, secret scan, occupied-PR review.
Fail-closed.
"""
from __future__ import annotations

class GateError(Exception):
    pass

class ImportGate100x:
    def check(self, stored_prose: int = 0) -> bool:
        if stored_prose != 0:
            raise GateError("fail-closed")
        return True
