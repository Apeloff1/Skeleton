"""Planner, QA, structured briefs, deadline, and the game.build queue."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api.hmac_seal import mint_seal
from skeleton.api.routes import router
from skeleton.api.server import get_state, skeleton_error_handler
from skeleton.forge.game_builder import (
    PROJECTS_SCHEMA,
    RUN_SCHEMA,
    _apply_planner,
    build_playable_game,
    coerce_brief,
    prove_and_repair,
)
from skeleton.forge.game_build_queue import (
    IdempotencyMismatch,
    enqueue_game_build,
    execution_view,
    using_internal_systems_queue,
)
from skeleton.forge.game_design_spec import compile_brief
from skeleton.forge.universal import Forge
from skeleton.kernel.errors import SkeletonError

SECRET = "game-build-contracts"
_PIPELINE = {
    "succeeded": True,
    "era": "extraction_now",
    "files": {"project.godot": "config_version=5\n"},
    "sim": {"passed": True},
    "forge": {"file_count": 1, "blueprint_id": "bp"},
    "playtest": None,
}
_PROOF = {
    "ok": True,
    "files": {"project.godot": "config_version=5\n"},
    "marker": "goal:1",
    "proof": "goal:1",
    "check": {"ok": True, "problems": []},
    "core_loop": {"passed": True, "marker": "goal:1"},
    "playtest": None,
    "repair": {"rounds": 1, "actions": []},
}


@pytest.fixture
def fallback_queue(monkeypatch):
    """Select the optional adapter explicitly; the durable owner is now installed."""
    from skeleton.forge import game_build_queue

    queue = game_build_queue._FallbackQueue()
    monkeypatch.setattr(game_build_queue, "_real_api", lambda: None)
    monkeypatch.setattr(game_build_queue, "_fallback", queue)
    yield queue
    if queue._worker is not None:
        queue._worker.stop(timeout=1)


def _patch_engine(monkeypatch):
    def fake_execute(self, vision, **kwargs):
        del self, kwargs
        return dict(_PIPELINE, intake={"vision": vision or "answered"})

    monkeypatch.setattr("skeleton.context.pipeline.GameForgeRun.execute", fake_execute)
    monkeypatch.setattr(
        "skeleton.forge.game_builder.generate_content",
        lambda *args, **kwargs: {"schema_version": "skeleton.game_content_bundle.v1"},
    )
    monkeypatch.setattr(
        "skeleton.forge.game_builder.attach_genre",
        lambda files, spec, content: dict(files),
    )
    monkeypatch.setattr(
        "skeleton.forge.game_builder.prove_and_repair",
        lambda *args, **kwargs: dict(_PROOF),
    )


def test_longform_campaign_completes_and_scales(tmp_path):
    from skeleton.forge.game_content import generate_content
    from skeleton.forge.genre_project import execute_core_loop

    small_spec = compile_brief("A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.")
    small = generate_content(small_spec, {}, root=tmp_path)
    story = small["longform"]
    assert story["schema_version"] == "skeleton.game_longform.v1"
    assert story["completed"] is True
    assert story["ending_id"] == "return"
    assert story["opening_id"] == "hook-0"
    assert [act["id"] for act in story["acts"]] == [
        "arrival", "trials", "fracture", "reckoning", "return",
    ]
    assert all(act["chapters"] > 0 for act in story["acts"])
    assert story["chapters"] == 8
    assert story["beat_count"] == 24
    assert len(story["beats"]) == 24
    assert small["narrative"][0]["id"] == "hook-0"
    assert small["narrative"][-1]["act"] == "return"
    assert execute_core_loop(small, "platformer").startswith("goal:")
    again = generate_content(small_spec, {}, root=tmp_path)
    assert again["longform"]["digest"] == story["digest"]

    large_spec = compile_brief("A large campaign roguelike. Fantasy: the drowned archive.")
    large = generate_content(large_spec, {}, root=tmp_path)
    assert large["genre"] == "rpg_roguelike"
    assert large["scope"] == "large"
    assert large["longform"]["chapters"] == 120
    assert large["longform"]["beat_count"] == 360
    assert large["longform"]["completed"] is True
    assert large["longform"]["acts"][-1]["id"] == "return"
    assert execute_core_loop(large, "rpg_roguelike").startswith("rooms:")

    unfinished = dict(small)
    unfinished["longform"] = dict(story, completed=False)
    assert execute_core_loop(unfinished, "platformer") == "unfinished"
    missing_ending = dict(small)
    missing_ending["longform"] = dict(story, ending_id="")
    assert execute_core_loop(missing_ending, "platformer") == "unfinished"


def test_string_and_structured_briefs_are_both_valid():
    structured, text = coerce_brief({
        "schema_version": PROJECTS_SCHEMA,
        "title": "Ledges",
        "summary": "jump the rain-slick gaps",
        "genre": "platformer",
        "constraints": ["small"],
    })
    assert structured["schema_version"] == PROJECTS_SCHEMA
    assert compile_brief(text)["genre"] == "platformer"
    plain, plain_text = coerce_brief("A small platformer.")
    assert plain is None
    assert plain_text == "A small platformer."
    with pytest.raises(ValueError, match="unknown brief fields"):
        coerce_brief({"title": "Ledges", "owner_id": "hidden"})
    with pytest.raises(ValueError, match="title is required"):
        coerce_brief({"summary": "no title"})


def test_planner_hook_cannot_change_genre_engine_brief_or_scope(monkeypatch):
    _patch_engine(monkeypatch)
    spec = compile_brief("A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.")

    def planner(proposed):
        changed = dict(proposed)
        changed["genre"] = "rpg_roguelike"
        changed["engine"] = "other"
        changed["brief"] = "a different game"
        changed["scope"] = "large"
        changed["fantasy"] = "discarded with the locked fields"
        return changed

    assert _apply_planner(spec, planner) == dict(spec)

    def enrich(proposed):
        changed = dict(proposed)
        changed["fantasy"] = "rain on the gantry"
        changed["production"] = {"pillar": "jump"}
        return changed

    result = build_playable_game(
        "A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.",
        planner=enrich,
        playtest_mode="off",
        deadline_s=5,
    )
    assert result["ok"] is True
    assert result["spec"]["genre"] == "platformer"
    assert result["spec"]["fantasy"] == "rain on the gantry"
    assert result["spec"]["production"] == {"pillar": "jump"}
    assert "qa" not in result


def test_qa_repair_requested_runs_one_more_proof(monkeypatch):
    _patch_engine(monkeypatch)
    calls = {"n": 0}

    def prove(*args, **kwargs):
        del args, kwargs
        calls["n"] += 1
        return dict(_PROOF)

    monkeypatch.setattr("skeleton.forge.game_builder.prove_and_repair", prove)

    def qa(build):
        assert "check" in build
        assert "playtest" in build
        if calls["n"] == 1:
            return {"passed": False, "repair_requested": True, "issues": [{"source": "checker"}]}
        return {"passed": True, "repair_requested": True}

    result = build_playable_game(
        {"title": "Ledges", "genre": "platformer", "summary": "jump"},
        qa=qa,
        actor_id="actor-1",
        tenant_id="tenant-1",
        playtest_mode="off",
        deadline_s=5,
    )
    assert calls["n"] == 2
    assert result["ok"] is True
    assert result["qa"]["passed"] is True
    assert "repair_requested" not in result["qa"]
    assert result["actor_id"] == "actor-1"
    assert result["tenant_id"] == "tenant-1"
    assert result["structured_brief"]["title"] == "Ledges"
    assert result["spec"]["genre"] == "platformer"


def test_build_deadline_zero_skips_materialise(monkeypatch):
    def execute(self, vision, **kwargs):
        del self, vision, kwargs
        raise AssertionError("materialise ran after the deadline")

    monkeypatch.setattr("skeleton.context.pipeline.GameForgeRun.execute", execute)
    result = build_playable_game(
        "A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.",
        playtest_mode="off",
        deadline_s=0,
    )
    assert result["ok"] is False
    assert "deadline exceeded" in result["error"]
    assert result["check"]["problems"] == ["deadline exceeded"]


def test_deadline_exceeded_mid_build_skips_later_stages(monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setattr("skeleton.forge.game_builder.time.monotonic", lambda: clock["now"])
    called = {"planner": 0, "qa": 0, "prove": 0, "content": 0}

    def execute(self, vision, **kwargs):
        del self, kwargs
        clock["now"] = 1_050.0
        return dict(_PIPELINE, intake={"vision": vision or "answered"})

    monkeypatch.setattr("skeleton.context.pipeline.GameForgeRun.execute", execute)
    monkeypatch.setattr(
        "skeleton.forge.game_builder.generate_content",
        lambda *args, **kwargs: called.__setitem__("content", called["content"] + 1),
    )
    monkeypatch.setattr(
        "skeleton.forge.game_builder.prove_and_repair",
        lambda *args, **kwargs: called.__setitem__("prove", called["prove"] + 1) or dict(_PROOF),
    )

    def planner(spec):
        called["planner"] += 1
        return spec

    def qa(build):
        del build
        called["qa"] += 1
        return {"passed": True}

    result = build_playable_game(
        "A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.",
        planner=planner,
        qa=qa,
        playtest_mode="off",
        deadline_s=1,
    )
    assert result["ok"] is False
    assert "deadline exceeded" in result["error"]
    assert called == {"planner": 0, "qa": 0, "prove": 0, "content": 0}


def test_deadline_blocks_qa_repair_pass(monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setattr("skeleton.forge.game_builder.time.monotonic", lambda: clock["now"])
    _patch_engine(monkeypatch)
    calls = {"n": 0}

    def prove(*args, **kwargs):
        del args, kwargs
        calls["n"] += 1
        return dict(_PROOF)

    monkeypatch.setattr("skeleton.forge.game_builder.prove_and_repair", prove)

    def qa(build):
        del build
        clock["now"] = 2_000.0
        return {"passed": False, "repair_requested": True, "issues": [{"source": "qa"}]}

    result = build_playable_game(
        "A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.",
        qa=qa,
        playtest_mode="off",
        deadline_s=30,
    )
    assert calls["n"] == 1
    assert result["ok"] is False
    assert "deadline exceeded" in result["error"]
    assert result["qa"]["passed"] is False
    assert "repair_requested" not in result["qa"]


def test_blocking_planner_and_qa_stop_at_the_deadline(monkeypatch):
    _patch_engine(monkeypatch)
    calls = {"prove": 0, "qa": 0}

    def prove(*args, **kwargs):
        del args, kwargs
        calls["prove"] += 1
        return dict(_PROOF)

    monkeypatch.setattr("skeleton.forge.game_builder.prove_and_repair", prove)

    def planner(spec):
        time.sleep(30)
        return spec

    started = time.monotonic()
    planned = build_playable_game(
        "A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.",
        planner=planner,
        playtest_mode="off",
        deadline_s=0.4,
    )
    assert time.monotonic() - started < 3
    assert calls["prove"] == 0
    assert planned["ok"] is False
    assert "deadline exceeded" in planned["error"]

    def qa(build):
        del build
        calls["qa"] += 1
        time.sleep(30)
        return {"passed": False, "repair_requested": True}

    started = time.monotonic()
    reviewed = build_playable_game(
        "A small platformer. Fantasy: ledges. Core loop: jump. Scope: small.",
        qa=qa,
        playtest_mode="off",
        deadline_s=0.4,
    )
    assert time.monotonic() - started < 3
    assert calls["qa"] == 1
    assert calls["prove"] == 1
    assert reviewed["ok"] is False
    assert "deadline exceeded" in reviewed["error"]


def test_playtest_does_not_start_godot_after_deadline(monkeypatch):
    from skeleton.forge import playtest as playtest_mod

    def boom(*args, **kwargs):
        del args, kwargs
        raise AssertionError("godot started after the deadline")

    monkeypatch.setattr(playtest_mod, "_run", boom)
    monkeypatch.setattr(playtest_mod, "resolve_binary", lambda binary: ("/usr/bin/godot", "env", True))
    report = playtest_mod.playtest(
        {"project.godot": "config_version=5\n"},
        frames=20,
        timeout=90,
        deadline=time.monotonic() - 1,
    )
    assert report["passed"] is False
    assert "deadline exceeded" in report["errors"]


def test_job_timeout_is_the_builder_deadline(monkeypatch, fallback_queue):
    seen = []

    def fake_build(brief, **kwargs):
        del brief
        seen.append(kwargs["deadline_s"])
        kwargs["on_progress"](0.4, "halfway")
        return {"ok": True, "schema_version": RUN_SCHEMA, "file_names": [], "stubbed": []}

    monkeypatch.setattr("skeleton.forge.game_builder.build_playable_game", fake_build)
    from skeleton.forge.game_build_queue import drain

    enqueue_game_build(
        {"brief": "A small platformer", "deadline_s": 120},
        actor_id="golden",
        tenant_id="default",
        idempotency_key="deadline-cap",
        timeout_s=30,
    )
    enqueue_game_build(
        {"brief": "A small platformer"},
        actor_id="golden",
        tenant_id="default",
        idempotency_key="deadline-timeout",
        timeout_s=45,
    )
    for _ in range(5):
        if len(seen) >= 2:
            break
        drain()
    assert seen == [30.0, 45.0]


def test_trailing_heartbeat_timeout_keeps_the_result(monkeypatch):
    from skeleton.forge.game_build_queue import JobTimeout, handle_game_build

    def fake_build(brief, **kwargs):
        del brief, kwargs
        return {
            "ok": True,
            "schema_version": RUN_SCHEMA,
            "file_names": ["project.godot"],
            "stubbed": [],
        }

    monkeypatch.setattr("skeleton.forge.game_builder.build_playable_game", fake_build)

    class Ctx:
        timeout_s = 30
        actor_id = "golden"
        tenant_id = "default"
        execution_id = "exe"
        project_id = None
        beats = 0

        def heartbeat(self, progress=None, message=None):
            del progress, message
            self.beats += 1
            if self.beats > 2:
                raise JobTimeout("job exceeded timeout_s=30")

        def progress(self, fraction, message=""):
            del fraction, message
            self.heartbeat()

    result = handle_game_build(Ctx(), {"brief": "A small platformer"})
    assert result["ok"] is True
    assert result["file_names"] == ["project.godot"]


def test_mid_build_heartbeat_timeout_propagates(monkeypatch):
    from skeleton.forge.game_build_queue import JobTimeout, handle_game_build

    def fake_build(brief, **kwargs):
        del brief
        kwargs["on_progress"](0.4, "halfway")
        return {"ok": True, "schema_version": RUN_SCHEMA, "file_names": [], "stubbed": []}

    monkeypatch.setattr("skeleton.forge.game_builder.build_playable_game", fake_build)

    class Ctx:
        timeout_s = 30
        actor_id = "golden"
        tenant_id = "default"
        execution_id = "exe"
        project_id = None
        beats = 0

        def heartbeat(self, progress=None, message=None):
            del progress, message
            self.beats += 1
            if self.beats >= 3:
                raise JobTimeout("job exceeded timeout_s=30")

        def progress(self, fraction, message=""):
            del fraction, message
            self.heartbeat()

    with pytest.raises(JobTimeout):
        handle_game_build(Ctx(), {"brief": "A small platformer"})


def test_deadline_zero_fails_before_godot():
    proved = prove_and_repair(
        {"project.godot": "config_version=5\n"},
        {"genre": "platformer", "brief": "x"},
        {},
        playtest_mode="require",
        deadline_s=0,
    )
    assert proved["ok"] is False
    assert proved["playtest"] is None
    assert "deadline exceeded" in proved["check"]["problems"]
    assert proved["repair"]["rounds"] == 0


def test_queue_enqueue_progress_and_idempotency(monkeypatch, fallback_queue):
    seen = []

    def fake_build(brief, **kwargs):
        seen.append(brief)
        kwargs["on_progress"](0.4, "halfway")
        return {
            "ok": True,
            "schema_version": RUN_SCHEMA,
            "spec": {"genre": "platformer"},
            "file_names": ["project.godot"],
            "files": {"project.godot": "config_version=5\n"},
            "stubbed": ["sprites"],
        }

    monkeypatch.setattr("skeleton.forge.game_builder.build_playable_game", fake_build)
    assert using_internal_systems_queue() is False
    payload = {"brief": "A small platformer", "playtest": "off", "include_files": True}
    handle = enqueue_game_build(
        payload, actor_id="golden", tenant_id="default", idempotency_key="contract-1",
    )
    assert handle.status == "queued"
    assert handle.replayed is False
    from skeleton.forge.game_build_queue import drain

    assert drain() == 1
    view = execution_view(handle.execution_id)
    assert view["status"] == "succeeded"
    assert view["progress"] == 1.0
    assert view["result"]["ok"] is True
    assert "project.godot" in view["result"]["files"]
    assert seen == ["A small platformer"]
    replay = enqueue_game_build(
        payload, actor_id="golden", tenant_id="default", idempotency_key="contract-1",
    )
    assert replay.replayed is True
    assert replay.job_id == handle.job_id
    with pytest.raises(IdempotencyMismatch):
        enqueue_game_build(
            {"brief": "different", "playtest": "off"},
            actor_id="golden",
            tenant_id="default",
            idempotency_key="contract-1",
        )


@pytest.fixture()
def client(monkeypatch, tmp_path, fallback_queue):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)

    def fake_build(brief, **kwargs):
        kwargs["on_progress"](1.0, "done")
        return {
            "ok": True,
            "schema_version": RUN_SCHEMA,
            "spec": {"genre": "platformer"},
            "marker": "goal:1",
            "file_names": [],
            "stubbed": [],
            "actor_id": kwargs.get("actor_id"),
            "tenant_id": kwargs.get("tenant_id"),
        }

    monkeypatch.setattr("skeleton.forge.game_builder.build_playable_game", fake_build)
    state = get_state()
    saved = getattr(state, "forge", None)
    state.forge = Forge()
    app = FastAPI()
    app.add_exception_handler(SkeletonError, skeleton_error_handler)
    app.include_router(router, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as api:
        yield api
    state.forge = saved


def test_http_build_returns_202_and_polls(client):
    headers = {"x-gf-seal": mint_seal("golden", secret=SECRET), "x-skeleton-tenant": "studio"}
    rejected = client.post("/api/v1/game/build", json={"brief": {"title": "X", "extra": 1}}, headers=headers)
    assert rejected.status_code == 422
    accepted = client.post(
        "/api/v1/game/build",
        json={"brief": {"title": "Ledges", "genre": "platformer"}, "playtest": "off"},
        headers=headers,
    )
    assert accepted.status_code == 202, accepted.text
    body = accepted.json()
    assert body["status"] == "queued"
    assert body["status_ref"].endswith(body["execution_id"])
    from skeleton.forge.game_build_queue import drain

    deadline = time.time() + 5
    view = execution_view(body["execution_id"])
    while time.time() < deadline and view["status"] not in {"succeeded", "failed", "cancelled"}:
        drain()
        time.sleep(0.02)
        view = execution_view(body["execution_id"])
    assert view["status"] == "succeeded", view
    assert view["result"]["actor_id"] == "golden"
    assert view["result"]["tenant_id"] == "studio"
    from skeleton.forge.game_build_queue import _fallback_queue

    assert _fallback_queue()._jobs[body["job_id"]]["timeout_s"] == 120.0
    capped = client.post(
        "/api/v1/game/build",
        json={"brief": "A small platformer", "playtest": "off", "deadline_s": 15},
        headers=headers,
    )
    assert capped.status_code == 202, capped.text
    assert _fallback_queue()._jobs[capped.json()["job_id"]]["timeout_s"] == 15.0
    missing = client.get("/api/v1/game/build/missing-build", headers=headers)
    assert missing.status_code == 404
