"""Fails when docs/api/API_V1_ROUTES.md drifts from create_app()'s route table."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_api_v1_reference.py"


def _load():
    spec = importlib.util.spec_from_file_location("gen_api_v1_reference", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_api_v1_reference_matches_route_table(monkeypatch):
    monkeypatch.delenv("SKELETON_OMNIFABRIC_API", raising=False)
    mod = _load()
    expected = mod.render(mod.collect_rows())
    current = mod.OUT.read_text(encoding="utf-8")
    assert current == expected, "API reference is stale; run python scripts/gen_api_v1_reference.py"


def test_reference_covers_core_surfaces():
    mod = _load()
    rows = mod.collect_rows()
    paths = {r[0] for r in rows}
    assert "/api/v1/events" in paths  # realtime ADR #4101
    assert any(p.startswith("/api/v1/projects") for p in paths)
    assert not any("/secrets" in p for p in paths)  # cortex guard
    auth = {r[0]: r[2] for r in rows}
    assert auth["/api/v1/events"] == "sealed"
    assert all(a == "engine-bearer" for p, a in auth.items() if p.startswith("/api/v1/engine/"))
