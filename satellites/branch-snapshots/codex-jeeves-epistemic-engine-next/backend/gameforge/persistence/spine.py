from __future__ import annotations
"""
Conglomerate persistence spine — unified paths, encryption flags, twin hooks.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional


class PersistenceSpine:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.root = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.encrypt = os.getenv("GAMEFORGE_ENCRYPT", "1") == "1"
        self.air_gap = os.getenv("GAMEFORGE_AIR_GAP", "1") == "1"

    def user_dir(self) -> Path:
        p = self.root / "users" / self.user_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def surface_path(self, surface: str) -> Path:
        p = self.user_dir() / surface
        p.mkdir(parents=True, exist_ok=True)
        return p

    def status(self) -> Dict[str, Any]:
        return {
            "root": str(self.root),
            "user_dir": str(self.user_dir()),
            "encrypt": self.encrypt,
            "air_gap": self.air_gap,
            "policy": "local_first_conglomerate",
        }
