"""2026-grade single-host local inference admission and durable replay guards.

These tests deliberately exercise a second OS process and the actual native
transformer. No remote provider, fake answer or production GGUF claim.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import time

import pytest

from skeleton.app.jeeves_local_lease import (
    LocalInferenceLease,
    LocalInferenceLeaseBusy,
    LocalInferenceLeaseUnavailable,
)
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


def native_model() -> NativeRuntimeLocalModel:
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer",
               "local", "offline", "jeeves", "computer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))


def test_independent_local_lease_owners_are_exclusive_and_reusable(tmp_path: Path):
    database = tmp_path / "native.sqlite3"
    first = LocalInferenceLease(database)
    second = LocalInferenceLease(database)
    assert first.path == second.path
    with first.hold():
        assert first.path.exists()
        assert first.path.read_bytes() == bytes((0,))
        with pytest.raises(LocalInferenceLeaseBusy):
            with second.hold():
                pytest.fail("a second local owner acquired the same GPU workspace")
        with pytest.raises(LocalInferenceLeaseBusy):
            with first.hold():
                pytest.fail("a single instance admitted concurrent inference")
    # No unlink/recreate: the same inode remains the cross-process lock anchor.
    inode = first.path.stat().st_ino
    with second.hold():
        assert first.path.stat().st_ino == inode
    assert first.path.stat().st_ino == inode


def test_lease_crash_releases_kernel_lock_to_new_process(tmp_path: Path):
    """Real subprocess dies while holding the lock; no TTL or stale PID bypass."""
    database = tmp_path / "shared.sqlite3"
    ready = tmp_path / "child-ready"
    root = str(Path(__file__).resolve().parents[1])
    child_script = "\n".join([
        "from pathlib import Path",
        "import sys",
        "import time",
        "from skeleton.app.jeeves_local_lease import LocalInferenceLease",
        "db, ready = map(Path, sys.argv[1:3])",
        "with LocalInferenceLease(db).hold():",
        "    ready.write_text('locked', encoding='ascii')",
        "    time.sleep(30)",
    ])
    env = dict(os.environ)
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.Popen(
        [sys.executable, "-c", child_script, str(database), str(ready)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env,
    )
    try:
        deadline = time.monotonic() + 8
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.read_text(encoding="ascii") == "locked", (
            "child did not prove local OS lock custody"
        )
        lease = LocalInferenceLease(database)
        with pytest.raises(LocalInferenceLeaseBusy):
            with lease.hold():
                pytest.fail("parent process bypassed live child lease")
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=8)
    # Kernel ownership must release automatically, without deleting a marker.
    with LocalInferenceLease(database).hold():
        assert ready.exists()
        assert LocalInferenceLease(database).path.read_bytes() == bytes((0,))


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are not Windows ACLs")
def test_world_readable_lease_is_rejected_without_chmod_or_truncation(tmp_path: Path):
    lease = LocalInferenceLease(tmp_path / "unsafe.sqlite3")
    lease.path.write_bytes(bytes((0,)))
    lease.path.chmod(0o644)
    try:
        with pytest.raises(LocalInferenceLeaseUnavailable):
            with lease.hold():
                pytest.fail("unsafe ownership admitted inference")
        assert lease.path.read_bytes() == bytes((0,))
        assert stat.S_IMODE(lease.path.stat().st_mode) == 0o644
    finally:
        lease.path.chmod(0o600)


def test_symlink_or_hardlinked_local_lease_is_refused(tmp_path: Path):
    target = tmp_path / "foreign"
    target.write_bytes(bytes((0,)))
    target.chmod(0o600)
    linked = LocalInferenceLease(tmp_path / "linked.sqlite3")
    os.link(target, linked.path)
    with pytest.raises(LocalInferenceLeaseUnavailable):
        with linked.hold():
            pytest.fail("hardlinked lock marker should not be trusted")
    symlinked = LocalInferenceLease(tmp_path / "symlink.sqlite3")
    try:
        symlinked.path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("host does not allow test symlinks")
    with pytest.raises(LocalInferenceLeaseUnavailable):
        with symlinked.hold():
            pytest.fail("symlinked lock marker should not be trusted")


@pytest.mark.parametrize("bytes_on_disk", [b"not-a-valid-lock", bytes((0, 0))])
def test_lease_marker_rejects_unexpected_file_content(tmp_path: Path, bytes_on_disk: bytes):
    lease = LocalInferenceLease(tmp_path / "corrupt.sqlite3")
    lease.path.write_bytes(bytes_on_disk)
    lease.path.chmod(0o600)
    with pytest.raises(LocalInferenceLeaseUnavailable):
        with lease.hold():
            pytest.fail("corrupt marker should reject inference")
    assert lease.path.read_bytes() == bytes_on_disk


def test_local_http_denies_peer_generation_and_recovers_genuine_native_turn(tmp_path: Path):
    """A rejected peer cannot consume the request ID or corrupt the transcript."""
    model = native_model()
    database = tmp_path / "real-native.sqlite3"
    first = OfflineHTTPApplication(model, database, token="t" * 64)
    second = OfflineHTTPApplication(model, database, token="t" * 64)
    request = {
        "message": "Real Jeeves answer protected from concurrent local processes",
        "request_id": "lease-native-2026",
        "max_output_tokens": 2,
    }
    try:
        status, created = first.dispatch("POST", "/v1/sessions", {})
        assert status == 201
        session_id = created["session_id"]
        path = "/v1/sessions/" + session_id + "/turn"
        with LocalInferenceLease(database).hold():
            with pytest.raises(OfflineHTTPError) as error:
                second.dispatch("POST", path, request)
            assert error.value.status == 423
            assert second._session(session_id).revision == 0
            assert second._inference_circuit.status()["recent_runtime_failures"] == 0

        # This MUST use the genuine native inference engine and commit a real
        # local runtime receipt, not a canned success response or mock callback.
        status, first_answer = first.dispatch("POST", path, request)
        assert status == 200
        assert first_answer["replayed"] is False
        assert first_answer["output_tokens"] >= 1
        assert first_answer["local_execution_receipt"]["model_digest"] == model.model_digest
        assert first_answer["revision"] == 1

        # A busy foreign process cannot prevent immutable, read-only replay.
        with LocalInferenceLease(database).hold():
            status, replay = second.dispatch("POST", path, request)
            assert status == 200
            assert replay["replayed"] is True
            assert replay["output_digest"] == first_answer["output_digest"]
            with pytest.raises(OfflineHTTPError) as blocked:
                second.dispatch("POST", path, {
                    **request, "request_id": "lease-new-native-turn-2026",
                })
            assert blocked.value.status == 423
        assert second._session(session_id).revision == 1
    finally:
        second.close()
        first.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory mode policy")
def test_unprotected_shared_lock_directory_fails_closed(tmp_path: Path):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    try:
        lease = LocalInferenceLease(shared / "victim.sqlite3")
        with pytest.raises(LocalInferenceLeaseUnavailable):
            with lease.hold():
                pytest.fail("unprotected shared directory admitted cross-process exclusion")
        assert not lease.path.exists()
    finally:
        shared.chmod(0o700)


def test_memory_database_cannot_claim_crash_safe_multi_process_exclusion():
    with pytest.raises(LocalInferenceLeaseUnavailable):
        LocalInferenceLease(":memory:")


def test_identical_peer_request_committed_during_lease_admission_replays_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Adversarial timing: the peer commits AFTER the first replay lookup."""
    from contextlib import contextmanager

    model = native_model()
    database = tmp_path / "racing.sqlite3"
    winner = OfflineHTTPApplication(model, database, token="w" * 64)
    loser = OfflineHTTPApplication(model, database, token="l" * 64)
    request = {
        "message": "Exactly one local committed model response across two owners",
        "request_id": "same-identity-race-2026",
        "max_output_tokens": 2,
    }
    try:
        status, created = winner.dispatch("POST", "/v1/sessions", {})
        assert status == 201
        sid = created["session_id"]
        path = "/v1/sessions/" + sid + "/turn"
        actual_lease = loser._inference_lease.hold
        committed = []

        @contextmanager
        def concurrent_peer_holds_generation():
            # This hook runs after the losing process looked up an absent
            # receipt, but BEFORE it acquires the cross-process lease.
            if not committed:
                status, answer = winner.dispatch("POST", path, request)
                assert status == 200
                assert answer["replayed"] is False
                committed.append(answer)
            with actual_lease():
                yield

        monkeypatch.setattr(loser._inference_lease, "hold", concurrent_peer_holds_generation)
        status, recovered = loser.dispatch("POST", path, request)
        assert status == 200 and recovered["replayed"] is True
        assert recovered["output_digest"] == committed[0]["output_digest"]
        assert recovered["local_execution_receipt"] == committed[0]["local_execution_receipt"]
        assert loser._session(sid).revision == winner._session(sid).revision == 1
        # The peer-winning genuine native generation must not change model
        # circuit health in the losing service (no duplicate execution).
        assert loser._inference_circuit.status()["recent_runtime_failures"] == 0
    finally:
        loser.close()
        winner.close()


