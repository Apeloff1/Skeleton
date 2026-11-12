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
    assert "get('send').disabled = locked || working || foreignLease" in JAVASCRIPT
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
