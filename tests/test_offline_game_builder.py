"""Same-file local build jobs and source archive custody, without model doubles
being represented as real trained-model or native Godot qualification.
"""
from __future__ import annotations

import io
import asyncio
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import zipfile

import pytest

from skeleton.app import offline_game_builder as builder
from skeleton.forge.game_design_spec import compile_brief
from skeleton.forge.projector import write_project


class Backend:
    model_id = "jeeves"
    model_digest = "a" * 64
    tokenizer_digest = "b" * 64
    runtime_digest = "c" * 64
    protocol_capabilities = ("structured-output",)

    def check_readiness(self):
        return None

    def generation_limits(self):
        return {"max_output_tokens": 1024, "context_window": 4096}

    def infer(self, *_args):
        raise AssertionError("this source test never runs model inference")


@pytest.fixture(autouse=True)
def isolate_source_backend_tokenizer_admission(monkeypatch):
    # Production keeps its closed NativeRuntimeLocalModel/LlamaCppModel
    # boundary. Only this explicit source test double substitutes identity.
    from skeleton.app import local_ai
    original = local_ai._model_tokenizer_digest
    monkeypatch.setattr(local_ai, "_model_tokenizer_digest",
        lambda backend: backend.tokenizer_digest if isinstance(backend, Backend) else original(backend))


def operation(backend, brief, out, **kwargs):
    for stage in ("planning", "building", "verifying"):
        kwargs["on_stage"](stage)
    spec = compile_brief(brief)
    manifest = write_project(out, {"project.godot": "config_version=5\n",
        "scripts/main.gd": "extends Node\n"}, meta={"spec_id": spec["spec_id"]})
    return {"schema": builder.SCHEMA, "ok": True,
        "planning": {"status": "accepted", "model_digest": backend.model_digest,
                     "runtime_digest": backend.runtime_digest, "attempts": []},
        "build": {"ok": True, "schema_version": "skeleton.game_builder_run.v1", "spec": spec,
                  "project": manifest, "file_names": manifest["files"],
                  "playtest": {"passed": True, "status": "passed", "steps": [str(out)]},
                  "interactive": {"native_boot_verified": True, "input_journey_verified": True,
                                  "controls": {"movement": "WASD"}, "receipt": {"phase": "won"}}},
        "elapsed_seconds": 0.01}


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr("skeleton.forge.playtest.resolve_binary", lambda: ("/host/godot", "fixture", False))
    monkeypatch.setattr(builder, "run_local_game_build", operation)
    value = builder.LocalGameBuilder(Backend(), tmp_path / "chat.sqlite3")
    yield value
    value.close()


def settled(manager, rid="build_one"):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = manager.get(rid)
        if job["terminal"]:
            return job
        time.sleep(0.01)
    raise AssertionError(manager.get(rid))


def test_durable_same_file_job_produces_safe_bounded_archive_and_controls(manager):
    job = manager.submit("build_one", "A small platformer. Theme: frost.")
    assert job["state"] in builder.JOB_STATES
    job = settled(manager)
    assert job["state"] == "complete" and job["terminal"]
    assert job["result"]["planning"]["status"] == "accepted"
    assert job["result"]["build"]["interactive"]["native_boot_verified"] is True
    assert job["result"]["build"]["interactive"]["controls"] == {"movement": "WASD"}
    assert str(manager.artifact_root) not in json.dumps(job)
    payload = manager.archive("build_one")
    assert len(payload) == job["archive"]["bytes"] <= manager.limits()["archive_bytes"]
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert len(archive.infolist()) == job["archive"]["file_count"]
        manifest = json.loads(archive.read("FORGE_MANIFEST.json"))
        assert manifest["root"] == "project"
        for item in archive.infolist():
            assert str(manager.artifact_root).encode() not in archive.read(item)
    assert manager._store._db.execute("SELECT COUNT(*) FROM offline_game_builds").fetchone() == (1,)
    assert not manager.database.with_name("game-builds.sqlite3").exists()