def test_async_peer_lease_conflict_retries_same_request_after_release(tmp_path: Path):
    """The accepted async ticket fails terminally, then retries idempotently."""
    model = native_model()
    database = tmp_path / "async-peer.sqlite3"
    app = OfflineHTTPApplication(model, database, token="t" * 64)
    request = {
        "message": "A real native generation after private GPU lease contention",
        "request_id": "lease-async-retry-2026",
        "max_output_tokens": 2,
    }
    try:
        _, created = app.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        with LocalInferenceLease(database).hold():
            status, accepted = app.submit_turn(sid, request)
            assert status == 202 and accepted["request_id"] == request["request_id"]
            deadline = time.monotonic() + 8
            while True:
                result = app.turn_status(sid, request["request_id"])
                if result["terminal"] and result["finished_at"] is not None:
                    break
                assert time.monotonic() < deadline, "lease failure left async ticket active"
                time.sleep(0.01)
            assert result["state"] == "failed"
            assert result["error"] == "another local service owns the inference execution slot"
            assert result["result"] is None
            assert app._session(sid).revision == 0

        # An explicit same-content retry only, never silent automatic replay.
        status, accepted = app.submit_turn(sid, {**request, "retry": True})
        assert status == 202
        deadline = time.monotonic() + 30
        while True:
            result = app.turn_status(sid, request["request_id"])
            if result["terminal"] and result["finished_at"] is not None:
                break
            assert time.monotonic() < deadline, "recovered native execution did not finish"
            time.sleep(0.01)
        assert result["state"] == "complete", result["error"]
        assert result["result"]["replayed"] is False
        assert result["result"]["local_execution_receipt"]["model_digest"] == model.model_digest
        assert app._session(sid).revision == 1
        replay_status, replay = app.submit_turn(sid, request)
        assert replay_status == 200
        assert replay["state"] == "complete"
        assert replay["result"]["replayed"] is True or replay["result"]["output_digest"] == result["result"]["output_digest"]
    finally:
        app.close()


@pytest.mark.skipif(os.name != "posix", reason="only POSIX flock descriptors support this inheritance")
def test_native_worker_context_propagates_kernel_lease_across_asyncio_to_thread(tmp_path: Path):
    """Native inference uses asyncio.to_thread: the kernel FD must follow it."""
    import asyncio

    from skeleton.ai.runtime.inference.lease_custody import gguf_child_pass_fds

    lease = LocalInferenceLease(tmp_path / "native-task.sqlite3")
    assert gguf_child_pass_fds() == ()
    with lease.hold():
        inherited = gguf_child_pass_fds()
        assert len(inherited) == 1
        assert os.fstat(inherited[0]).st_ino == lease.path.stat().st_ino

        async def check_async_native_worker():
            # The engine creates an asyncio.Task that delegates to_thread.
            # Verify that both contexts see exactly the same locked FD.
            async def delegated():
                return await asyncio.to_thread(gguf_child_pass_fds)
            return await asyncio.create_task(delegated())

        assert asyncio.run(check_async_native_worker()) == inherited
    assert gguf_child_pass_fds() == ()


