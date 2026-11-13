"""Read-only mirror routes must mount before optional learning package imports."""

from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.routes_registry import register_routes


def test_mirror_room_route_registers_even_when_observatory_is_unavailable(monkeypatch):
    from routes import mirror_room

    app = FastAPI()
    report = register_routes(app, [("routes.mirror_room", "router")])
    assert report["ok"] == 1, report
    assert report["mounted_names"] == ["routes.mirror_room"]

    real_import = builtins.__import__

    def block_learning(name, *args, **kwargs):
        if name.startswith("skeleton.learning.mirror_room"):
            raise ImportError("optional learning package unavailable")
        return real_import(name, *args, **kwargs)

    # Register first, then deliberately fail every observatory import.
    # The mounted endpoints must fail closed without exposing import detail.
    with TestClient(app) as client:
        monkeypatch.setattr(builtins, "__import__", block_learning)
        for url in (
            "/api/mirror-room/status",
            "/api/mirror-room/file-tree",
            "/api/mirror-room/observatory",
        ):
            response = client.get(url)
            assert response.status_code == 503, response.text
            assert response.json() == {"detail": "Mirror Room observatory unavailable"}


def test_mirror_room_module_import_defers_expensive_learning_package():
    script = """
import builtins
real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name.startswith('skeleton.learning.mirror_room'):
        raise AssertionError('learning package imported during router registration')
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked
from routes.mirror_room import router
assert len(router.routes) >= 3
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