def test_exact_request_replay_never_repeats_model_even_when_readiness_is_lost(manager, monkeypatch):
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return operation(*args, **kwargs)
    monkeypatch.setattr(builder, "run_local_game_build", counted)
    brief = "A small platformer."
    manager.submit("build_one", brief)
    original = settled(manager)
    monkeypatch.setattr(manager.backend, "check_readiness", lambda: (_ for _ in ()).throw(RuntimeError("private failure")))
    monkeypatch.setattr("skeleton.forge.playtest.resolve_binary", lambda: (None, "missing", False))
    assert manager.submit("build_one", brief) == original
    assert manager.archive("build_one")
    assert calls == [1]
    with pytest.raises(builder.GameBuildRejected) as error:
        manager.submit("build_one", "A different small shooter.")
    assert error.value.status == 409


def test_instruction_or_schema_drift_fences_existing_request_without_rerun(manager, monkeypatch):
    manager.submit("build_one", "A small platformer.")
    settled(manager)
    monkeypatch.setattr(builder, "SYSTEM", builder.SYSTEM + " Changed instruction identity.")
    with pytest.raises(builder.GameBuildRejected) as error:
        manager.submit("build_one", "A small platformer.")
    assert error.value.status == 409


@pytest.mark.parametrize("rid,brief", [("../escape", "A platformer."), ("valid", ""),
    ("valid", "界" * 1334), ("valid", "\ud800"), ("valid", "A shooter. Player speed: true.")],
    ids=("path", "empty", "utf8_budget", "invalid_unicode", "invalid_label"))
def test_invalid_identifier_encoding_and_brief_do_not_create_jobs(manager, rid, brief):
    with pytest.raises(builder.GameBuildRejected) as error:
        manager.submit(rid, brief)
    assert error.value.status == 400
    assert manager.list_jobs() == []


def test_native_or_structured_model_unavailability_denies_new_work(manager, monkeypatch):
    monkeypatch.setattr(manager.backend, "protocol_capabilities", ("text-generation",))
    assert not manager.availability()["ready"]
    with pytest.raises(builder.GameBuildRejected) as error:
        manager.submit("new", "A small platformer.")
    assert error.value.status == 503
    assert manager.list_jobs() == []


@pytest.mark.parametrize("damage", ["model", "runtime", "boot", "input", "build_ok", "planning"])
def test_wrong_model_or_unproved_native_result_cannot_publish(manager, monkeypatch, damage):
    def rejected(*args, **kwargs):
        report = operation(*args, **kwargs)
        if damage == "model": report["planning"]["model_digest"] = "d" * 64
        elif damage == "runtime": report["planning"]["runtime_digest"] = "d" * 64
        elif damage == "boot": report["build"]["interactive"]["native_boot_verified"] = False
        elif damage == "input": report["build"]["interactive"]["input_journey_verified"] = False
        elif damage == "build_ok": report["build"]["ok"] = False
        else: report["planning"]["status"] = "unavailable"
        return report
    monkeypatch.setattr(builder, "run_local_game_build", rejected)
    manager.submit("build_one", "A small platformer.")
    assert settled(manager)["state"] == "failed"
    assert not list(manager.artifact_root.glob("game-*"))