@pytest.mark.skipif(os.name != "posix", reason="only POSIX flock descriptors support this inheritance")
def test_abrupt_supervisor_death_keeps_lease_held_until_orphan_native_child_exits(tmp_path: Path):
    """Kill the lease-owning parent but not its admitted child subprocess.

    A new server must not spawn a second GGUF while a real first child lives.
    No mock and no external provider: the worker is a real separate OS process.
    """
    database = tmp_path / "orphan-native.sqlite3"
    parent_started = tmp_path / "parent-started"
    child_started = tmp_path / "child-started"
    child_finished = tmp_path / "child-finished"
    root = str(Path(__file__).resolve().parents[1])
    child_script = "\n".join([
        "from pathlib import Path",
        "import sys, time",
        "started, finished = map(Path, sys.argv[1:3])",
        "started.write_text('executing', encoding='ascii')",
        "time.sleep(2.5)",
        "finished.write_text('completed', encoding='ascii')",
    ])
    # The admitted GGUF runtime passes the same FD with Popen(close_fds=True).
    # This parent reproduces that exact kernel-level process boundary.
    parent_script = "\n".join([
        "from pathlib import Path",
        "import subprocess, sys, time",
        "from skeleton.app.jeeves_local_lease import LocalInferenceLease",
        "from skeleton.ai.runtime.inference.lease_custody import gguf_child_pass_fds",
        "db, parent_ready, child_ready, child_done = map(Path, sys.argv[1:5])",
        "child_source = sys.argv[5]",
        "with LocalInferenceLease(db).hold():",
        "    subprocess.Popen([sys.executable, '-c', child_source, str(child_ready), str(child_done)],",
        "        pass_fds=gguf_child_pass_fds(), close_fds=True,",
        "        start_new_session=True, stdin=subprocess.DEVNULL,",
        "        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)",
        "    parent_ready.write_text('spawned', encoding='ascii')",
        "    time.sleep(30)",
    ])
    env = dict(os.environ)
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_script, str(database), str(parent_started),
         str(child_started), str(child_finished), child_script],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, env=env,
    )
    try:
        deadline = time.monotonic() + 8
        while (not child_started.exists() and parent.poll() is None
               and time.monotonic() < deadline):
            time.sleep(0.02)
        assert parent_started.read_text(encoding="ascii") == "spawned"
        assert child_started.read_text(encoding="ascii") == "executing"
        assert not child_finished.exists()

        # Simulate a forced kill in which Python cannot unlock its flock.
        # The orphaned native child must retain the inherited open file
        # description and block replacement inference during its lifetime.
        parent.kill()
        parent.communicate(timeout=8)
        with pytest.raises(LocalInferenceLeaseBusy):
            with LocalInferenceLease(database).hold():
                pytest.fail("second model admitted while orphan native child still owns the lease")

        deadline = time.monotonic() + 8
        while not child_finished.exists() and time.monotonic() < deadline:
            time.sleep(0.025)
        assert child_finished.read_text(encoding="ascii") == "completed"

        # The child closes its inherited FD at exit. The OS then releases
        # the lock even though the original Python supervisor never returned.
        deadline = time.monotonic() + 5
        while True:
            try:
                with LocalInferenceLease(database).hold():
                    break
            except LocalInferenceLeaseBusy:
                assert time.monotonic() < deadline, "orphan failed to release kernel lease"
                time.sleep(0.025)
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=8)


def test_lease_inspection_is_read_only_private_and_distinguishes_busy_idle_invalid(tmp_path: Path):
    database = tmp_path / "inspected.sqlite3"
    current = LocalInferenceLease(database)
    observed = current.inspect()
    assert observed == {
        "schema": "skeleton.jeeves.local-inference-lease-status.v1",
        "state": "uninitialized",
        "single_host_only": True,
        "ownership_is_generation_proof": False,
    }
    assert not current.path.exists(), "status GET must not create a lease sidecar"
    with current.hold():
        busy = LocalInferenceLease(database).inspect()
        assert busy["state"] == "busy" and busy["ownership_is_generation_proof"] is False
        assert "pid" not in busy and "path" not in busy and "token" not in busy
    after = LocalInferenceLease(database).inspect()
    assert after["state"] == "idle"
    current.path.write_bytes(b"unsafe-marker")
    assert current.inspect()["state"] == "unavailable"


def test_authenticated_status_reports_live_lease_without_claiming_generation(tmp_path: Path):
    model = native_model()
    db = tmp_path / "actual-status.sqlite3"
    app = OfflineHTTPApplication(model, db, token="t" * 64)
    try:
        status, before = app.dispatch("GET", "/v1/status")
        assert status == 200 and before["inference_lease"]["state"] == "uninitialized"
        assert before["inference_lease"]["ownership_is_generation_proof"] is False
        with LocalInferenceLease(db).hold():
            status, busy = app.dispatch("GET", "/v1/status")
            assert status == 200 and busy["inference_lease"]["state"] == "busy"
            assert busy["readiness_is_live_inference_proof"] is False
        status, idle = app.dispatch("GET", "/v1/status")
        assert status == 200 and idle["inference_lease"]["state"] == "idle"
        assert idle["ready"] is True
    finally:
        app.close()


def test_local_desktop_prototype_exposes_real_kernel_lock_and_fail_closed_send():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    assert 'id="lease-indicator"' in HTML
    assert "observed.inference_lease?.state" in JAVASCRIPT
    assert "const foreignLease = ['busy', 'unavailable'].includes" in JAVASCRIPT
    assert "get('send').disabled = locked || working || (foreignLease && !mayQueue)" in JAVASCRIPT
    assert "health?.inference_lease?.state === 'busy'" in JAVASCRIPT
    assert "health.active_turn.session_id !== session" in JAVASCRIPT
    assert "/pending-turn" in JAVASCRIPT
    assert "get('selftest-start').disabled = locked || working || foreignLease" in JAVASCRIPT
    assert "get('lease-indicator').textContent = 'Execution lock unknown'" in JAVASCRIPT
    assert "LOCAL • ANOTHER EXECUTOR IS ACTIVE" in JAVASCRIPT
    assert "LOCAL • EXECUTION LOCK UNSAFE" in JAVASCRIPT


