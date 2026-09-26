"""HTTP E2E: /gameforge/run and /gameforge/intake drive the ten-stage GameForgeRun.

Regression: ``state.gameforge`` is the questionnaire ``pipelines.GameForge``
(no ``execute``), so both routes returned 500. They now run the context
pipeline, share the server cockpit (``BIND ARCHETYPE``), and expose
``playtest`` / ``repair_mode``.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api.hmac_seal import mint_seal
from skeleton.api.routes import router
from skeleton.api.server import get_state, skeleton_error_handler
from skeleton.context.cockpit import Cockpit
from skeleton.context.questionnaire import BEATS
from skeleton.forge import playtest as pt
from skeleton.forge.universal import Forge
from skeleton.kernel.errors import SkeletonError
from skeleton.pipelines import GameForge

SECRET = "gameforge-http-e2e"
ANSWERS = {b["id"]: next(iter(b["options"])) for b in BEATS if b["id"] != "era_explicit"}
_BIN = pt.resolve_binary()[0]


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    state = get_state()
    saved = {k: getattr(state, k, None) for k in ("forge", "gameforge", "cockpit", "gameforge_run")}
    state.forge = Forge()
    state.gameforge = GameForge()
    state.cockpit = Cockpit()
    state.gameforge_run = None
    app = FastAPI()
    app.add_exception_handler(SkeletonError, skeleton_error_handler)
    app.include_router(router, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    for key, value in saved.items():
        setattr(state, key, value)


def _h():
    return {"x-gf-seal": mint_seal("e2e", secret=SECRET)}


def _post(client, path, body):
    return client.post(f"/api/v1{path}", json=body, headers=_h())


def test_gameforge_run_route_executes_pipeline(client):
    res = _post(client, "/gameforge/run", {"vision": "a tense extraction heist"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["succeeded"] is True
    assert body["complete"] is True
    assert body["forge"]["verification"]["accepted"] is True
    assert body["forge"]["verify_loop"]["repair_mode"] == "apply"
    assert "project.godot" in body["file_names"]
    assert "files" not in body
    assert body["playtest"] is None


def test_gameforge_intake_route_questionnaire_to_verified_build(client):
    res = _post(client, "/gameforge/intake", {"answers": ANSWERS, "include_files": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["succeeded"] is True
    assert body["era"] == body["intake"]["era"]
    assert body["sim"]["passed"] is True
    assert "project.godot" in body["files"]


def test_run_route_accepts_answers(client):
    res = _post(client, "/gameforge/run", {"answers": {"genre": "metroidvania"}})
    assert res.status_code == 200, res.text
    assert res.json()["era"] == "metroidvania"


def test_repair_mode_suggest_reaches_loop(client):
    res = _post(client, "/gameforge/run", {"vision": "a heist", "repair_mode": "suggest"})
    assert res.status_code == 200, res.text
    assert res.json()["forge"]["verify_loop"]["repair_mode"] == "suggest"


@pytest.mark.parametrize("field,value", [("playtest", "sometimes"), ("repair_mode", "rewrite")])
def test_bad_modes_are_client_errors(client, field, value):
    res = _post(client, "/gameforge/run", {"vision": "a heist", field: value})
    assert 400 <= res.status_code < 500, res.text


def test_playtest_auto_without_binary_reports_unavailable(client, monkeypatch):
    monkeypatch.setattr(pt, "resolve_binary", lambda binary=None: (None, "missing-godot-binary", False))
    res = _post(client, "/gameforge/intake", {"answers": ANSWERS, "playtest": "auto"})
    assert res.status_code == 200, res.text
    assert res.json()["playtest"]["status"] == "unavailable"


def test_cockpit_bind_archetype_applies_over_http(client):
    state = get_state()
    state.cockpit.apply("BIND ARCHETYPE auto")
    res = _post(client, "/gameforge/run", {"vision": "a gothic castle metroidvania with a grappling hook"})
    assert res.status_code == 200, res.text
    assert res.json()["forge"]["composition"] is not None


def test_forge_archetype_route_repair_mode(client):
    res = _post(client, "/forge/archetype", {"name": "extraction", "repair_mode": "suggest"})
    assert res.status_code == 200, res.text
    assert res.json()["verify_loop"]["repair_mode"] == "suggest"


@pytest.mark.skipif(_BIN is None, reason="no Godot binary (set SKELETON_GODOT_BIN)")
def test_intake_route_require_playtest_boots_build(client):
    res = _post(client, "/gameforge/intake", {"answers": ANSWERS, "playtest": "require"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["succeeded"] is True
    assert body["playtest"]["status"] == "passed"
