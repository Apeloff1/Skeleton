"""Version migrator.
Upgrades saved state schemas across pipeline versions.
"""
from __future__ import annotations
from typing import Any, Dict

class VersionMigrator:
    def migrate(self, state: Dict[str, Any], from_version: str = "v1") -> Dict[str, Any]:
        out = dict(state)
        if from_version == "v1":
            out.setdefault("optical", 0.9)
            out.setdefault("schema", "skeleton.state.v2")
        if "schema" not in out:
            out["schema"] = "skeleton.state.v2"
        return out
    def current_schema(self) -> str:
        return "skeleton.state.v2"
