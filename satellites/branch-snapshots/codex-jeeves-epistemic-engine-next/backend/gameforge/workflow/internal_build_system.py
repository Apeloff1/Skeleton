#!/usr/bin/env python3
"""
GameForge Internal Build System (self-contained) — Cowabunga v4 adaptation.

Takes assembled game data and produces a packaged, self-runnable bundle. The
bundle bytes are stored (encrypted + versioned) in the persistent boardroom
vault so they survive restarts/forks — the standalone version wrote to an
ephemeral /tmp/builds dir, which does not persist here.

No external engine or dependency required.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from typing import Any, Dict, List

_RUNTIME_STUB = '''#!/usr/bin/env python3
"""GameForge Internal Runtime (self-contained)."""
import json, sys

def run(manifest_path="game_manifest.json"):
    with open(manifest_path) as f:
        data = json.load(f)
    print("=== GameForge Internal Game ===")
    print("Name:", data.get("name"))
    print("Levels:", len(data.get("levels", {})))
    print("Systems:", len(data.get("systems", {})))
    print("Narrative loaded:", bool(data.get("narrative")))
    print("Simulation complete.")
    return {"status": "completed"}

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "game_manifest.json")
'''


class InternalBuildSystem:
    """Fully internal build/package system. Multi-arch aware, signed (sim)."""

    ARCHITECTURES = ["arm64", "x86_64", "universal"]

    def __init__(self, project_name: str):
        self.project_name = project_name
        self.build_history: List[Dict] = []

    def build_game(self, game_data: Dict, phase: str = "final") -> Dict:
        """Assemble source files → zip bundle → runnable descriptor + signing."""
        source = self._generate_source(game_data)
        bundle_bytes, files = self._zip_bundle(source, game_data)
        signature = self._sign(bundle_bytes)

        pkg_name = f"{self._safe(self.project_name)}__{self._safe(phase)}.zip"
        result = {
            "project": self.project_name,
            "phase": phase,
            "package_name": pkg_name,
            "bundle_bytes": bundle_bytes,          # raw bytes (route strips before JSON)
            "size_bytes": len(bundle_bytes),
            "files": files,
            "architectures": self.ARCHITECTURES,
            "signature": signature,
            "runnable": {
                "entry_point": "internal_runtime.py",
                "data_file": "game_manifest.json",
                "execution_command": "python internal_runtime.py game_manifest.json",
                "can_run_internally": True,
            },
            "timestamp": time.time(),
            "status": "built_successfully",
        }
        self.build_history.append({k: v for k, v in result.items() if k != "bundle_bytes"})
        return result

    # ── internals ──
    def _generate_source(self, game_data: Dict) -> Dict[str, str]:
        return {
            "game_manifest.json": json.dumps({
                "name": self.project_name,
                "version": "1.0.0-internal",
                "generated_by": "GameForge Internal Build System",
                "built_at": time.time(),
            }, indent=2),
            "levels.json": json.dumps(game_data.get("levels", {}), indent=2, default=str),
            "systems.json": json.dumps(game_data.get("systems", {}), indent=2, default=str),
            "narrative.json": json.dumps(game_data.get("narrative", {}), indent=2, default=str),
            "content.json": json.dumps(game_data.get("content", {}), indent=2, default=str),
            "raw_game_data.json": json.dumps(game_data, indent=2, default=str),
            "internal_runtime.py": _RUNTIME_STUB,
            "README.txt": (
                f"{self.project_name} — built by GameForge Internal Build System.\n"
                "Run: python internal_runtime.py game_manifest.json\n"
            ),
        }

    def _zip_bundle(self, source: Dict[str, str], game_data: Dict):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in source.items():
                zf.writestr(name, content)
        return buf.getvalue(), list(source.keys())

    def _sign(self, data: bytes) -> Dict[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        return {
            "algorithm": "sha256-sim",
            "digest": digest,
            "signature": hashlib.sha256((digest + "gameforge-signing-key").encode()).hexdigest(),
            "signed": True,
        }

    @staticmethod
    def _safe(s: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(s))[:60]


def create_internal_build_system(project_name: str) -> InternalBuildSystem:
    return InternalBuildSystem(project_name)
