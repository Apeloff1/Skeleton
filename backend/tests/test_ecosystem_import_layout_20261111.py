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
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
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
# Concurrent first access must produce a single orchestrator.
module = importlib.import_module(route.get_orchestrator.__module__)
with ThreadPoolExecutor(max_workers=12) as pool:
    singleton_ids = list(pool.map(lambda _: id(route.get_orchestrator()), range(48)))
assert len(set(singleton_ids)) == 1
paths = {item.path for item in route.router.routes}
# FastAPI stores APIRouter prefix on every registered route, not bare paths.
expected = {route.router.prefix + suffix for suffix in (
    "/health", "/session", "/run", "/session/{session_id}",
    "/session/{session_id}/export", "/sessions", "/studio/status"
)}
assert expected <= paths, (expected - paths, paths)
methods = {(item.path, method) for item in route.router.routes for method in item.methods}
assert (route.router.prefix + "/session", "POST") in methods
assert (route.router.prefix + "/run", "POST") in methods
assert (route.router.prefix + "/health", "GET") in methods
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
# Complete the real pipeline and verify a detached five-file Godot export.
ran = asyncio.run(route.run_session(route.RunBody(session_id=created["session_id"])))
assert ran["ok"] is True and ran["status"] == "sealed", ran
exported = asyncio.run(route.session_export(created["session_id"]))
assert exported["ok"] and len(exported["files"]) == 5
assert {item["path"] for item in exported["files"]} == {
    "project.godot", "world.tscn", "player.gd", "boss.gd", "cutscene.gd"
}
exported["files"][0]["content"] = "tampered"
assert asyncio.run(route.session_export(created["session_id"]))["files"][0]["content"] != "tampered"
# Evict only completed sessions, then deny capacity when all jobs are pending.
orch = route.get_orchestrator()
module.MAX_SESSIONS = 3
orch.rate.limit = 100
pending = [asyncio.run(route.create_session(route.CreateSessionBody(brief="Pending original world"))) for _ in range(2)]
assert all(item["ok"] for item in pending)
new = asyncio.run(route.create_session(route.CreateSessionBody(brief="Original world after eviction")))
assert new["ok"] and orch.session_count() == 3
assert orch.status(created["session_id"])["reason"] == "session_not_found"
try:
    asyncio.run(route.create_session(route.CreateSessionBody(brief="Must reject when full")))
    raise AssertionError("expected capacity HTTP error")
except HTTPException as exc:
    assert exc.status_code == 503 and exc.detail == "session_capacity"
with orch._sessions_lock:
    orch.sessions[pending[0]["session_id"]].status = "failed"
newer = asyncio.run(route.create_session(route.CreateSessionBody(brief="Original world after terminal eviction")))
assert newer["ok"] and orch.session_count() == 3
assert orch.status(pending[0]["session_id"])["reason"] == "session_not_found"
assert orch.status(pending[1]["session_id"])["ok"]
assert orch._run_lock.acquire(blocking=False)
try:
    busy = orch.run(pending[1]["session_id"])
    assert busy["reason"] == "studio_busy"
finally:
    orch._run_lock.release()
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

    def test_import_failures_are_not_swallowed(self):
        source = (ROOT / "backend/core/ecosystem_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("from skeleton.jeeves.studio.integrated_studio import IntegratedStudio", source)
        self.assertNotIn("from jeeves.studio.integrated_studio import IntegratedStudio", source)
        self.assertNotIn("except Exception:  # pragma: no cover - import path differs by cwd", source)

    def test_dockerfile_production_layout(self):
        source = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("mv backend /runtime", source)
        self.assertIn("COPY --from=runtime-source --chown=appuser:appuser /runtime/ .", source)

if __name__ == "__main__":
    unittest.main()
