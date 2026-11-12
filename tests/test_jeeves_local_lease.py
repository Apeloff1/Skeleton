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
