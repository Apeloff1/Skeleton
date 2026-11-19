"""Workspace game-operation integration and failure/recovery invariants.

SQLite, HTTP framing, leases, source manifests and ZIP bytes are genuine. The
trusted model/build operation is replaced by an explicitly counted fixture;
these tests make no native-engine or model-quality qualification claim. The
separate browser operator executes the real GGUF and Godot path.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import http.client
import io
import json
from pathlib import Path
import shutil
import sqlite3
import threading
import time
import zipfile

import pytest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import _model_tokenizer_digest
from skeleton.app.offline_game_builder import GameBuildRejected, LocalGameBuilder
from skeleton.app.offline_http import LocalOnlyHTTPServer, OfflineHTTPApplication
from skeleton.cortex.transformer import TinyTransformer
from skeleton.forge.game_design_spec import compile_brief
from skeleton.forge.projector import write_project


BRIEF = "A small top-down shooter. Fantasy: an original signal garden. Theme: moss. Difficulty: easy."
TOKEN = "integration-fixture-only-" + "x" * 48


def model(seed: int = 41):
    backend = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "local", " "),
        dim=8, ctx=2048, seed=seed, n_heads=2, n_layers=2, d_ff=16,
    )))
    # This explicitly labelled test adapter never runs model inference. Keep
    # its real native identity/tokenizer/readiness machinery for store scope.
    backend.model_id = backend._admitted_model_id = "jeeves"
    return backend


class CountedPipeline:
    def __init__(self):
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.mutate = None
        self.failure = None

    def __call__(self, backend, brief, out, **options):
        self.calls.append({"model_digest": backend.model_digest, "brief": brief})
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("fixture was not released")
        if self.failure is not None:
            raise self.failure
        for state in ("planning", "building", "verifying"):
            if options.get("on_stage"):
                options["on_stage"](state)
        spec = compile_brief(brief)
        files = {
            "project.godot": 'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
            "main.tscn": '[gd_scene format=3]\n[node name="Fixture" type="Node2D"]\n',
            "data/design_spec.json": json.dumps(spec),
            "PLAY.md": "Explicit fixture source; no engine or model was exercised.\n",
        }
        manifest = write_project(out, files, meta={"spec_id": spec["spec_id"], "fixture": True})
        report = {
            "schema": "skeleton.jeeves.local-game-build.v1", "ok": True,
            "planning": {"status": "accepted", "model_digest": backend.model_digest,
                         "runtime_digest": backend.runtime_digest, "attempts": [],
                         "fixture_only": True},
            "build": {"schema_version": "skeleton.game_builder_run.v1", "ok": True,
                      "spec": spec, "file_names": list(files), "project": manifest,
                      "playtest": {"status": "passed", "passed": True},
                      "interactive": {"native_boot_verified": True, "input_journey_verified": True,
                                      "fixture_only": True, "controls": {"restart": "R"}}},
        }
        if self.mutate:
            self.mutate(report, Path(out))
        return report


@pytest.fixture
def pipeline(monkeypatch):
    fixture = CountedPipeline()
    monkeypatch.setattr("skeleton.app.offline_game_builder.run_local_game_build", fixture)
    # Readiness resolution is a fixture dependency; the fake executable is
    # never run because only the explicitly counted trusted pipeline is used.
    monkeypatch.setattr("skeleton.forge.playtest.resolve_binary", lambda *args, **kwargs: (
        "/trusted-fixture/godot", "fixture-only", False))
    yield fixture
    fixture.release.set()


def terminal(manager, identifier: str, *, seconds: float = 5):
    stop = time.monotonic() + seconds
    while time.monotonic() < stop:
        job = manager.get(identifier)
        if job["terminal"]:
            return job
        time.sleep(0.01)
    raise AssertionError("fixture game operation did not reach a terminal state")


@contextmanager
def server(backend, database: Path):
    application = OfflineHTTPApplication(backend, database, token=TOKEN)
    httpd = LocalOnlyHTTPServer(application)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield application, httpd.server_port
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
        httpd.server_close()
        application.close()


def http_request(port, method, path, body=None, *, authenticated=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Authorization": "Bearer " + TOKEN} if authenticated else {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def mutate_row(database, identifier, **values):
    with sqlite3.connect(database) as connection:
        changed = connection.execute(
            "UPDATE offline_game_builds SET " + ",".join(key + "=?" for key in values)
            + " WHERE request_id=?", (*values.values(), identifier)).rowcount
        assert changed == 1


def test_authenticated_http_job_archive_and_replay_survive_model_unavailability(tmp_path, pipeline, monkeypatch):
    backend = model()
    with server(backend, tmp_path / "workspace.sqlite3") as (app, port):
        for method, body in (("GET", None), ("POST", {"request_id": "denied", "brief": BRIEF})):
            assert http_request(port, method, "/v1/game-builds", body, authenticated=False)[0] == 401
        assert not pipeline.calls
        assert http_request(port, "POST", "/v1/game-builds", {
            "request_id": "job-http", "brief": BRIEF, "out": "/private/path"})[0] == 400
        assert not pipeline.calls
        status, _, admitted = http_request(port, "POST", "/v1/game-builds", {"request_id": "job-http", "brief": BRIEF})
        assert status == 202 and json.loads(admitted)["request_id"] == "job-http"
        job = terminal(app._game_builder, "job-http")
        assert job["state"] == "complete" and len(pipeline.calls) == 1
        status, headers, archive = http_request(port, "GET", "/v1/game-builds/job-http/archive")
        assert status == 200 and headers["Content-Type"] == "application/zip"
        assert "attachment;" in headers["Content-Disposition"]
        assert len(archive) == job["archive"]["bytes"]
        assert sha256(archive).hexdigest() == job["archive"]["sha256"]
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            assert bundle.testzip() is None
            assert "project.godot" in bundle.namelist()
            assert json.loads(bundle.read("FORGE_MANIFEST.json"))["root"] == "project"
        monkeypatch.setattr(backend, "check_readiness", lambda: (_ for _ in ()).throw(RuntimeError("private model path")))
        assert http_request(port, "POST", "/v1/game-builds", {"request_id": "job-http", "brief": BRIEF})[0] == 202
        assert http_request(port, "POST", "/v1/game-builds", {"request_id": "job-http", "brief": BRIEF + " changed"})[0] == 409
        assert http_request(port, "POST", "/v1/game-builds", {"request_id": "new-unavailable", "brief": BRIEF})[0] == 503
        assert http_request(port, "GET", "/v1/game-builds/job-http/archive")[2] == archive
        status, _, listing = http_request(port, "GET", "/v1/game-builds")
        assert status == 200 and len(json.loads(listing)["jobs"]) == 1
        assert len(pipeline.calls) == 1


def test_same_sqlite_preserves_chat_and_scopes_foreign_model_records(tmp_path, pipeline):
    database = tmp_path / "workspace.sqlite3"
    first = model()
    with OfflineChatStore(database) as chat:
        sid = chat.create(first.model_digest, _model_tokenizer_digest(first))
    manager = LocalGameBuilder(first, database)
    try:
        manager.submit("scope-case", BRIEF)
        assert terminal(manager, "scope-case")["state"] == "complete"
    finally:
        manager.close()
    with OfflineChatStore(database) as chat:
        assert chat.load(sid, first.model_digest, _model_tokenizer_digest(first)).revision == 0
        assert chat._db.execute("SELECT count(*) FROM offline_game_builds").fetchone()[0] == 1
    foreign = LocalGameBuilder(model(83), database)
    try:
        assert foreign.list_jobs() == []
        for read in (foreign.get, foreign.archive):
            with pytest.raises(GameBuildRejected) as denied:
                read("scope-case")
            assert denied.value.status == 404
        assert len(pipeline.calls) == 1
    finally:
        foreign.close()


def test_peer_startup_cannot_fail_a_live_worker_or_admit_overlapping_build(tmp_path, pipeline):
    pipeline.release.clear()
    database = tmp_path / "workspace.sqlite3"
    backend = model()
    first = LocalGameBuilder(backend, database)
    second = None
    try:
        first.submit("live-peer", BRIEF)
        assert pipeline.entered.wait(3)
        second = LocalGameBuilder(backend, database)
        assert second.get("live-peer")["state"] in {"queued", "planning", "building", "verifying"}
        assert second.submit("live-peer", BRIEF)["terminal"] is False
        with pytest.raises(GameBuildRejected) as busy:
            second.submit("overlap-denied", BRIEF)
        assert busy.value.status in {423, 503}
        pipeline.release.set()
        assert terminal(first, "live-peer")["state"] == "complete"
        assert second.get("live-peer")["state"] == "complete" and len(pipeline.calls) == 1
    finally:
        pipeline.release.set()
        first.close()
        if second:
            second.close()


@pytest.mark.parametrize("published", [False, True])
def test_restart_resolves_interruption_without_rerunning_the_model(tmp_path, pipeline, published):
    database = tmp_path / "workspace.sqlite3"
    backend = model()
    manager = LocalGameBuilder(backend, database)
    manager.submit("restart-case", BRIEF)
    original = terminal(manager, "restart-case")
    assert original["state"] == "complete"
    archive = manager.archive("restart-case")
    bundle = manager.artifact_root / manager._row("restart-case")["artifact_id"]
    manager.close()
    if published:
        mutate_row(database, "restart-case", state="verifying", stage="publishing")
    else:
        shutil.rmtree(bundle)
        mutate_row(database, "restart-case", state="planning", stage="planning",
                   result_json=None, archive_sha256=None, archive_bytes=None, file_count=None, receipt_sha256=None)
    reopened = LocalGameBuilder(backend, database)
    try:
        recovered = reopened.get("restart-case")
        assert recovered["terminal"] is True
        if published:
            assert recovered["state"] == "complete" and reopened.archive("restart-case") == archive
        else:
            assert recovered["state"] == "failed" and recovered["error"]["code"] == "interrupted_build"
            assert recovered["archive"] is None
        assert reopened.submit("restart-case", BRIEF)["state"] == recovered["state"]
        assert len(pipeline.calls) == 1
    finally:
        reopened.close()


@pytest.mark.parametrize("tamper", ["bytes", "receipt", "symlink", "hardlink"])
def test_archive_tamper_never_exports_bytes_or_reexecutes_pipeline(tmp_path, pipeline, tamper):
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("integrity-case", BRIEF)
        assert terminal(manager, "integrity-case")["state"] == "complete"
        bundle = manager.artifact_root / manager._row("integrity-case")["artifact_id"]
        archive = bundle / "project.zip"
        target = tmp_path / "private-original.txt"
        target.write_bytes(b"private original never exported")
        target.chmod(0o600)
        if tamper == "bytes":
            archive.write_bytes(archive.read_bytes() + b"changed")
        elif tamper == "receipt":
            (bundle / "receipt.json").write_bytes(b'{"changed":true}')
        elif tamper == "symlink":
            archive.unlink()
            archive.symlink_to(target)
        else:
            archive.unlink()
            archive.hardlink_to(target)
        with pytest.raises(GameBuildRejected) as denied:
            manager.archive("integrity-case")
        assert denied.value.status == 409
        assert target.read_bytes() == b"private original never exported"
        assert len(pipeline.calls) == 1
    finally:
        manager.close()


@pytest.mark.parametrize("missing_proof", ["native_boot_verified", "input_journey_verified", "model_digest"])
def test_incomplete_or_foreign_execution_proof_cannot_publish_source(tmp_path, pipeline, missing_proof):
    def mutate(report, _out):
        if missing_proof == "model_digest":
            report["planning"]["model_digest"] = "f" * 64
        else:
            report["build"]["interactive"][missing_proof] = False
    pipeline.mutate = mutate
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("unqualified", BRIEF)
        job = terminal(manager, "unqualified")
        assert job["state"] == "failed" and job["archive"] is None
        with pytest.raises(GameBuildRejected) as denied:
            manager.archive("unqualified")
        assert denied.value.status == 409 and len(pipeline.calls) == 1
    finally:
        manager.close()


def test_public_failure_and_archive_metadata_redact_runtime_paths(tmp_path, pipeline):
    sentinel = "/private/operator/model-and-runtime-path"
    def add_private_diagnostics(report, _out):
        report["build"]["project"]["root"] = sentinel
        report["build"]["playtest"].update(binary=sentinel, steps=[{"log_tail": sentinel}])
    pipeline.mutate = add_private_diagnostics
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("redacted-success", BRIEF)
        job = terminal(manager, "redacted-success")
        assert job["state"] == "complete" and sentinel not in json.dumps(job)
        with zipfile.ZipFile(io.BytesIO(manager.archive("redacted-success"))) as archive:
            assert sentinel.encode() not in archive.read("JEEVES_BUILD.json")
            assert json.loads(archive.read("FORGE_MANIFEST.json"))["root"] == "project"
        pipeline.failure = RuntimeError(sentinel + " secret stderr")
        manager.submit("redacted-failure", BRIEF)
        failed = terminal(manager, "redacted-failure")
        assert failed["state"] == "failed" and sentinel not in json.dumps(failed)
    finally:
        manager.close()


def test_source_manifest_path_escape_is_rejected_before_archive_publication(tmp_path, pipeline):
    def malicious_manifest(_report, project):
        path = project / "FORGE_MANIFEST.json"
        manifest = json.loads(path.read_text())
        manifest["files"].append("../private.txt")
        manifest["sha256"]["../private.txt"] = "0" * 64
        path.write_text(json.dumps(manifest))
    pipeline.mutate = malicious_manifest
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("escaped-member", BRIEF)
        job = terminal(manager, "escaped-member")
        assert job["state"] == "failed" and job["archive"] is None
        assert not list(manager.artifact_root.glob("game-*"))
    finally:
        manager.close()


@pytest.mark.parametrize(("method", "path", "body", "expected"), [
    ("DELETE", "/v1/game-builds", None, 405),
    ("POST", "/v1/game-builds/unknown/archive", {}, 405),
    ("GET", "/v1/game-builds/", None, 404),
    ("GET", "/v1/game-builds/job/not-an-archive", None, 404),
    ("GET", "/v1/game-builds/job/archive/extra", None, 404),
    ("GET", "/v1/game-builds/bad%20id", None, 400),
    ("POST", "/v1/game-builds", {"request_id": "missing-brief"}, 400),
    ("POST", "/v1/game-builds", {"request_id": "bad id", "brief": BRIEF}, 400),
    ("POST", "/v1/game-builds", {"request_id": "blank", "brief": "  "}, 400),
    ("POST", "/v1/game-builds", {"request_id": "null", "brief": None}, 400),
    ("POST", "/v1/game-builds", {"request_id": "boolean", "brief": True}, 400),
    ("POST", "/v1/game-builds", {"request_id": "object", "brief": {"genre": "shooter"}}, 400),
    ("POST", "/v1/game-builds", {"request_id": "long", "brief": "x" * 4001}, 400),
    ("POST", "/v1/game-builds", {"request_id": "utf8", "brief": "界" * 1334}, 400),
    ("POST", "/v1/game-builds", {"request_id": "surrogate", "brief": "\ud800"}, 400),
    ("POST", "/v1/game-builds", {"request_id": "unexpected", "brief": BRIEF, "out": "/private/path"}, 400),
])
def test_invalid_http_game_build_envelopes_do_not_initialize_store(
        tmp_path, pipeline, method, path, body, expected):
    database = tmp_path / "workspace.sqlite3"
    with server(model(), database) as (app, port):
        assert app._game_builder is None
        assert http_request(port, method, path, body)[0] == expected
        assert app._game_builder is None
        assert not pipeline.calls
        with sqlite3.connect(database) as connection:
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='offline_game_builds'"
            ).fetchone() is None
        status, _, listing = http_request(port, "GET", "/v1/game-builds")
        assert status == 200 and json.loads(listing)["jobs"] == []
        assert app._game_builder is not None
        assert not pipeline.calls


@pytest.mark.parametrize("brief", [None, True, "", " " * 4000, "x" * 4001, "界" * 1334, "\ud800"])
def test_pure_game_build_admission_rejects_invalid_briefs(brief):
    from skeleton.app.offline_game_builder import validate_game_build_request
    with pytest.raises(GameBuildRejected) as denied:
        validate_game_build_request("valid-id", brief)
    assert denied.value.status == 400
    assert denied.value.code == "invalid_game_brief"


def test_pure_game_build_admission_preserves_request_identity():
    from skeleton.app.offline_game_builder import validate_game_build_request
    assert validate_game_build_request("local-build_17", BRIEF) == "local-build_17"


def test_closed_game_builder_refuses_public_operations_with_typed_errors(tmp_path, pipeline):
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    manager.close()
    manager.close()
    assert manager.availability()["ready"] is False
    for operation in (
        lambda: manager.submit("after-close", BRIEF),
        lambda: manager.get("after-close"),
        manager.list_jobs,
        lambda: manager.archive("after-close"),
    ):
        with pytest.raises(GameBuildRejected) as denied:
            operation()
        assert denied.value.status == 503
        assert denied.value.code == "local_service_shutting_down"
    assert not pipeline.calls


def test_readiness_callback_cannot_submit_recursively(tmp_path, pipeline, monkeypatch):
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    original = manager.availability
    def reenter():
        with pytest.raises(GameBuildRejected) as denied:
            manager.submit("recursive", BRIEF)
        assert denied.value.status == 423
        return original()
    monkeypatch.setattr(manager, "availability", reenter)
    try:
        manager.submit("outer", BRIEF)
        assert terminal(manager, "outer")["state"] == "complete"
        assert len(pipeline.calls) == 1
        assert [job["request_id"] for job in manager.list_jobs()] == ["outer"]
    finally:
        manager.close()


def test_readiness_callback_shutdown_cannot_start_worker(tmp_path, pipeline, monkeypatch):
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    def shutdown():
        manager.close()
        return {"ready": True, "code": "ready"}
    monkeypatch.setattr(manager, "availability", shutdown)
    try:
        with pytest.raises(GameBuildRejected) as denied:
            manager.submit("stale-readiness", BRIEF)
        assert denied.value.code == "local_service_shutting_down"
        assert manager._worker is None
        assert not pipeline.calls
    finally:
        manager.close()


def test_worker_reentrant_close_preserves_journal_until_external_drain(tmp_path, pipeline):
    database = tmp_path / "workspace.sqlite3"
    backend = model()
    manager = LocalGameBuilder(backend, database)
    observed = []
    pipeline.release.clear()
    def request_close(_report, _project):
        try:
            manager.close()
        except GameBuildRejected as denied:
            observed.append((denied.code, manager._closed))
    pipeline.mutate = request_close
    try:
        manager.submit("worker-close", BRIEF)
        assert pipeline.entered.wait(3)
        pipeline.release.set()
        worker = manager._worker
        assert worker is not None
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert observed == [("game_worker_draining", False)]
        assert manager._closed is False
    finally:
        pipeline.release.set()
        manager.close()
    reopened = LocalGameBuilder(backend, database)
    try:
        assert reopened.get("worker-close")["state"] == "failed"
        assert len(pipeline.calls) == 1
    finally:
        reopened.close()


def test_worker_start_failure_does_not_poison_future_admission(tmp_path, pipeline, monkeypatch):
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    def unavailable(_worker):
        raise RuntimeError("fixture thread startup failure")
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(threading.Thread, "start", unavailable)
            with pytest.raises(GameBuildRejected) as denied:
                manager.submit("failed-start", BRIEF)
        assert denied.value.code == "game_admission_unavailable"
        assert manager._worker is None
        assert manager.list_jobs() == []
        manager.submit("valid-retry", BRIEF)
        assert terminal(manager, "valid-retry")["state"] == "complete"
        assert len(pipeline.calls) == 1
    finally:
        manager.close()


@pytest.mark.parametrize("field,value", [
    ("result_json", "x" * (262144 + 1)),
    ("result_json", b'{"schema":"wrong"}'),
    ("brief", "x" * 4001),
    ("request_digest", "not-a-digest"),
    ("receipt_sha256", "f" * 65),
    ("archive_bytes", 16 * 1024 * 1024 + 1),
    ("file_count", 0),
    ("artifact_id", "game-" + "f" * 64),
])
def test_corrupt_saved_build_does_not_become_absent_or_replay(tmp_path, pipeline, field, value):
    database = tmp_path / "workspace.sqlite3"
    manager = LocalGameBuilder(model(), database)
    try:
        manager.submit("bounded-row", BRIEF)
        assert terminal(manager, "bounded-row")["state"] == "complete"
        mutate_row(database, "bounded-row", **{field: value})
        for operation in (
            lambda: manager.get("bounded-row"),
            manager.list_jobs,
            lambda: manager.submit("bounded-row", BRIEF),
            lambda: manager.archive("bounded-row"),
        ):
            with pytest.raises(GameBuildRejected) as denied:
                operation()
            assert denied.value.status == 503
            assert denied.value.code == "invalid_build_record"
        assert len(pipeline.calls) == 1
    finally:
        manager.close()


def test_archive_readback_rejects_journal_change_after_verification(tmp_path, pipeline, monkeypatch):
    database = tmp_path / "workspace.sqlite3"
    manager = LocalGameBuilder(model(), database)
    try:
        manager.submit("archive-race", BRIEF)
        assert terminal(manager, "archive-race")["state"] == "complete"
        original = manager._verify
        def changed(row):
            payload = original(row)
            mutate_row(database, "archive-race", updated_at=row["updated_at"] + 1)
            return payload
        monkeypatch.setattr(manager, "_verify", changed)
        with pytest.raises(GameBuildRejected) as denied:
            manager.archive("archive-race")
        assert denied.value.code == "game_archive_changed"
        assert len(pipeline.calls) == 1
    finally:
        manager.close()


def test_corrupt_interrupted_row_blocks_recovery_without_reexecution(tmp_path, pipeline):
    database = tmp_path / "workspace.sqlite3"
    backend = model()
    manager = LocalGameBuilder(backend, database)
    try:
        manager.submit("interrupted-corrupt", BRIEF)
        assert terminal(manager, "interrupted-corrupt")["state"] == "complete"
    finally:
        manager.close()
    mutate_row(database, "interrupted-corrupt", state="verifying", stage="publishing",
               result_json="x" * (262144 + 1))
    with pytest.raises(GameBuildRejected) as denied:
        LocalGameBuilder(backend, database)
    assert denied.value.code == "invalid_build_record"
    assert len(pipeline.calls) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT state FROM offline_game_builds WHERE request_id=?", ("interrupted-corrupt",)
        ).fetchone() == ("verifying",)


def test_recovery_refuses_changed_record_between_proof_and_writer_reservation(tmp_path, pipeline, monkeypatch):
    database = tmp_path / "workspace.sqlite3"
    backend = model()
    manager = LocalGameBuilder(backend, database)
    try:
        manager.submit("recovery-race", BRIEF)
        assert terminal(manager, "recovery-race")["state"] == "complete"
    finally:
        manager.close()
    mutate_row(database, "recovery-race", state="verifying", stage="publishing")
    original = LocalGameBuilder._verify
    def mutate_after_proof(owner, row):
        raw = original(owner, row)
        mutate_row(database, "recovery-race", updated_at=row["updated_at"] + 1)
        return raw
    with monkeypatch.context() as scoped:
        scoped.setattr(LocalGameBuilder, "_verify", mutate_after_proof)
        with pytest.raises(GameBuildRejected) as denied:
            LocalGameBuilder(backend, database)
        assert denied.value.code == "invalid_build_record"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT state,stage FROM offline_game_builds WHERE request_id=?", ("recovery-race",)
        ).fetchone() == ("verifying", "publishing")
    reopened = LocalGameBuilder(backend, database)
    try:
        assert reopened.get("recovery-race")["state"] == "complete"
        assert len(pipeline.calls) == 1
    finally:
        reopened.close()


def test_publication_retry_cannot_adopt_a_changed_pending_journal(tmp_path, pipeline, monkeypatch):
    database = tmp_path / "workspace.sqlite3"
    backend = model()
    manager = LocalGameBuilder(backend, database)
    original = manager._verify
    observed = []
    def changed(row):
        raw = original(row)
        observed.append(row["updated_at"])
        if len(observed) == 1:
            mutate_row(database, "publish-race", updated_at=row["updated_at"] + 1)
        return raw
    monkeypatch.setattr(manager, "_verify", changed)
    try:
        manager.submit("publish-race", BRIEF)
        worker = manager._worker
        assert worker is not None
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert len(observed) == 2 and observed[0] == observed[1]
        assert manager.get("publish-race")["state"] == "verifying"
        with pytest.raises(GameBuildRejected) as denied:
            manager.archive("publish-race")
        assert denied.value.code == "game_archive_not_ready"
    finally:
        manager.close()
    reopened = LocalGameBuilder(backend, database)
    try:
        assert reopened.get("publish-race")["state"] == "complete"
        assert len(pipeline.calls) == 1
    finally:
        reopened.close()


def test_public_planning_projection_redacts_backend_diagnostics_at_every_attempt(tmp_path, pipeline):
    sentinel = "/private/operator/planning-diagnostics"
    def mutate(report, _out):
        report["planning"].update(
            raw_output=sentinel, command=sentinel,
            attempts=[
                {"attempt": 1, "elapsed_seconds": 0.1, "output_tokens": 42,
                 "response_sha256": "a" * 64, "execution_receipt_sha256": "b" * 64,
                 "violations": ["invalid:gameplay.theme", sentinel], "log": sentinel},
                {"attempt": 2, "elapsed_seconds": 0.2, "output_tokens": 43,
                 "response_sha256": "c" * 64, "execution_receipt_sha256": "d" * 64,
                 "violations": [], "raw_prompt": sentinel},
            ],
        )
        report["reason"] = sentinel
    pipeline.mutate = mutate
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("private-planning", BRIEF)
        job = terminal(manager, "private-planning")
        assert job["state"] == "complete"
        assert sentinel not in json.dumps(job)
        assert job["result"]["planning"]["attempts"][0]["violations"] == [
            "invalid:gameplay.theme", "unclassified_rejection"]
        assert job["result"]["planning"]["attempts"][1]["execution_receipt_sha256"] == "d" * 64
        with zipfile.ZipFile(io.BytesIO(manager.archive("private-planning"))) as archive:
            assert sentinel.encode() not in archive.read("JEEVES_BUILD.json")
        assert len(pipeline.calls) == 1
    finally:
        manager.close()


@pytest.mark.parametrize("damage", [
    {"status": "foreign-status"},
    {"attempts": [{}, {}, {}]},
    {"network_provider_used": True},
    {"quality_qualified": True},
    {"generated_source_admitted": 0},
    {"runtime_digest": "not-a-digest"},
    {"instruction_policy": "foreign-policy"},
])
def test_invalid_public_planning_receipt_never_publishes_source(tmp_path, pipeline, damage):
    pipeline.mutate = lambda report, _out: report["planning"].update(damage)
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("invalid-planning", BRIEF)
        assert terminal(manager, "invalid-planning")["state"] == "failed"
        with pytest.raises(GameBuildRejected) as denied:
            manager.archive("invalid-planning")
        assert denied.value.status == 409
        assert len(pipeline.calls) == 1
    finally:
        manager.close()


@pytest.mark.parametrize("damage", ["reported_digest", "reported_names", "reported_meta",
                                    "source_design", "foreign_design", "source_meta"])
def test_packaged_game_source_must_agree_with_accepted_design_and_report(tmp_path, pipeline, damage):
    from skeleton.forge.source_manifest import source_manifest
    def mutate(report, project):
        build = report["build"]
        if damage == "reported_digest":
            build["project"]["source_sha256"] = "f" * 64
        elif damage == "reported_names":
            build["file_names"].remove("PLAY.md")
        elif damage == "reported_meta":
            build["project"]["meta"]["spec_id"] = "a" * 64
        else:
            path = project / "FORGE_MANIFEST.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if damage == "source_meta":
                manifest["meta"]["genre"] = "platformer"
            else:
                spec = compile_brief("A small platformer.") if damage == "foreign_design" else dict(build["spec"])
                if damage == "source_design":
                    spec["title"] = "Unexpected design"
                (project / "data/design_spec.json").write_text(json.dumps(spec), encoding="utf-8")
                files = {name: (project / name).read_bytes().decode("utf-8") for name in manifest["files"]}
                actual = source_manifest(files)
                manifest["sha256"] = actual["files"]
                manifest["source_sha256"] = actual["sha256"]
                build["project"]["sha256"] = actual["files"]
                build["project"]["source_sha256"] = actual["sha256"]
                if damage == "foreign_design":
                    build["spec"] = spec
                    build["project"]["meta"]["spec_id"] = spec["spec_id"]
                    manifest["meta"]["spec_id"] = spec["spec_id"]
            path.write_text(json.dumps(manifest), encoding="utf-8")
    pipeline.mutate = mutate
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("mismatch", BRIEF)
        job = terminal(manager, "mismatch")
        assert job["state"] == "failed" and job["archive"] is None
        assert not list(manager.artifact_root.glob("game-*"))
        assert len(pipeline.calls) == 1
    finally:
        manager.close()


def test_archive_manifest_redacts_unadmitted_project_metadata(tmp_path, pipeline):
    sentinel = "/private/local/project-diagnostics"
    def mutate(report, project):
        path = project / "FORGE_MANIFEST.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["private_root"] = sentinel
        manifest["meta"]["debug"] = {"path": sentinel}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        report["build"]["project"]["meta"]["debug"] = sentinel
    pipeline.mutate = mutate
    manager = LocalGameBuilder(model(), tmp_path / "workspace.sqlite3")
    try:
        manager.submit("safe-meta", BRIEF)
        assert terminal(manager, "safe-meta")["state"] == "complete"
        with zipfile.ZipFile(io.BytesIO(manager.archive("safe-meta"))) as archive:
            manifest = json.loads(archive.read("FORGE_MANIFEST.json"))
            assert set(manifest) == {"root", "files", "count", "sha256", "source_sha256", "meta"}
            assert set(manifest["meta"]) == {"spec_id"}
            assert sentinel not in json.dumps(manifest)
    finally:
        manager.close()