def test_live_peer_startup_preserves_active_job_and_denies_second_admission(manager, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return operation(*args, **kwargs)
    monkeypatch.setattr(builder, "run_local_game_build", blocked)
    manager.submit("build_one", "A small platformer.")
    assert started.wait(2)
    peer = builder.LocalGameBuilder(Backend(), manager.database)
    try:
        assert not peer.get("build_one")["terminal"]
        with pytest.raises(builder.GameBuildRejected) as error:
            peer.submit("build_two", "A small shooter.")
        assert error.value.status == 423
        assert peer.submit("build_one", "A small platformer.")["terminal"] is False
    finally:
        release.set()
        settled(manager)
        peer.close()


def test_restart_recovers_only_exact_published_bundle_and_never_calls_model(manager, monkeypatch):
    manager.submit("build_one", "A small platformer.")
    complete = settled(manager)
    manager._store._db.execute("UPDATE offline_game_builds SET state='verifying',stage='publishing' WHERE request_id='build_one'")
    monkeypatch.setattr(builder, "run_local_game_build", lambda *_a, **_k: pytest.fail("recovery must not call a model"))
    peer = builder.LocalGameBuilder(Backend(), manager.database)
    try:
        recovered = peer.get("build_one")
        assert recovered["state"] == "complete"
        assert recovered["archive"] == complete["archive"]
        assert peer.archive("build_one") == manager.archive("build_one")
    finally:
        peer.close()


def test_interrupted_unpublished_job_becomes_terminal_without_automatic_retry(manager, monkeypatch):
    manager.submit("build_one", "A small platformer.")
    settled(manager)
    manager._store._db.execute("UPDATE offline_game_builds SET state='planning',stage='planning',result_json=NULL WHERE request_id='build_one'")
    monkeypatch.setattr(builder, "run_local_game_build", lambda *_a, **_k: pytest.fail("interrupted work must not rerun"))
    peer = builder.LocalGameBuilder(Backend(), manager.database)
    try:
        assert peer.get("build_one")["state"] == "failed"
        assert peer.submit("build_one", "A small platformer.")["state"] == "failed"
    finally:
        peer.close()


@pytest.mark.parametrize("tamper", ["bytes", "symlink", "hardlink"])
def test_changed_archive_or_host_file_alias_never_exports_bytes(manager, tmp_path, tamper):
    manager.submit("build_one", "A small platformer.")
    settled(manager)
    row = manager._row("build_one")
    archive = manager.artifact_root / row["artifact_id"] / "project.zip"
    if tamper == "bytes": archive.write_bytes(b"changed")
    else:
        target = tmp_path / "foreign.zip"
        target.write_bytes(archive.read_bytes())
        archive.unlink()
        if tamper == "symlink": archive.symlink_to(target)
        else: os.link(target, archive)
    with pytest.raises(builder.GameBuildRejected) as error:
        manager.archive("build_one")
    assert error.value.code == "game_archive_changed"


def test_model_tokenizer_scope_prevents_foreign_job_or_archive_reads(manager):
    manager.submit("build_one", "A small platformer.")
    settled(manager)
    other = Backend()
    other.tokenizer_digest = "e" * 64
    peer = builder.LocalGameBuilder(other, manager.database)
    try:
        assert peer.list_jobs() == []
        with pytest.raises(builder.GameBuildRejected) as error:
            peer.archive("build_one")
        assert error.value.status == 404
    finally:
        peer.close()


def test_normal_publication_collision_settles_failed_preserving_forensic_destination(manager, monkeypatch):
    def collision(source, destination):
        destination.mkdir(mode=0o700)
        (destination / "preserve.txt").write_text("newer owner bytes")
        raise FileExistsError("private path must not escape")
    monkeypatch.setattr(builder, "publish_create_only", collision)
    manager.submit("build_one", "A small platformer.")
    job = settled(manager)
    assert job["state"] == "failed" and job["error"]["code"] == "artifact_publication_failed"
    assert next(manager.artifact_root.glob("game-*/preserve.txt")).read_text() == "newer owner bytes"


def test_private_artifact_directory_rejects_symlink_or_world_readable_roots(tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(builder.GameBuildRejected):
        builder.LocalGameBuilder(Backend(), tmp_path / "chat.sqlite3", artifact_root=link)
    target.chmod(0o755)
    with pytest.raises(builder.GameBuildRejected):
        builder.LocalGameBuilder(Backend(), tmp_path / "chat.sqlite3", artifact_root=target)


def test_close_requests_one_cooperative_stop_and_drains_worker_without_publication(manager, monkeypatch):
    entered = threading.Event()
    def stop_on_close(*args, **kwargs):
        entered.set()
        assert kwargs["cancellation"].wait(3)
        raise builder.GameBuildRejected(409, "build_interrupted", "stopped")
    monkeypatch.setattr(builder, "run_local_game_build", stop_on_close)
    manager.submit("build_one", "A small platformer.")
    assert entered.wait(2)
    manager.close()
    assert not manager._worker.is_alive()
    peer = builder.LocalGameBuilder(Backend(), manager.database)
    try:
        assert peer.get("build_one")["state"] == "failed"
    finally:
        peer.close()


def test_directory_entries_are_flushed_before_terminal_sqlite_publication(manager, monkeypatch):
    events = []
    original_flush, original_publish, original_complete = builder._fsync_directory, builder.publish_create_only, manager._complete
    def flush(path):
        events.append("root_flush" if path == manager.artifact_root else "bundle_flush")
        return original_flush(path)
    def publish(source, destination):
        events.append("publish")
        return original_publish(source, destination)
    def complete(rid):
        events.append("complete")
        return original_complete(rid)
    monkeypatch.setattr(builder, "_fsync_directory", flush)
    monkeypatch.setattr(builder, "publish_create_only", publish)
    monkeypatch.setattr(manager, "_complete", complete)
    manager.submit("build_one", "A small platformer.")
    assert settled(manager)["state"] == "complete"
    assert events.index("bundle_flush") < events.index("publish") < events.index("root_flush") < events.index("complete")


def test_retrying_close_after_drain_timeout_rechecks_worker_and_closes_authority(manager):
    class Drain:
        def __init__(self): self.joins = 0
        def join(self, timeout): self.joins += 1
        def is_alive(self): return self.joins == 1
    worker = Drain()
    manager._worker = worker
    with pytest.raises(builder.GameBuildRejected) as error:
        manager.close()
    assert error.value.code == "game_worker_draining" and not manager._closed
    manager.close()
    assert worker.joins == 2 and manager._closed


def test_planning_stop_sends_one_cancellation_and_waits_for_cleanup(tmp_path, monkeypatch):
    cancelled = threading.Event()
    planning_started = threading.Event()
    observed = []
    async def pending(*_args, **_kwargs):
        try:
            planning_started.set()
            await asyncio.sleep(60)
        finally:
            # Physical model cleanup must remain awaitable after cancellation.
            observed.append(asyncio.current_task().cancelling())
            await asyncio.sleep(0.15)
            observed.append("drained")
    monkeypatch.setattr(builder, "propose", pending)
    def cancel_running_planner():
        # Cancellation must exercise the running task's cleanup. A wall-clock
        # timer may fire during cold imports before the planner ever starts.
        planning_started.wait(timeout=5)
        cancelled.set()
    requester = threading.Thread(target=cancel_running_planner, daemon=True)
    requester.start()
    try:
        with pytest.raises(builder.GameBuildRejected) as error:
            builder.run_local_game_build(Backend(), "A small platformer.", tmp_path / "project",
                workspace_database=tmp_path / "chat.sqlite3", cancellation=cancelled)
        assert error.value.code == "build_interrupted"
    finally:
        cancelled.set()
        requester.join(timeout=5)
    assert not requester.is_alive()
    assert planning_started.is_set()
    assert observed == [1, "drained"]


def test_saved_history_has_a_transactional_admission_limit(manager, monkeypatch):
    monkeypatch.setattr(builder, "MAX_HISTORY_JOBS", 1)
    manager.submit("build_one", "A small platformer.")
    settled(manager)
    manager._worker.join(timeout=2)
    with pytest.raises(builder.GameBuildRejected) as error:
        manager.submit("build_two", "A small shooter.")
    assert error.value.status == 429 and error.value.code == "local_game_history_full"
    assert len(manager.list_jobs()) == 1
