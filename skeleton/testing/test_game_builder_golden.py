"""Golden briefs: design spec, content, Godot project, core loop, repair."""
from __future__ import annotations

import json
import os
import time

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.__main__ import main
from skeleton.api.hmac_seal import mint_seal
from skeleton.api.routes import router
from skeleton.api.server import get_state, skeleton_error_handler
from skeleton.forge.game_builder import build_playable_game, prove_and_repair
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS, SCHEMA_VERSION
from skeleton.forge.genre_project import CORE_LOOP_GD, execute_core_loop
from skeleton.forge.universal import Forge
from skeleton.kernel.errors import SkeletonError

SECRET = "game-builder-golden"
REQUIRE_GODOT = os.environ.get("SKELETON_GAME_BUILDER_REQUIRE_GODOT") == "1"
PLAYTEST_MODE = "require" if REQUIRE_GODOT else "off"
CONTENT_KEYS = (
    "levels",
    "encounters",
    "economy",
    "combat_design",
    "narrative",
    "longform",
    "animation",
    "vfx",
    "physics",
)


@pytest.fixture(scope="module")
def built():
    return {
        item["genre"]: build_playable_game(item["brief"], playtest_mode=PLAYTEST_MODE)
        for item in GOLDEN_BRIEFS
    }


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    state = get_state()
    saved = getattr(state, "forge", None)
    state.forge = Forge()
    app = FastAPI()
    app.add_exception_handler(SkeletonError, skeleton_error_handler)
    app.include_router(router, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as api:
        yield api
    state.forge = saved


def _headers():
    return {"x-gf-seal": mint_seal("golden", secret=SECRET)}


def _engine_log(playtest: dict) -> str:
    return "\n".join(
        str(step.get("log_tail") or "")
        for step in (playtest.get("steps") or [])
        if isinstance(step, dict)
    )


@pytest.mark.parametrize("item", GOLDEN_BRIEFS, ids=[item["id"] for item in GOLDEN_BRIEFS])
def test_golden_brief_builds_and_runs_core_loop(item, built):
    result = built[item["genre"]]
    assert result["ok"] is True, result.get("error") or result.get("check") or result.get("playtest")
    spec = result["spec"]
    assert spec["schema_version"] == SCHEMA_VERSION
    assert spec["version"] == 1
    assert spec["genre"] == item["genre"]
    assert spec["engine"] == "godot4"
    assert spec["fantasy"]
    assert spec["core_loop"]
    assert spec["scope"] == "small"
    assert len(spec["spec_id"]) == 64
    content = result["content"]
    assert content["schema_version"] == "skeleton.game_content_bundle.v1"
    for key in CONTENT_KEYS:
        assert content[key], key
    assert content["longform"]["completed"] is True
    assert content["longform"]["chapters"] == 8
    assert content["longform"]["beat_count"] == 24
    assert content["longform"]["ending_id"] == "return"
    assert content["narrative"][0]["id"] == "hook-0"
    assert result["core_loop"]["passed"] is True
    assert result["marker"] == execute_core_loop(content, spec["genre"])
    assert result["check"]["ok"] is True
    assert result["pipeline"]["sim_passed"] is True
    assert "project.godot" in result["files"]
    assert result["files"]["scripts/autoloads/core_loop.gd"] == CORE_LOOP_GD
    assert 'CoreLoop="*res://scripts/autoloads/core_loop.gd"' in result["files"]["project.godot"]
    assert result["content"]["combat_design"]["duel_digest"]
    assert result["content"]["economy"]["ledger_digest"]
    assert result["content"]["physics"]["position"][0] > 0
    if REQUIRE_GODOT:
        playtest = result["playtest"]
        assert playtest["passed"] is True, playtest
        assert result["proof"] in _engine_log(playtest)


def test_repair_reads_syntax_error_and_restores_core_loop(built):
    result = built["top_down_shooter"]
    files = dict(result["files"])
    files["scripts/autoloads/core_loop.gd"] = "extends Node\nfunc _ready():\n\tprint('CORE_LOOP_OK'\n"
    proved = prove_and_repair(
        files,
        result["spec"],
        result["content"],
        playtest_mode="off",
        max_rounds=3,
    )
    assert proved["ok"] is True
    assert proved["repair"]["rounds"] >= 2
    assert any(action["action"] == "restore_core_loop" and action["read"] for action in proved["repair"]["actions"])
    assert proved["files"]["scripts/autoloads/core_loop.gd"] == CORE_LOOP_GD
    assert proved["marker"] == result["marker"]


def test_cli_prints_platformer_build(capsys):
    code = main(["game", GOLDEN_BRIEFS[1]["brief"], "--playtest", "off", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["spec"]["genre"] == "platformer"
    assert payload["marker"].startswith("goal:")
    assert "files" not in payload


def _poll_build(client, execution_id: str):
    deadline = time.time() + 90
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/v1/game/build/{execution_id}", headers=_headers())
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"succeeded", "failed", "cancelled"}:
            return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_api_builds_roguelike_and_rejects_empty_brief(client):
    missing = client.post("/api/v1/game/build", json={}, headers=_headers())
    assert missing.status_code == 422
    response = client.post(
        "/api/v1/game/build",
        json={"brief": GOLDEN_BRIEFS[2]["brief"], "playtest": "off", "include_files": True},
        headers=_headers(),
    )
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert accepted["execution_id"]
    assert accepted["job_id"]
    assert accepted["status_ref"] == f"/api/v1/game/build/{accepted['execution_id']}"
    assert "ok" not in accepted
    polled = _poll_build(client, accepted["execution_id"])
    assert polled["status"] == "succeeded", polled
    body = polled["result"]
    assert body["ok"] is True
    assert body["spec"]["genre"] == "rpg_roguelike"
    assert body["marker"].startswith("rooms:")
    assert "project.godot" in body["files"]
    assert body["stubbed"]