def test_strict_full_history_preview_stays_readonly_during_peer_lease_and_replays_exactly(tmp_path: Path):
    """Combined prototype: context budgets are readable while a peer owns the GGUF slot.

    A live kernel lock denies new strict model execution, not permissioned
    history/context inspection; release permits one genuine native generation
    with precisely the original policy-bound request ID and SQLite receipt.
    """
    model = native_model()
    database = tmp_path / "strict-cross-process.sqlite3"
    first = OfflineHTTPApplication(model, database, token="a" * 64)
    peer = OfflineHTTPApplication(model, database, token="b" * 64)
    request = {
        "message": "hello",
        "request_id": "strict-cross-process-2026",
        "max_output_tokens": 2,
        "require_full_history": True,
    }
    try:
        _, created = first.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        turn_path = f"/v1/sessions/{sid}/turn"
        preview_path = f"/v1/sessions/{sid}/context-preview"
        with first._inference_lease.hold():
            status, preview = peer.dispatch("POST", preview_path, {
                "message": "hello", "max_output_tokens": 2,
                "require_full_history": True,
            })
            assert status == 200
            assert preview["read_only"] is True
            assert preview["generation_performed"] is False
            assert preview["fits_full_history"] is True
            assert preview["session_revision"] == 0
            with pytest.raises(OfflineHTTPError) as blocked:
                peer.dispatch("POST", turn_path, request)
            assert blocked.value.status == 423
            assert peer._session(sid).revision == 0
        status, generated = peer.dispatch("POST", turn_path, request)
        assert status == 200 and generated["replayed"] is False
        assert generated["text"].strip()
        assert generated["local_execution_receipt"]["output_sha256"] == generated["output_digest"]
        status, replay = first.dispatch("POST", turn_path, request)
        assert status == 200 and replay["replayed"] is True
        assert replay["text"] == generated["text"]
        _, checked = first.dispatch("GET", f"/v1/sessions/{sid}")
        assert checked["revision"] == 1
        assert len(checked["messages"]) == 2
        status, post = first.dispatch("POST", preview_path, {
            "message": "world", "max_output_tokens": 2,
            "require_full_history": True,
        })
        assert status == 200 and post["session_revision"] == 1
        assert post["full_history_messages"] == 2
        assert post["fits_full_history"] is True
    finally:
        peer.close()
        first.close()


def test_scoped_grounding_honors_live_peer_lease_and_sqlite_source_custody(tmp_path: Path):
    """Two real local apps must not bypass either the source or OS lease fence."""
    from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
    model = native_model()
    db = tmp_path / "scoped-native-service.sqlite3"
    first = OfflineHTTPApplication(model, db, token="a" * 64)
    peer = OfflineHTTPApplication(model, db, token="b" * 64)
    try:
        _, selected = first.dispatch("POST", "/v1/knowledge/documents", {
            "title": "Operator-reviewed rasterizer A",
            "text": "The local rasterizer uses integer edge equations for coverage.",
        })
        _, excluded = first.dispatch("POST", "/v1/knowledge/documents", {
            "title": "Operator-reviewed rasterizer B",
            "text": "The alternate rasterizer uses local fixed-point edge coverage.",
        })
        _, created = first.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        endpoint = "/v1/sessions/" + sid
        chosen = selected["document_id"]
        rejected = excluded["document_id"]
        request = {
            "message": "How does rasterizer edge coverage work?",
            "request_id": "scoped-lease-local-model",
            "grounded": True, "require_full_history": True,
            "max_output_tokens": 2, "document_ids": [chosen],
        }
        with first._inference_lease.hold():
            _, preview = peer.dispatch("POST", endpoint + "/context-preview", {
                "message": request["message"],
                "grounded": True, "require_full_history": True,
                "max_output_tokens": 2, "document_ids": [chosen],
            })
            assert preview["document_scope"] == [chosen]
            assert preview["grounding_preview"]["citations"]
            assert all(c["document_id"] == chosen
                       for c in preview["grounding_preview"]["citations"])
            assert preview["generation_performed"] is False
            with pytest.raises(OfflineHTTPError) as busy:
                peer.dispatch("POST", endpoint + "/turn", request)
            assert busy.value.status == 423
            assert peer._session(sid).revision == 0

        # A previously lease-rejected request ID remains available for real
        # local model execution and an exact SQLite model-bound receipt.
        status, generated = peer.dispatch("POST", endpoint + "/turn", request)
        assert status == 200
        assert generated["replayed"] is False
        assert generated["local_execution_receipt"]["output_sha256"] == generated["output_digest"]
        assert generated["evidence"]["citations"]
        assert all(c["document_id"] == chosen for c in generated["evidence"]["citations"])

        status, replay = first.dispatch("POST", endpoint + "/turn", request)
        assert status == 200
        assert replay["replayed"] is True
        assert replay["text"] == generated["text"]
        with pytest.raises((RuntimeContractError, OfflineHTTPError)):
            first.dispatch("POST", endpoint + "/turn", {
                **request, "document_ids": [rejected],
            })
        _, before_revocation = first.dispatch("GET", endpoint)
        assert before_revocation["revision"] == 1
        first.dispatch("DELETE", "/v1/knowledge/documents/" + chosen)
        with pytest.raises(OfflineHTTPError) as revoked:
            peer.dispatch("POST", endpoint + "/turn", {
                **request, "request_id": "scoped-lease-revoked",
            })
        assert revoked.value.status == 422
        _, final = peer.dispatch("GET", endpoint)
        assert final["revision"] == 1
        # No source deletion may retroactively destroy the committed receipt.
        assert final["evidence"][0] == generated["evidence"]
    finally:
        peer.close()
        first.close()


