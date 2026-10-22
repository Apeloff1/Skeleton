"""skeleton/install/offline_10000x.py
10000x extreme complete offline / air-gapped path.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class OfflineError(Exception):
    pass

class OfflineInstall10000x:
    def prepare(self, bundle: str) -> str:
        return hashlib.sha256(f"offline10000:{bundle}".encode()).hexdigest()
