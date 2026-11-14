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