def test_real_media_advisory_is_non_inferential_during_lease_then_scoped_native_turn_commits(tmp_path: Path):
    """End-user full path: raw local source -> review -> private knowledge -> model.

    This uses two real independent local HTTP application owners backed by
    one SQLite workspace and an actual source-native local transformer.
    Media is admitted while another service owns the native executor lease,
    without invoking a second model, and later generates exactly once.
    """
    import base64
    from hashlib import sha256
    from skeleton.app.jeeves_advisory import SCHEMA

    model = native_model()
    database = tmp_path / "media-owned-native.sqlite3"
    first = OfflineHTTPApplication(model, database, token="a" * 64)
    second = OfflineHTTPApplication(model, database, token="b" * 64)
    raw = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" +
           (8).to_bytes(4, "big") + (8).to_bytes(4, "big") +
           b"\x08\x06\x00\x00\x00" + b"OWNER_ONLY_BYTES_NEVER_IN_SQLITE_" * 3)
    statement = "The local rasterizer uses integer edge equations for coverage."
    media = {
        "schema_version": SCHEMA,
        "title": "Reviewed local renderer screenshot",
        "modality": "image-caption",
        "observation": statement,
        "observation_sha256": sha256(statement.encode("utf-8")).hexdigest(),
        "source_sha256": sha256(raw).hexdigest(),
        "media_type": "image/png",
        "media_base64": base64.b64encode(raw).decode("ascii"),
        "reviewed": True,
    }
    query = "How does rasterizer integer edge coverage work?"
    try:
        _, created = first.dispatch("POST", "/v1/sessions", {})
        sid = created["session_id"]
        path = "/v1/sessions/" + sid
        with first._inference_lease.hold():
            code, accepted = second.dispatch("POST", "/v1/advisory/ingest", media)
            assert code == 201
            assert accepted["reviewed"] is True
            assert accepted["source_digest_authority"] == "server-verified-transient-source-bytes"
            assert accepted["media_attestation"]["media_bytes_persisted"] is False
            assert accepted["generation_performed"] is False
            assert accepted["primary_model_unchanged"] is True
            assert accepted["remote_provider_called"] is False
            chosen = accepted["document_id"]
            request = {
                "message": query,
                "request_id": "media-reviewed-scoped-real-native",
                "grounded": True,
                "document_ids": [chosen],
                "max_output_tokens": 2,
                "require_full_history": True,
            }
            code, preview = second.dispatch("POST", path + "/context-preview", {
                "message": query,
                "grounded": True,
                "document_ids": [chosen],
                "require_full_history": True,
                "max_output_tokens": 2,
            })
            assert code == 200
            assert preview["read_only"] is True
            assert preview["generation_performed"] is False
            assert preview["document_scope"] == [chosen]
            assert preview["grounding_preview"]["citations"]
            assert all(c["document_id"] == chosen
                       for c in preview["grounding_preview"]["citations"])
            with pytest.raises(OfflineHTTPError) as locked:
                second.dispatch("POST", path + "/turn", request)
            assert locked.value.status == 423
            _, before = first.dispatch("GET", path)
            assert before["revision"] == 0
            assert before["messages"] == [] and before["evidence"] == []
        code, generated = second.dispatch("POST", path + "/turn", request)
        assert code == 200
        assert generated["replayed"] is False
        assert generated["text"].strip()
        assert generated["local_execution_receipt"]["output_sha256"] == generated["output_digest"]
        assert generated["evidence"]["citations"]
        assert all(c["document_id"] == chosen for c in generated["evidence"]["citations"])
        code, replay = first.dispatch("POST", path + "/turn", request)
        assert code == 200
        assert replay["replayed"] is True
        assert replay["text"] == generated["text"]
        _, stored = first.dispatch("GET", path)
        assert stored["revision"] == 1
        assert stored["evidence"][0] == generated["evidence"]
        _, reference = first.dispatch("GET", "/v1/knowledge/documents/" + chosen)
        assert reference["sha256"] == accepted["advisory_sha256"]
        assert "UNTRUSTED JEEVES ADVISORY" in reference["text"]
        assert "Server-verified transient media SHA-256" in reference["text"]
        assert media["media_base64"] not in reference["text"]
        assert raw not in database.read_bytes()
        assert media["media_base64"].encode("ascii") not in database.read_bytes()
    finally:
        second.close()
        first.close()


def test_inspection_does_not_initialize_existing_empty_marker(tmp_path: Path):
    lease = LocalInferenceLease(tmp_path / "empty.sqlite3")
    lease.path.touch(mode=0o600)
    lease.path.chmod(0o600)
    assert lease.inspect()["state"] == "unavailable"
    assert lease.path.read_bytes() == b""
    with lease.hold():
        assert lease.path.read_bytes() == b"\x00"


def test_inspection_cannot_recreate_marker_removed_after_initial_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    lease = LocalInferenceLease(tmp_path / "race.sqlite3")
    with lease.hold():
        pass
    original = lease._verified_descriptor

    def removed_before_open(*, initialize: bool):
        assert initialize is False
        lease.path.unlink()
        return original(initialize=initialize)

    monkeypatch.setattr(lease, "_verified_descriptor", removed_before_open)
    assert lease.inspect()["state"] == "unavailable"
    assert not lease.path.exists()


def test_single_nonzero_marker_is_not_valid_execution_custody(tmp_path: Path):
    lease = LocalInferenceLease(tmp_path / "wrong-byte.sqlite3")
    lease.path.write_bytes(b"\x01")
    lease.path.chmod(0o600)
    assert lease.inspect()["state"] == "unavailable"
    with pytest.raises(LocalInferenceLeaseUnavailable, match="marker format|reconciliation"):
        with lease.hold():
            pytest.fail("invalid single-byte marker admitted execution")
    assert lease.path.read_bytes() == b"\x01"


@pytest.mark.skipif(os.name != "posix", reason="POSIX open-file-description inheritance")
def test_parent_scope_exit_does_not_unlock_live_inherited_child(tmp_path):
    from skeleton.ai.runtime.inference.lease_custody import gguf_child_pass_fds

    lease = LocalInferenceLease(tmp_path / "scope-exit.sqlite3")
    worker = None
    try:
        with lease.hold():
            worker = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                pass_fds=gguf_child_pass_fds(), close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        assert worker.poll() is None
        with pytest.raises(LocalInferenceLeaseBusy):
            with LocalInferenceLease(tmp_path / "scope-exit.sqlite3").hold():
                pytest.fail("parent scope exit unlocked a live child")
    finally:
        if worker is not None:
            worker.kill()
            worker.wait(timeout=8)
    with lease.hold():
        assert lease.path.read_bytes() == b"\x00"


