"""E2E: GameForge 7-step conductor -> ten-stage GameForgeRun -> playable Godot.

VisionRequest -> 7 steps -> manifest ok -> playable Godot files ->
source manifest + cockpit ledger bind the conductor receipt chain.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

from skeleton.context.pipeline import GameForgeRun
from skeleton.forge.archetype_content import content_archetypes, verify_archetype_content
from skeleton.forge.gdscript_check import check_ok
from skeleton.forge.playable_portal import verify_playable_portal
from skeleton.forge.source_manifest import source_manifest
from skeleton.gameforge import STEPS, GameForgeConductor, ConductorConfig, verify_manifest
from skeleton.gameforge.serving import (
    GENRE_PLAYABLE, MANIFEST_PATH, SCHEMA, admit_conductor_manifest, cli, conduct,
    conductor_manifest_source, public_envelope,
)

REQ = {"title": "Lantern Run", "pitch": "Carry light through caves", "genre": "shooter",
       "pillars": ["light", "speed"], "target_minutes": 15}


class _Recording:
    """Pure (non-persisting) GameForgeRun factory that keeps the runner."""

    def __init__(self):
        self.runners = []

    def __call__(self):
        runner = GameForgeRun()
        self.runners.append(runner)
        return runner


def _never():
    raise AssertionError("forge must not run when the conductor halts")


@pytest.fixture(scope="module")
def happy():
    rec = _Recording()
    return conduct(REQ, runner_factory=rec), rec.runners[0]


def _conductor_manifest():
    res = GameForgeConductor(config=ConductorConfig(target="desktop")).run(REQ)
    assert res.ok
    return res.manifest.to_dict()


# --- the one product path ----------------------------------------------------
def test_vision_runs_all_seven_steps_then_ten_stage_forge(happy):
    env, _ = happy
    assert env["schema"] == SCHEMA and env["ok"] is True
    assert env["conductor"]["ok"] and env["conductor"]["completed"] == list(STEPS)
    stages = [s["name"] for s in env["forge"]["run"]["stages"]]
    assert stages == ["ingest", "detect", "tensor", "lattice", "oracle", "forge",
                      "jeeves", "sim", "emit", "seal"]
    assert all(s["status"] != "FAILED" for s in env["forge"]["run"]["stages"])
    assert env["forge"]["succeeded"] is True


def test_conductor_manifest_verifies_and_is_emitted_into_godot_project(happy):
    env, _ = happy
    files = env["files"]
    body = files[MANIFEST_PATH]
    data = json.loads(body)
    verify_manifest(data)
    assert data["manifest_digest"] == env["conductor_manifest_digest"]
    assert data["steps"] == list(STEPS)
    assert env["conductor_manifest_bound"] is True
    assert body == conductor_manifest_source(env["conductor"]["manifest"])


def test_playable_godot_files_pass_static_and_source_verification(happy):
    env, _ = happy
    files = env["files"]
    mode = env["playable"]["mode"]
    assert mode == "combat_loop" and env["playable"]["fallback"] is False
    assert "project.godot" in files
    ok, problems = check_ok(files)
    assert ok, problems
    assert verify_archetype_content(files, mode)
    assert verify_playable_portal(files, mode)


def test_source_manifest_seals_conductor_file(happy):
    env, _ = happy
    sealed = env["forge"]["source_manifest"]
    assert sealed == source_manifest(env["files"])
    assert sealed["files"][MANIFEST_PATH] == env["conductor_manifest_file_sha256"]
    receipt = env["forge"]["conductor"]
    assert receipt["sealed"] is True and receipt["path"] == MANIFEST_PATH
    assert receipt["manifest_digest"] == env["conductor_manifest_digest"]
    assert receipt["receipt_head"] == env["conductor"]["manifest"]["receipts"][-1]["link"]


def test_cockpit_ledger_binds_conductor_digest_at_ingest_and_emit(happy):
    env, runner = happy
    ledger = runner.cockpit.ledger.to_dict()
    assert ledger["valid"] is True
    by_stage = {b["stage"]: b["payload"] for b in ledger["blocks"]}
    digest = env["conductor_manifest_digest"]
    assert by_stage["ingest"]["conductor_manifest_digest"] == digest
    assert by_stage["ingest"]["conductor_game_id"] == "lantern-run"
    assert by_stage["emit"]["conductor_manifest_digest"] == digest
    assert env["ledger"]["valid"] is True


def test_product_path_is_deterministic():
    a = conduct(REQ, runner_factory=GameForgeRun)
    b = conduct(REQ, runner_factory=GameForgeRun)
    assert a["conductor_manifest_digest"] == b["conductor_manifest_digest"]
    assert a["files"][MANIFEST_PATH] == b["files"][MANIFEST_PATH]


@pytest.mark.parametrize("genre", sorted(GENRE_PLAYABLE))
def test_every_conductor_genre_emits_an_honest_playable_mode(genre):
    env = conduct({**REQ, "genre": genre}, runner_factory=GameForgeRun)
    assert env["ok"] is True
    preferred = GENRE_PLAYABLE[genre]
    if preferred in content_archetypes():
        assert env["playable"] == {"requested": True, "mode": preferred,
                                   "preferred_mode": preferred, "fallback": False}
    else:
        assert env["playable"]["mode"] == "extraction" and env["playable"]["fallback"] is True
    assert verify_archetype_content(env["files"], env["playable"]["mode"])


def test_no_playable_still_binds_conductor_manifest():
    env = conduct(REQ, playable_content=False, runner_factory=GameForgeRun)
    assert env["ok"] is True and env["playable"]["requested"] is False
    assert MANIFEST_PATH in env["files"]
    assert env["forge"].get("playable_portal") is None


# --- fail closed -------------------------------------------------------------
def test_unknown_genre_halts_at_vision_before_any_emit():
    env = conduct({**REQ, "genre": "mmo"}, runner_factory=_never)
    assert env["ok"] is False and env["forge"] is None and "files" not in env
    assert env["conductor"]["completed"] == []
    assert env["conductor"]["error"]["step"] == "vision"
    assert env["halted_at"] == "vision"


def test_unknown_conductor_era_halts_without_forge():
    env = conduct(REQ, conductor_era="NOT_AN_ERA", runner_factory=_never)
    assert env["ok"] is False and env["forge"] is None


def test_budget_overrun_halts_without_forge():
    env = conduct(REQ, budget_bytes=1, runner_factory=_never)
    assert env["ok"] is False and env["conductor"]["error"]["code"] == "gameforge.budget"


def test_tampered_conductor_manifest_is_rejected_by_ten_stage_run():
    data = _conductor_manifest()
    data["game_id"] = "forged"
    with pytest.raises(ValueError, match="conductor manifest rejected"):
        GameForgeRun().execute("caves", conductor_manifest=data)


def test_partial_step_manifest_is_rejected():
    data = _conductor_manifest()
    admit_conductor_manifest(data)
    with pytest.raises(ValueError):
        admit_conductor_manifest({**data, "steps": data["steps"][:3]})
    with pytest.raises(ValueError):
        admit_conductor_manifest("not a mapping")


def test_conductor_manifest_requires_godot_target():
    with pytest.raises(ValueError, match="Godot target"):
        GameForgeRun().execute("caves", target="web", conductor_manifest=_conductor_manifest())


def test_ten_stage_run_without_conductor_is_unchanged():
    payload = GameForgeRun().execute("caves", playable_content=True)
    assert payload["succeeded"] is True
    assert "conductor" not in payload and MANIFEST_PATH not in payload["files"]


def test_public_envelope_hides_files_unless_requested(happy):
    env, _ = happy
    out = public_envelope(env)
    assert "files" not in out and MANIFEST_PATH in out["file_names"]
    assert public_envelope(env, include_files=True)["files"] == env["files"]


# --- CLI ---------------------------------------------------------------------
def test_cli_json_runs_product_path(capsys):
    code = cli(["--title", "Lantern Run", "--pitch", "Carry light through caves",
                "--genre", "shooter", "--pillar", "light", "--pillar", "speed", "--json"],
               runner_factory=GameForgeRun)
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["ok"] is True and MANIFEST_PATH in out["file_names"]
    assert "files" not in out


def test_cli_bad_genre_exits_nonzero(capsys):
    code = cli(["--title", "X", "--pitch", "Y", "--genre", "mmo"], runner_factory=_never)
    assert code == 1
    assert "halted at vision" in capsys.readouterr().err


def test_cli_writes_project_with_conductor_manifest(tmp_path, capsys):
    out_dir = tmp_path / "lantern"
    code = cli(["--title", "Lantern Run", "--pitch", "Carry light", "--genre", "puzzle",
                "--pillar", "light", "--out", str(out_dir)], runner_factory=GameForgeRun)
    capsys.readouterr()
    assert code == 0
    assert (out_dir / "project.godot").is_file()
    verify_manifest(json.loads((out_dir / MANIFEST_PATH).read_text(encoding="utf-8")))


def test_main_dispatches_gameforge_conduct(monkeypatch, capsys):
    import skeleton.__main__ as entry
    monkeypatch.setattr(GameForgeRun, "live", classmethod(lambda cls, **_: cls()))
    code = entry.main(["gameforge-conduct", "--title", "Lantern Run", "--pitch", "Carry light",
                       "--genre", "racing", "--pillar", "speed", "--json"])
    assert code == 0 and json.loads(capsys.readouterr().out)["ok"] is True


# --- HTTP --------------------------------------------------------------------
@pytest.fixture()
def client(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from backend.routes.skeleton_gameforge import router
    monkeypatch.setattr(GameForgeRun, "live", classmethod(lambda cls, **_: cls()))
    app = fastapi.FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_http_conduct_ok(client):
    r = client.post("/api/skeleton/conduct", json=REQ)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["conductor"]["completed"] == list(STEPS)
    assert body["forge"]["conductor"]["sealed"] is True
    assert "files" not in body


def test_http_conduct_include_files_exports_verified_source(client):
    r = client.post("/api/skeleton/conduct", json={**REQ, "include_files": True})
    body = r.json()
    assert body["source_export"]["status"] == "ready"
    assert source_manifest(body["files"])["sha256"] == body["source_export"]["manifest_sha256"]
    verify_manifest(json.loads(body["files"][MANIFEST_PATH]))


def test_http_conduct_rejects_server_paths(client):
    r = client.post("/api/skeleton/conduct", json={**REQ, "project_root": "/tmp/x"})
    assert r.status_code == 422
    r = client.post("/api/skeleton/conduct", json={**REQ, "overwrite": True})
    assert r.status_code == 422


def test_http_conduct_halts_closed_on_bad_vision(client):
    r = client.post("/api/skeleton/conduct", json={**REQ, "genre": "mmo"})
    assert r.status_code == 422
    assert r.json()["detail"]["halted_at"] == "vision"


# --- real Godot (optional) ---------------------------------------------------
@pytest.mark.skipif(
    not (os.environ.get("SKELETON_GODOT_BIN") or shutil.which("godot")),
    reason="Godot binary not available",
)
def test_real_godot_boots_conducted_playable_scene():
    env = conduct(REQ, playtest="require", runner_factory=GameForgeRun)
    assert env["ok"] is True, env["forge"]
    assert env["forge"]["playable_scene_playtest"]["passed"] is True
