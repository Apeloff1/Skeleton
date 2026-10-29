"""Install manifest.
Lists required surfaces for first install and verifies presence.
"""
from typing import Any, Dict, List

class InstallManifest:
    REQUIRED = ["local_ai", "godot", "peak_seal", "consumer_cli", "asset_quality"]

    def verify(self, present: List[str]) -> Dict[str, Any]:
        if not isinstance(present, list):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.install.manifest.v1"}
        missing = [r for r in self.REQUIRED if r not in present]
        ok = len(missing) == 0
        return {
            "ok": ok,
            "required": self.REQUIRED,
            "missing": missing,
            "reason": "ok" if ok else "missing_surfaces",
            "schema": "skeleton.install.manifest.v1",
        }