@pytest.mark.skipif(os.name != "posix", reason="POSIX ancestor mode checks")
def test_private_leaf_below_unprotected_ancestor_refuses_lease(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o700)
    leaf = shared / "private"
    leaf.mkdir(mode=0o700)
    shared.chmod(0o777)
    try:
        lease = LocalInferenceLease(leaf / "native.sqlite3")
        with pytest.raises(LocalInferenceLeaseUnavailable, match="ancestor"):
            with lease.hold():
                pytest.fail("unsafe ancestor allowed replacement of private lock directory")
        assert not lease.path.exists()
    finally:
        shared.chmod(0o700)


@pytest.mark.skipif(os.name != "posix", reason="POSIX inherited descriptor custody")
def test_copied_context_is_revoked_after_lease_exit(tmp_path):
    from contextvars import copy_context
    from skeleton.ai.runtime.inference.lease_custody import gguf_child_pass_fds

    with LocalInferenceLease(tmp_path / "revoked.sqlite3").hold():
        captured = copy_context()
        assert captured.run(gguf_child_pass_fds)
    with pytest.raises(RuntimeError, match="revoked"):
        captured.run(gguf_child_pass_fds)
    assert gguf_child_pass_fds() == ()


@pytest.mark.skipif(os.name != "posix", reason="POSIX inherited descriptor custody")
def test_descriptor_replacement_is_not_admitted_as_the_original_lease(tmp_path):
    from skeleton.ai.runtime.inference.lease_custody import (
        enter_local_lease, leave_local_lease, gguf_child_fd_scope,
    )
    first = os.open(tmp_path / "first", os.O_RDWR | os.O_CREAT, 0o600)
    second = os.open(tmp_path / "second", os.O_RDWR | os.O_CREAT, 0o600)
    token = enter_local_lease(first)
    try:
        os.dup2(second, first)
        with pytest.raises(RuntimeError, match="identity changed"):
            with gguf_child_fd_scope():
                pytest.fail("recycled descriptor admitted")
    finally:
        leave_local_lease(token)
        os.close(first)
        os.close(second)

def test_opt_in_queue_serializes_distinct_sessions_and_cancels_before_execution(tmp_path, monkeypatch):
    """Admission only: intentionally mocked execution failure, no inference claim."""
    import threading

    app = OfflineHTTPApplication(
        native_model(), tmp_path / "queued.sqlite3", token="q" * 64, max_queued_turns=2,
    )
    entered = threading.Event()
    release = threading.Event()
    started = []

    def blocked_failure(sid, request, *, turn=None):
        started.append(request["request_id"])
        if request["request_id"] == "first":
            entered.set()
            assert release.wait(10)
        raise OfflineHTTPError(503, "private runtime detail")

    monkeypatch.setattr(app, "_perform_turn", blocked_failure)

    def request(rid):
        return {"message": "hello", "request_id": rid, "max_output_tokens": 2}

    def settled(sid, rid):
        deadline = time.monotonic() + 10
        while True:
            ticket = app.turn_status(sid, rid)
            if ticket["terminal"]:
                assert ticket["finished_at"] is not None
                return ticket
            assert time.monotonic() < deadline
            time.sleep(0.01)

    try:
        sessions = [app.dispatch("POST", "/v1/sessions", {})[1]["session_id"] for _ in range(4)]
        first, second, third, fourth = sessions
        assert app.submit_turn(first, request("first"))[0] == 202
        assert entered.wait(5)
        assert app.submit_turn(second, request("second"))[1]["state"] == "queued"
        assert app.submit_turn(third, request("third"))[1]["state"] == "queued"
        _, observation = app.dispatch("GET", f"/v1/sessions/{second}/pending-turn")
        assert observation["turn"]["request_id"] == "second"
        assert observation["turn"]["state"] == "queued"
        assert set(observation["turn"]) == {
            "session_id", "request_id", "state", "cancel_requested", "created_at", "terminal",
        }
        assert app.dispatch("GET", "/v1/status")[1]["queued_turn_count"] == 2
        assert app.submit_turn(second, request("second"))[0] == 202
        with pytest.raises(OfflineHTTPError) as same:
            app.submit_turn(second, request("duplicate-session"))
        assert same.value.status == 409
        with pytest.raises(OfflineHTTPError) as full:
            app.submit_turn(fourth, request("fourth"))
        assert full.value.status == 429
        with pytest.raises(OfflineHTTPError) as deleting:
            app.dispatch("DELETE", f"/v1/sessions/{second}", {})
        assert deleting.value.status == 409
        cancelled = app.turn_status(second, "second", cancel=True)
        assert cancelled["state"] == "cancelled" and cancelled["finished_at"] is not None
        assert app.dispatch("GET", f"/v1/sessions/{second}/pending-turn")[1] == {"turn": None}
        assert app.submit_turn(fourth, request("fourth"))[1]["state"] == "queued"
        release.set()
        for sid, rid in [(first, "first"), (third, "third"), (fourth, "fourth")]:
            assert settled(sid, rid)["error"] == "local model or durable storage unavailable"
        assert started == ["first", "third", "fourth"]
        assert app._active_session is None
        assert not app._pending_turns
    finally:
        release.set()
        app.close()

