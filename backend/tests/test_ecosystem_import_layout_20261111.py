"""Regression: ecosystem router works in flattened production and checkout layouts."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SMOKE = r"""
import asyncio
import importlib
import sys
import types
from pathlib import Path
root = Path(sys.argv[1])
mode = sys.argv[2]
if mode == "flat":
    sys.path.insert(0, str(root / "backend"))
    # Make skeleton available without exposing the absent backend/ namespace.
    skeleton = types.ModuleType("skeleton")
    skeleton.__path__ = [str(root / "skeleton")]
    sys.modules["skeleton"] = skeleton
    route = importlib.import_module("routes.ecosystem_api")
    assert "backend" not in sys.modules, "unexpected backend namespace"
    assert route.get_orchestrator.__module__ == "core.ecosystem_orchestrator"
else:
    sys.path.insert(0, str(root))
    route = importlib.import_module("backend.routes.ecosystem_api")
    assert route.get_orchestrator.__module__ == "backend.core.ecosystem_orchestrator"
assert route.router.prefix == "/api/ecosystem"
paths = {item.path for item in route.router.routes}
assert {"/health", "/session", "/run", "/session/{session_id}",
        "/session/{session_id}/export", "/sessions", "/studio/status"} <= paths
health = asyncio.run(route.ecosystem_health())
assert health["ok"] is True
created = asyncio.run(route.create_session(
    route.CreateSessionBody(brief="An original offline puzzle world", era="ash")
))
assert created["ok"] is True
status = asyncio.run(route.session_status(created["session_id"]))
assert status["ok"] is True and status["status"] == "created"
listed = asyncio.run(route.list_sessions())
assert any(item["session_id"] == created["session_id"] for item in listed["sessions"])
"""

class EcosystemImportLayoutTests(unittest.TestCase):
    def _run_layout(self, layout: str):
        result = subprocess.run(
            [sys.executable, "-I", "-c", SMOKE, str(ROOT), layout],
            cwd=ROOT / "backend" if layout == "flat" else ROOT,
            capture_output=True, text=True, check=False, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_flat_production_router(self):
        self._run_layout("flat")

    def test_source_checkout_router(self):
        self._run_layout("checkout")

    def test_dockerfile_production_layout(self):
        source = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("mv backend /runtime", source)
        self.assertIn("COPY --from=runtime-source --chown=appuser:appuser /runtime/ .", source)

if __name__ == "__main__":
    unittest.main()