def test_queued_real_native_turns_commit_and_replay_separately(tmp_path, monkeypatch):
    """Actual tiny native model, controlled admission timing; no trained GGUF claim."""
    import threading

    model = native_model()
    app = OfflineHTTPApplication(
        model, tmp_path / "native-queue.sqlite3", token="q" * 64, max_queued_turns=1,
    )
    entered = threading.Event()
    allow_first = threading.Event()
    original = app._perform_turn
    calls = []

    def controlled(sid, request, *, turn=None):
        calls.append((sid, request["request_id"]))
        if request["request_id"] == "first-native":
            entered.set()
            assert allow_first.wait(10)
        return original(sid, request, turn=turn)

    monkeypatch.setattr(app, "_perform_turn", controlled)
    try:
        first, second = [app.dispatch("POST", "/v1/sessions", {})[1]["session_id"] for _ in range(2)]
        inputs = [
            (first, {"message": "hello world", "request_id": "first-native", "max_output_tokens": 2}),
            (second, {"message": "local answer", "request_id": "second-native", "max_output_tokens": 2}),
        ]
        assert app.submit_turn(*inputs[0])[0] == 202
        assert entered.wait(5)
        assert app.submit_turn(*inputs[1])[1]["state"] == "queued"
        allow_first.set()
        for sid, request in inputs:
            rid = request["request_id"]
            deadline = time.monotonic() + 30
            while True:
                observed = app.turn_status(sid, rid)
                if observed["terminal"]:
                    break
                assert time.monotonic() < deadline, "native queue did not settle"
                time.sleep(0.02)
            assert observed["state"] == "complete", observed["error"]
            assert observed["result"]["local_execution_receipt"]["model_digest"] == model.model_digest
            assert app._session(sid).revision == 1
            status, replay = app.submit_turn(sid, request)
            assert status == 200
            assert replay["result"]["output_digest"] == observed["result"]["output_digest"]
            assert app.dispatch("GET", f"/v1/sessions/{sid}/pending-turn")[1] == {"turn": None}
        assert calls == [(sid, request["request_id"]) for sid, request in inputs]
    finally:
        allow_first.set()
        app.close()

def test_durable_queue_metadata_survives_restart_and_refuses_changed_retry(tmp_path, monkeypatch):
    """Metadata only: no automatic inference, plaintext persistence or peer takeover."""
    import threading

    model = native_model()
    database = tmp_path / "durable-queue.sqlite3"
    app = OfflineHTTPApplication(model, database, token="q" * 64, max_queued_turns=2)
    entered = threading.Event()
    release = threading.Event()
    peer = None
    second = None
    calls = []

    def held_failure(sid, request, *, turn=None):
        calls.append(request["request_id"])
        entered.set()
        assert release.wait(10)
        raise OfflineHTTPError(503, "private backend detail")

    monkeypatch.setattr(app, "_perform_turn", held_failure)
    try:
        a, b = [app.dispatch("POST", "/v1/sessions", {})[1]["session_id"] for _ in range(2)]
        body = {"message": "private marker not stored by admission", "request_id": "recover-me",
                "max_output_tokens": 2}
        assert app.submit_turn(a, {**body, "request_id": "first"})[0] == 202
        assert entered.wait(5)
        assert app.submit_turn(b, body)[1]["state"] == "queued"
        peer = OfflineHTTPApplication(model, database, token="p" * 64)
        with pytest.raises(Exception, match="exclusive local queue ownership unavailable"):
            OfflineHTTPApplication(model, database, token="r" * 64, max_queued_turns=1)
        with pytest.raises(OfflineHTTPError) as occupied:
            peer.submit_turn(b, {**body, "retry": True})
        assert occupied.value.status == 409
        with pytest.raises(OfflineHTTPError) as different_id:
            peer.submit_turn(b, {**body, "request_id": "peer-other-id"})
        assert different_id.value.status == 409
        from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
        with pytest.raises(RuntimeContractError, match="local queue admission is unresolved"):
            peer._store.delete(b, peer.model_digest, peer.tokenizer_digest)
        saved = peer._session(b)
        rid, digest = peer._turn_identity({**body, "request_id": "direct-peer"}, peer.default_output_tokens)
        with pytest.raises(RuntimeContractError, match="queue custody"):
            peer._store.verify_turn_admission(saved, rid, digest)
        with pytest.raises(OfflineHTTPError) as sync_peer:
            peer.dispatch("POST", f"/v1/sessions/{b}/turn", {**body, "request_id": "peer-sync"})
        assert sync_peer.value.status == 409
        with pytest.raises(OfflineHTTPError) as delete:
            peer.dispatch("DELETE", f"/v1/sessions/{b}")
        assert delete.value.status == 409
        records = peer.dispatch("GET", f"/v1/sessions/{b}/admissions")[1]
        assert records["automatic_replay"] is False
        assert records["admissions"][0]["request_id"] == "recover-me"
        assert records["admissions"][0]["state"] == "admitted"
        assert "private marker" not in str(records)
        assert "digest" not in str(records)
        assert app.turn_status(b, "recover-me", cancel=True)["state"] == "cancelled"
        release.set()
        app.close()
        app = None
        second = OfflineHTTPApplication(model, database, token="s" * 64, max_queued_turns=1)
        recovered = second.turn_status(b, "recover-me")
        assert recovered["state"] == "cancelled"
        assert recovered["recovered_admission"] is True
        with pytest.raises(OfflineHTTPError) as changed:
            second.submit_turn(b, {**body, "message": "different", "retry": True})
        assert changed.value.status == 409
        with pytest.raises(OfflineHTTPError) as implicit:
            second.submit_turn(b, body)
        assert implicit.value.status == 409
        assert calls == ["first"]
        assert second._session(b).revision == 0
        assert second.submit_turn(b, {**body, "retry": True})[0] == 202
        deadline = time.monotonic() + 30
        while True:
            observed = second.turn_status(b, "recover-me")
            if observed["terminal"]:
                break
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert observed["state"] == "complete", observed["error"]
        assert second.dispatch("GET", f"/v1/sessions/{b}/admissions")[1]["admissions"] == []
    finally:
        release.set()
        if app is not None:
            app.close()
        if second is not None:
            second.close()
        if peer is not None:
            peer.close()


def test_interrupted_admission_recovery_is_metadata_only(tmp_path):
    from skeleton.app.offline_turn_admission import DurableTurnAdmissions, QueueAdmissionOwner

    model = native_model()
    database = tmp_path / "interrupted-queue.sqlite3"
    first = OfflineHTTPApplication(model, database, token="q" * 64)
    try:
        sid = first.dispatch("POST", "/v1/sessions", {})[1]["session_id"]
        body = {"message": "hello", "request_id": "interrupted", "max_output_tokens": 2}
        rid, digest = first._turn_identity(body, first.default_output_tokens)
        owner = QueueAdmissionOwner(database)
        try:
            ledger = DurableTurnAdmissions(first._store, first.model_digest, first.tokenizer_digest)
            assert ledger.claim(owner, sid, rid, digest, retry=False) == 1
        finally:
            owner.close()
    finally:
        first.close()
    reopened = OfflineHTTPApplication(model, database, token="t" * 64, max_queued_turns=1)
    try:
        status = reopened.turn_status(sid, rid)
        assert status["recovered_admission"] is True
        assert status["inference_outcome_unknown"] is True
        assert status["result"] is None
        assert reopened._session(sid).revision == 0
        assert reopened.dispatch("GET", f"/v1/sessions/{sid}/admissions")[1]["admissions"][0]["state"] == "interrupted"
    finally:
        reopened.close()

def test_local_browser_recovery_requires_explicit_same_identity_retry():
    from skeleton.app.offline_web import HTML, JAVASCRIPT
    assert 'id="admission-recovery"' in HTML
    assert "No automatic replay." in HTML
    assert "state.admissionSession !== session" in JAVASCRIPT
    assert "request_id: recoveryId ?? crypto.randomUUID()" in JAVASCRIPT
    assert "if (recoveryId !== null) retry = true" in JAVASCRIPT
    assert "await submit(false, rid)" in JAVASCRIPT
    assert "No request was replayed" in JAVASCRIPT

def test_queue_admission_fences_revision_and_attempt_without_backend(tmp_path):
    from skeleton.app.offline_turn_admission import AdmissionRejected, DurableTurnAdmissions, QueueAdmissionOwner

    model = native_model()
    database = tmp_path / "queue-revision.sqlite3"
    app = OfflineHTTPApplication(model, database, token="q" * 64)
    owner = QueueAdmissionOwner(database)
    try:
        sid = app.dispatch("POST", "/v1/sessions", {})[1]["session_id"]
        body = {"message": "hello", "request_id": "revision-pinned", "max_output_tokens": 2}
        rid, digest = app._turn_identity(body, app.default_output_tokens)
        ledger = DurableTurnAdmissions(app._store, app.model_digest, app.tokenizer_digest)
        assert ledger.claim(owner, sid, rid, digest, retry=False) == 1
        ledger.verify_execution(owner, sid, rid, digest, 1)
        with pytest.raises(AdmissionRejected):
            ledger.verify_execution(owner, sid, rid, digest, 2)
        with pytest.raises(AdmissionRejected):
            ledger.claim(owner, sid, rid, digest, retry=True)
        with pytest.raises(AdmissionRejected):
            ledger.claim(owner, sid, "different", digest, retry=False)
        with pytest.raises(AdmissionRejected):
            ledger.finish(owner, sid, rid, digest, 1, "settled")
        # Deliberately simulate a changed observation at the SQL authority.
        # No fabricated transcript or model result is asserted as valid.
        with app._store._transaction():
            app._store._db.execute("UPDATE offline_sessions SET revision=1 WHERE session_id=?", (sid,))
        with pytest.raises(AdmissionRejected, match="revision changed"):
            ledger.verify_execution(owner, sid, rid, digest, 1)
        ledger.finish(owner, sid, rid, digest, 1, "failed")
        with pytest.raises(AdmissionRejected, match="conversation changed"):
            ledger.claim(owner, sid, rid, digest, retry=True)
        with app._store._transaction():
            app._store._db.execute("UPDATE offline_sessions SET revision=0 WHERE session_id=?", (sid,))
        assert ledger.claim(owner, sid, rid, digest, retry=True) == 2
        with pytest.raises(AdmissionRejected):
            ledger.finish(owner, sid, rid, digest, 1, "failed")
        ledger.verify_execution(owner, sid, rid, digest, 2)
        ledger.finish(owner, sid, rid, digest, 2, "cancelled")
    finally:
        owner.close()
        app.close()


def test_committed_queue_metadata_reclaims_only_receipted_identity(tmp_path, monkeypatch):
    import skeleton.app.offline_turn_admission as admission

    model = native_model()
    app = OfflineHTTPApplication(
        model, tmp_path / "queue-reclaim.sqlite3", token="q" * 64, max_queued_turns=1,
    )
    monkeypatch.setattr(admission, "MAX_SESSION_ADMISSIONS", 1)
    try:
        sid = app.dispatch("POST", "/v1/sessions", {})[1]["session_id"]
        bodies = [
            {"message": "hello world", "request_id": "first-reclaim", "max_output_tokens": 2},
            {"message": "local answer", "request_id": "second-reclaim", "max_output_tokens": 2},
        ]
        for body in bodies:
            assert app.submit_turn(sid, body)[0] == 202
            deadline = time.monotonic() + 30
            while True:
                ticket = app.turn_status(sid, body["request_id"])
                if ticket["terminal"]:
                    break
                assert time.monotonic() < deadline
                time.sleep(0.02)
            assert ticket["state"] == "complete", ticket["error"]
        assert app._session(sid).revision == 2
        assert app._admissions.lookup(sid, bodies[0]["request_id"]) is None
        assert app.submit_turn(sid, bodies[0])[0] == 200
        assert app._session(sid).revision == 2
    finally:
        app.close()

def test_queue_receipt_and_admission_settlement_share_sqlite_commit(tmp_path, monkeypatch):
    """Actual tiny native model; interrupt only the later metadata callback."""
    import threading

    model = native_model()
    app = OfflineHTTPApplication(
        model, tmp_path / "atomic-admission.sqlite3", token="q" * 64, max_queued_turns=1,
    )
    callback = threading.Event()

    def unavailable(*args, **kwargs):
        callback.set()
        raise OSError("simulated later metadata write failure")

    monkeypatch.setattr(app._admissions, "finish", unavailable)
    try:
        sid = app.dispatch("POST", "/v1/sessions", {})[1]["session_id"]
        body = {"message": "hello world", "request_id": "atomic-receipt", "max_output_tokens": 2}
        assert app.submit_turn(sid, body)[0] == 202
        assert callback.wait(30)
        ticket = app.turn_status(sid, body["request_id"])
        assert ticket["state"] == "complete", ticket["error"]
        assert app._session(sid).revision == 1
        assert ticket["result"]["local_execution_receipt"]["model_digest"] == model.model_digest
        assert app._admissions.lookup(sid, body["request_id"])["state"] == "settled"
        assert app.submit_turn(sid, body)[0] == 200
        assert app._session(sid).revision == 1
    finally:
        app.close()
