"""Actual CPU-native -> guarded session -> journal -> AES-GCM app integration.

Uses a deterministic simulated OS probe and in-memory CAS; this does NOT
certify platform hardware or cross-process anti-rollback durability.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_queue import MeasuredStreamBudget, StreamRequest
from skeleton.ai.model_runtime.fair_stream_execution_journal import FairStreamExecutionJournal
from skeleton.ai.model_runtime.fair_stream_session import DurableFairStreamSession
from skeleton.ai.model_runtime.fair_stream_sqlite import DurableFairStreamStore
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase
from skeleton.ai.model_runtime.native_fair_stream_backend import NativePromptRegistry
from skeleton.ai.model_runtime.private_sqlite import open_private_sqlite
from skeleton.app.offline_native_fair_stream import (
    bind_native_cpu_dispatch_service, stage_native_cpu_prompt,
)

SESSION = "a" * 32
CUSTODY_KEY = b"c" * 32
EXECUTION_KEY = b"e" * 32
RESULT_KEY = b"r" * 32


class SimulatedCAS:
    def __init__(self):
        self.value = None

    def initialize(self, *, generation, digest):
        if self.value is not None:
            raise ValueError("already initialized")
        self.value = generation, digest

    def read(self):
        if self.value is None:
            raise ValueError("anchor missing")
        return self.value

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.value != (expected_generation, expected_digest):
            raise ValueError("CAS conflict")
        self.value = generation, digest


def install_probe(monkeypatch):
    def sample(self, *, token_budget, storage_path):
        return MeasuredStreamBudget(
            available_ram_bytes=8192, reserved_ram_bytes=1024,
            token_budget=token_budget, stream_slots=1, pressure_ppm=0,
            thermal_hold=False, measurement="os_probe",
        ), {
            "measurement": "os_probe",
            "gpu_device_qualified": False,
            "physical_memory_reserved": False,
            "auxiliary_telemetry_incomplete": True,
            "schema": "skeleton.ai.live-stream-pressure.v1",
            "cross_process_admission_guaranteed": False,
            "thermal_trip_measured": True,
            "cgroup_swap_spill_allowed": True,
            "cgroup_swap_limit_measured": True,
            "cgroup_memory_limit_measured": True,
            "holds": {
                "thermal": False, "cgroup_high": False, "cgroup_oom": False,
                "cgroup_memory": False, "cgroup_swap_spill": False,
                "io": False, "cpu_throttle": False, "swap_churn": False,
                "reclaim": False, "disk_reserve": False,
            },

        }
    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)


@pytest.fixture
def private_files(tmp_path):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("secure POSIX SQLite handles required")
    result_dir = tmp_path / "results"
    journal_dir = tmp_path / "journal"
    result_dir.mkdir(mode=0o700)
    journal_dir.mkdir(mode=0o700)
    result_dir.chmod(0o700)
    journal_dir.chmod(0o700)
    with open_private_sqlite(result_dir, create=True) as result_handle:
        with open_private_sqlite(journal_dir, create=True) as journal_handle:
            yield result_handle, journal_handle


def build(private_files):
    result_handle, journal_handle = private_files
    runtime = NativeLLMRuntime(
        TinyTransformer(vocab=("hello", "world"), dim=8, ctx=24, seed=3),
    )
    registry = NativePromptRegistry(session_id=SESSION)
    journal = FairStreamExecutionJournal(
        journal_handle.connection, session_id=SESSION, execution_key=EXECUTION_KEY,
    )
    store = DurableFairStreamStore(
        sqlite3.connect(":memory:"), custody_key=CUSTODY_KEY,
        execution_key=EXECUTION_KEY, session_id=SESSION, whole_request=True,
    )
    session = DurableFairStreamSession.bootstrap(store, SimulatedCAS())
    return runtime, registry, journal, session, result_handle


def test_real_cpu_app_dispatch_publishes_encrypted_result(private_files, monkeypatch):
    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    sampler = LiveStreamBudgetSampler()
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=sampler, storage_path=".",
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry,
        request_id="request-1", tenant_id="alice",
        prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest(
        "request-1", "alice", InferencePhase.PREFILL, 2, 16,
    ))
    result = service.execute_next(token_budget=2)
    assert result["state"] == "durably_acknowledged"
    assert result["executed"] is True
    assert result["gpu_device_qualified"] is False
    assert service.status().pending_leases == 0
    assert registry.status()["consumed_or_revoked"] == 1
    row = vault._connection.execute(
        "SELECT LENGTH(ciphertext), plaintext_bytes "
        "FROM local_fair_stream_sealed_results"
    ).fetchone()
    assert row is not None
    assert row[0] == row[1] + 16
    assert journal._connection.execute(
        "SELECT state FROM local_fair_stream_execution_journal"
    ).fetchone() == ("committed",)


def test_wrong_native_session_rejected_before_owner_creation(private_files):
    runtime, registry, journal, session, result_handle = build(private_files)
    registry = NativePromptRegistry(session_id="f" * 32)
    with pytest.raises(ValueError, match="session"):
        bind_native_cpu_dispatch_service(
            session=session, runtime=runtime, registry=registry,
            result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
            sampler=LiveStreamBudgetSampler(), storage_path=".",
        )


def test_result_and_journal_same_inode_denied(private_files):
    result_handle, _ = private_files
    runtime = NativeLLMRuntime(TinyTransformer(vocab=("hello",), ctx=16))
    registry = NativePromptRegistry(session_id=SESSION)
    journal = FairStreamExecutionJournal(
        result_handle.connection, session_id=SESSION, execution_key=EXECUTION_KEY,
    )
    from skeleton.app.offline_native_fair_stream import bind_native_cpu_result_owner
    with pytest.raises(ValueError, match="separate connections"):
        bind_native_cpu_result_owner(
            runtime=runtime, registry=registry, result_handle=result_handle,
            journal_handle=result_handle, journal=journal, result_key=RESULT_KEY,
            sampler=LiveStreamBudgetSampler(), storage_path=".",
        )


def test_app_native_prompt_ram_status_is_payload_free():
    from skeleton.app.offline_native_fair_stream import (
        native_cpu_prompt_memory_status,
    )
    runtime = NativeLLMRuntime(
        TinyTransformer(vocab=("hello", "world"), dim=8, ctx=24, seed=3),
    )
    registry = NativePromptRegistry(session_id=SESSION)
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry,
        request_id="sensitive-request", tenant_id="sensitive-tenant",
        prompt="hello", max_output_tokens=1,
    )
    status = native_cpu_prompt_memory_status(registry)
    assert status["staged_bytes"] == 5
    assert status["staged_grants"] == 1
    assert "sensitive-request" not in str(status)
    assert "sensitive-tenant" not in str(status)
    assert "hello" not in str(status)
    with pytest.raises(ValueError, match="canonical"):
        native_cpu_prompt_memory_status(object())


def test_authenticated_native_submission_stages_exact_bound_owner(
    private_files, monkeypatch,
):
    from skeleton.app.offline_native_fair_stream import (
        submit_authenticated_native_cpu_prompt,
    )
    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    request = StreamRequest(
        "native-auth-1", "alice", InferencePhase.PREFILL, 2, 16,
    )
    result = submit_authenticated_native_cpu_prompt(
        service=service, vault=vault, runtime=runtime, registry=registry,
        authenticated_tenant_id="alice", request=request,
        prompt="hello", max_output_tokens=2,
    )
    assert result.pending_leases == 0
    assert registry.budget_status()["staged_bytes"] == 5
    assert service.execute_next(token_budget=2)["executed"] is True
    assert registry.budget_status()["staged_bytes"] == 0


def test_authenticated_native_submission_denies_wrong_tenant_before_staging(
    private_files,
):
    from skeleton.app.offline_native_fair_stream import (
        submit_authenticated_native_cpu_prompt,
    )
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    request = StreamRequest(
        "native-auth-2", "alice", InferencePhase.PREFILL, 2, 16,
    )
    with pytest.raises(ValueError, match="tenant"):
        submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="bob", request=request,
            prompt="hello", max_output_tokens=2,
        )
    assert registry.budget_status()["staged_bytes"] == 0


def test_failed_native_submission_revokes_ephemeral_grant(
    private_files, monkeypatch,
):
    from skeleton.app.offline_native_fair_stream import (
        submit_authenticated_native_cpu_prompt,
    )
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    request = StreamRequest(
        "native-auth-3", "alice", InferencePhase.PREFILL, 2, 16,
    )
    def broken(_):
        raise RuntimeError("simulated durable submit failure")
    monkeypatch.setattr(service, "submit", broken)
    with pytest.raises(RuntimeError, match="durable submit failure"):
        submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="alice", request=request,
            prompt="hello", max_output_tokens=2,
        )
    assert registry.budget_status()["staged_bytes"] == 0
    assert registry.status()["consumed_or_revoked"] == 1


def test_native_owner_rejects_unrelated_journal_descriptor(private_files):
    from skeleton.app.offline_native_fair_stream import bind_native_cpu_result_owner
    result_handle, journal_handle = private_files
    runtime, registry, journal, session, _ = build(private_files)
    with pytest.raises(ValueError, match="mismatch"):
        bind_native_cpu_result_owner(
            runtime=runtime, registry=registry, result_handle=result_handle,
            journal_handle=result_handle, journal=journal, result_key=RESULT_KEY,
            sampler=LiveStreamBudgetSampler(), storage_path=".",
        )


def test_native_owner_detects_journal_path_replacement_before_execution(
    private_files, monkeypatch,
):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred
    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry,
        request_id="inode-race", tenant_id="alice",
        prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest(
        "inode-race", "alice", InferencePhase.PREFILL, 2, 16,
    ))
    handle = private_files[1]
    # Replacing a directory entry after binding cannot turn the old SQLite
    # connection into an authorized fresh journal inode.
    os.rename(
        handle._filename, handle._filename + ".moved",
        src_dir_fd=handle._directory_fd, dst_dir_fd=handle._directory_fd,
    )
    with pytest.raises(DispatchDeferred, match="queued authorization"):
        service.execute_next(token_budget=2)
    assert registry.status()["staged"] == 1
    assert service.status().pending_leases == 0
    assert not service.status().execution_uncertain

def test_native_whole_request_defers_without_consuming_prompt_then_completes(
    private_files, monkeypatch,
):
    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="whole",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("whole", "alice", InferencePhase.PREFILL, 2, 16))
    deferred = service.execute_next(token_budget=1)
    assert deferred["executed"] is False
    assert registry.status()["staged"] == 1
    assert service.status().pending_leases == 0
    assert journal._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 0
    result = service.execute_next(token_budget=2)
    assert result["executed"]
    assert session.verify()["checkpoint"]["requests"] == []
    assert registry.status()["consumed_or_revoked"] == 1
    assert service.execute_next(token_budget=2)["executed"] is False

def test_native_expired_grant_cannot_mint_lease_and_tenant_can_cancel(private_files, monkeypatch):
    from skeleton.ai.model_runtime import native_fair_stream_backend as native_module
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred

    install_probe(monkeypatch)
    now = [100]
    monkeypatch.setattr(native_module, "monotonic_ns", lambda: now[0])
    runtime, registry, journal, session, result_handle = build(private_files)
    service, _ = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="expires",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("expires", "alice", InferencePhase.PREFILL, 2, 16))
    original = session.verify()
    now[0] += registry._max_stage_age_ns
    with pytest.raises(DispatchDeferred, match="queued authorization"):
        service.execute_next(token_budget=2)
    assert session.verify() == original
    assert registry.status()["staged"] == 0
    assert journal._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 0
    with pytest.raises(ValueError, match="tenant"):
        service.cancel("expires", tenant_id="bob")
    with pytest.raises(ValueError, match="tenant"):
        service.cancel("expires")
    assert session.verify() == original
    assert service.cancel("expires", tenant_id="alice").pending_leases == 0
    assert not session.verify()["checkpoint"]["requests"]


def test_native_cancel_releases_plaintext_and_burns_grant(private_files, monkeypatch):
    from skeleton.ai.model_runtime.native_fair_stream_backend import NativeFairStreamDenied

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, _ = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="cancelled",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("cancelled", "alice", InferencePhase.PREFILL, 2, 16))
    assert registry.budget_status()["staged_bytes"] == 5
    service.cancel("cancelled", tenant_id="alice")
    assert registry.budget_status()["staged_bytes"] == 0
    assert service.execute_next(token_budget=2)["executed"] is False
    with pytest.raises(NativeFairStreamDenied, match="duplicate"):
        stage_native_cpu_prompt(
            runtime=runtime, registry=registry, request_id="cancelled",
            tenant_id="alice", prompt="hello", max_output_tokens=2,
        )

def test_native_durable_request_binds_process_keyed_grant_not_plaintext(private_files, monkeypatch):
    from skeleton.ai.model_runtime.native_fair_stream_backend import NativeFairStreamDenied
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred
    from skeleton.app.offline_native_fair_stream import submit_authenticated_native_cpu_prompt

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    request = StreamRequest("bound-native", "alice", InferencePhase.PREFILL, 2, 16)
    submit_authenticated_native_cpu_prompt(
        service=service, vault=vault, runtime=runtime, registry=registry,
        authenticated_tenant_id="alice", request=request,
        prompt="hello", max_output_tokens=2,
    )
    original = session.verify()
    rows = original["checkpoint"]["requests"]
    assert len(rows[0]["authorization_digest"]) == 64
    assert "hello" not in str(original)
    assert registry._binding_key.hex() not in str(original)
    with pytest.raises(ValueError, match="durable"):
        submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="alice", request=request,
            prompt="world", max_output_tokens=2,
        )
    assert session.verify() == original
    fresh = NativePromptRegistry(session_id=SESSION)
    stage_native_cpu_prompt(
        runtime=runtime, registry=fresh, request_id="bound-native",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    with pytest.raises(NativeFairStreamDenied, match="commitment mismatch"):
        fresh.verify_queued(rows)
    # Simulate a lost process key: the exact checkpoint remains unmodified.
    monkeypatch.setattr(registry, "_binding_key", fresh._binding_key)
    with pytest.raises(DispatchDeferred, match="queued authorization"):
        service.execute_next(token_budget=2)
    assert session.verify() == original
    assert journal._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 0
    service.cancel("bound-native", tenant_id="alice")
    assert registry.budget_status()["staged_bytes"] == 0

def test_expired_issued_native_permit_can_be_explicitly_cancelled_without_execution(
    private_files, monkeypatch,
):
    from skeleton.ai.model_runtime import native_fair_stream_backend as native_module
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred, DispatchUncertain

    install_probe(monkeypatch)
    now = [100]
    monkeypatch.setattr(native_module, "monotonic_ns", lambda: now[0])
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="issued-expired",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("issued-expired", "alice", InferencePhase.PREFILL, 2, 16))
    permits, _ = service._guard.plan_live(token_budget=2)
    permit, = permits
    now[0] += registry._max_stage_age_ns
    with pytest.raises(DispatchDeferred, match="pending prompt authorization"):
        service.execute_next(token_budget=2)
    before = session.verify()
    with pytest.raises(ValueError, match="tenant"):
        service.cancel_unstarted("issued-expired", tenant_id="bob")
    assert session.verify() == before
    status = service.cancel_unstarted("issued-expired", tenant_id="alice")
    assert status.pending_leases == 0 and not status.execution_uncertain
    assert not session.verify()["checkpoint"]["requests"]
    assert journal.request_exists("issued-expired")
    assert journal._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 0
    assert vault._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_sealed_results"
    ).fetchone()[0] == 0
    with pytest.raises(DispatchUncertain):
        service._guard.execute_once(permit)
    assert service.execute_next(token_budget=2)["executed"] is False

@pytest.mark.parametrize("damage", ["none", "ciphertext", "missing", "intent"])
def test_published_native_result_recovery_never_reexecutes(
    private_files, monkeypatch, damage,
):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
    from skeleton.ai.model_runtime.fair_stream_recovery import (
        issue_recovery_authorization, RecoveryAuthorizationDenied,
    )

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".", operator_recovery_key=b"o" * 32,
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="published-native",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("published-native", "alice", InferencePhase.PREFILL, 2, 16))
    original_commit = journal.commit

    def lost_commit(*args, **kwargs):
        raise OSError("simulated loss between vault publication and journal commit")

    monkeypatch.setattr(journal, "commit", lost_commit)
    with pytest.raises(DispatchUncertain, match="uncertain"):
        service.execute_next(token_budget=2)
    monkeypatch.setattr(journal, "commit", original_commit)
    before = session.verify()
    lease = before["checkpoint"]["pending"][0]
    assert registry.status()["consumed_or_revoked"] == 1
    assert journal._connection.execute(
        "SELECT state FROM local_fair_stream_execution_journal"
    ).fetchone() == ("running",)
    assert vault._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_sealed_results"
    ).fetchone()[0] == 1

    def approval(purpose):
        return issue_recovery_authorization(
            recovery_key=b"o" * 32, session_id=SESSION,
            generation=before["generation"], checkpoint_digest=before["checkpoint_digest"],
            lease_id=lease["lease_id"], nonce="f" * 32, purpose=purpose,
        )

    def forbidden(*args, **kwargs):
        pytest.fail("recovery invoked native inference")

    monkeypatch.setattr(vault._backend, "generate", forbidden)
    with pytest.raises(RecoveryAuthorizationDenied, match="purpose"):
        service.reconcile_published(authorization=approval("committed"), recovery_key=b"o" * 32)
    if damage == "ciphertext":
        vault._connection.execute("UPDATE local_fair_stream_sealed_results SET nonce=zeroblob(12)")
    elif damage == "missing":
        vault._connection.execute("DELETE FROM local_fair_stream_sealed_results")
    elif damage == "intent":
        journal._connection.execute("DELETE FROM local_fair_stream_execution_journal")
    if damage != "none":
        with pytest.raises(DispatchUncertain, match="published result"):
            service.reconcile_published(authorization=approval("published"), recovery_key=b"o" * 32)
        assert session.verify() == before
        assert service.status().execution_uncertain
        return
    result = service.reconcile_published(authorization=approval("published"), recovery_key=b"o" * 32)
    assert result.pending_leases == 0 and not result.execution_uncertain
    assert session.verify()["checkpoint"]["requests"] == []
    assert journal._connection.execute(
        "SELECT state FROM local_fair_stream_execution_journal"
    ).fetchone() == ("committed",)
    assert registry.status()["consumed_or_revoked"] == 1

@pytest.mark.parametrize("damage", ["none", "missing", "nonce", "signed-count", "foreign-journal"])
def test_committed_recovery_verifies_bound_native_vault(private_files, monkeypatch, damage):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
    from skeleton.ai.model_runtime.fair_stream_recovery import issue_recovery_authorization
    from skeleton.ai.model_runtime.fair_stream_custody import sign_execution_result
    from skeleton.ai.model_runtime.fair_stream_execution_journal import _receipt_bytes

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".", operator_recovery_key=b"o" * 32,
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="committed-native",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("committed-native", "alice", InferencePhase.PREFILL, 2, 16))
    original_ack = session.acknowledge

    def lost_ack(*args, **kwargs):
        raise OSError("simulated loss after signed journal commit")

    monkeypatch.setattr(session, "acknowledge", lost_ack)
    with pytest.raises(DispatchUncertain, match="receipt not durably reconciled"):
        service.execute_next(token_budget=2)
    monkeypatch.setattr(session, "acknowledge", original_ack)
    before = session.verify()
    lease = before["checkpoint"]["pending"][0]
    approval = issue_recovery_authorization(
        recovery_key=b"o" * 32, session_id=SESSION,
        generation=before["generation"], checkpoint_digest=before["checkpoint_digest"],
        lease_id=lease["lease_id"], nonce="f" * 32,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("committed recovery invoked native inference")

    monkeypatch.setattr(vault._backend, "generate", forbidden)
    if damage == "missing":
        vault._connection.execute("DELETE FROM local_fair_stream_sealed_results")
    elif damage == "nonce":
        vault._connection.execute("UPDATE local_fair_stream_sealed_results SET nonce=zeroblob(12)")
    elif damage == "signed-count":
        count, digest = journal._connection.execute(
            "SELECT consumed_tokens,result_digest FROM local_fair_stream_execution_journal"
        ).fetchone()
        different = (count + 1) % 3
        forged = sign_execution_result(
            execution_key=EXECUTION_KEY, session_id=SESSION,
            generation=before["generation"], checkpoint_digest=before["checkpoint_digest"],
            lease_id=lease["lease_id"], consumed_tokens=different, result_digest=digest,
        )
        journal._connection.execute(
            "UPDATE local_fair_stream_execution_journal SET consumed_tokens=?,receipt=?",
            (different, _receipt_bytes(forged)),
        )
    if damage == "foreign-journal":
        with sqlite3.connect(":memory:") as connection:
            other = FairStreamExecutionJournal(
                connection, session_id=SESSION, execution_key=EXECUTION_KEY,
            )
            with pytest.raises(ValueError, match="bound execution journal"):
                service.reconcile_committed(journal=other, authorization=approval, recovery_key=b"o" * 32)
        assert session.verify() == before
        return
    if damage != "none":
        with pytest.raises(DispatchUncertain, match="committed receipt"):
            service.reconcile_committed(journal=journal, authorization=approval, recovery_key=b"o" * 32)
        assert session.verify() == before and service.status().execution_uncertain
        return
    done = service.reconcile_committed(journal=journal, authorization=approval, recovery_key=b"o" * 32)
    assert done.pending_leases == 0 and not done.execution_uncertain
    assert registry.status()["consumed_or_revoked"] == 1


@pytest.mark.parametrize("ledger", ["journal", "vault"])
def test_native_admission_capacity_denies_before_staging(private_files, monkeypatch, ledger):
    from skeleton.app.offline_native_fair_stream import submit_authenticated_native_cpu_prompt
    from skeleton.ai.model_runtime import fair_stream_execution_journal, fair_stream_result_vault

    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    if ledger == "journal":
        monkeypatch.setattr(fair_stream_execution_journal, "MAX_JOURNAL_ROWS", 1)
    else:
        monkeypatch.setattr(fair_stream_result_vault, "MAX_RESULT_ROWS", 1)

    def submit(request_id):
        return submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="alice", prompt="hello", max_output_tokens=2,
            request=StreamRequest(request_id, "alice", InferencePhase.PREFILL, 2, 16),
        )

    submit("capacity-first")
    before = session.verify()
    memory = registry.budget_status()
    with pytest.raises(RuntimeError, match="capacity"):
        submit("capacity-second")
    assert session.verify() == before
    assert registry.budget_status() == memory
    assert registry.status()["staged"] == 1


def test_native_session_cannot_share_execution_connection(private_files):
    runtime, registry, journal, _, result_handle = build(private_files)
    store = DurableFairStreamStore(
        private_files[1].connection, custody_key=CUSTODY_KEY,
        execution_key=EXECUTION_KEY, session_id=SESSION, whole_request=True,
        private_handle=private_files[1],
    )
    session = DurableFairStreamSession.bootstrap(store, SimulatedCAS())
    with pytest.raises(ValueError, match="separate connections"):
        bind_native_cpu_dispatch_service(
            session=session, runtime=runtime, registry=registry,
            result_handle=result_handle, journal_handle=private_files[1],
            journal=journal, result_key=RESULT_KEY,
            sampler=LiveStreamBudgetSampler(), storage_path=".",
        )
    assert journal._private_handle is None

@pytest.mark.parametrize("published", [False, True])
def test_native_uncertain_retirement_preserves_replay_fence_and_output(private_files, monkeypatch, published):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
    from skeleton.ai.model_runtime.fair_stream_recovery import (
        issue_abandonment_authorization, issue_recovery_authorization, RecoveryAuthorizationDenied,
    )
    from skeleton.ai.model_runtime.fair_stream_execution_journal import ExecutionOutcomeUnknown

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".", operator_recovery_key=b"o" * 32,
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="retire-native",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("retire-native", "alice", InferencePhase.PREFILL, 2, 16))

    def fail(*args, **kwargs):
        raise OSError("simulated interrupted owner")

    with monkeypatch.context() as patch:
        if published:
            patch.setattr(journal, "commit", fail)
        else:
            patch.setattr(NativeLLMRuntime, "generate_sequence", fail)
        with pytest.raises(DispatchUncertain, match="uncertain"):
            service.execute_next(token_budget=2)

    before = session.verify()
    lease = before["checkpoint"]["pending"][0]
    kwargs = dict(recovery_key=b"o" * 32, session_id=SESSION, generation=before["generation"],
                  checkpoint_digest=before["checkpoint_digest"], lease_id=lease["lease_id"],
                  nonce="f" * 32)
    with pytest.raises(RecoveryAuthorizationDenied, match="distinct"):
        service.abandon_uncertain(authorization=issue_recovery_authorization(**kwargs), recovery_key=b"o" * 32)
    approval = issue_abandonment_authorization(**kwargs, evidence_digest="d" * 64)

    if published:
        with pytest.raises(DispatchUncertain, match="abandonment"):
            service.abandon_uncertain(authorization=approval, recovery_key=b"o" * 32)
        assert session.verify() == before
        assert vault._connection.execute("SELECT COUNT(*) FROM local_fair_stream_sealed_results").fetchone() == (1,)
        return

    with pytest.raises(ValueError, match="independent"):
        service.abandon_uncertain(authorization=approval, recovery_key=EXECUTION_KEY)
    status = service.abandon_uncertain(authorization=approval, recovery_key=b"o" * 32)
    assert status.pending_leases == 0 and not status.execution_uncertain
    assert session.verify()["checkpoint"]["requests"] == []
    assert vault._connection.execute("SELECT COUNT(*) FROM local_fair_stream_sealed_results").fetchone() == (0,)
    assert journal.request_exists("retire-native")
    with pytest.raises(ExecutionOutcomeUnknown):
        journal.assert_request_admissible("retire-native")
    with pytest.raises(DispatchUncertain, match="exactly one pending"):
        service.abandon_uncertain(authorization=approval, recovery_key=b"o" * 32)

    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="fresh-native",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("fresh-native", "alice", InferencePhase.PREFILL, 2, 16))
    assert service.execute_next(token_budget=2)["executed"] is True

@pytest.mark.parametrize("role", ["journal", "result", "recovery"])
def test_native_composition_rejects_cross_role_or_wrong_keys(private_files, role):
    runtime, registry, journal, session, result_handle = build(private_files)
    if role == "journal":
        journal._key = b"x" * 32
    result_key = CUSTODY_KEY if role == "result" else RESULT_KEY
    recovery_key = RESULT_KEY if role == "recovery" else b"o" * 32
    before = session.verify()
    with pytest.raises(ValueError, match="authority differs|independent"):
        bind_native_cpu_dispatch_service(
            session=session, runtime=runtime, registry=registry,
            result_handle=result_handle, journal_handle=private_files[1],
            journal=journal, result_key=result_key, operator_recovery_key=recovery_key,
            sampler=LiveStreamBudgetSampler(), storage_path=".",
        )
    assert session.verify() == before
    assert journal._private_handle is None
    assert registry.status()["staged"] == 0

def test_authenticated_native_interrupt_cannot_publish_or_reexecute(private_files, monkeypatch):
    from skeleton.app.offline_native_fair_stream import interrupt_authenticated_native_cpu_prompt
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1], journal=journal,
        result_key=RESULT_KEY, sampler=LiveStreamBudgetSampler(), storage_path=".",
        operator_recovery_key=b"o" * 32,
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="interrupt-native",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("interrupt-native", "alice", InferencePhase.PREFILL, 2, 16))
    calls = []

    def generate(self, sequence, config, *, interrupt=None):
        calls.append(sequence)
        assert not interrupt_authenticated_native_cpu_prompt(
            service=service, authenticated_tenant_id="bob", request_id="interrupt-native",
        )
        assert not interrupt_authenticated_native_cpu_prompt(
            service=service, authenticated_tenant_id="alice", request_id="foreign",
        )
        assert interrupt_authenticated_native_cpu_prompt(
            service=service, authenticated_tenant_id="alice", request_id="interrupt-native",
        )
        assert callable(interrupt)
        interrupt()
        pytest.fail("signalled execution reached completion")

    monkeypatch.setattr(NativeLLMRuntime, "generate_sequence", generate)
    with pytest.raises(DispatchUncertain, match="uncertain"):
        service.execute_next(token_budget=2)
    assert service.status().execution_uncertain
    assert service.status().pending_leases == 1
    assert vault._connection.execute("SELECT COUNT(*) FROM local_fair_stream_sealed_results").fetchone() == (0,)
    assert journal._connection.execute("SELECT state,receipt FROM local_fair_stream_execution_journal").fetchone() == ("running", None)
    assert not interrupt_authenticated_native_cpu_prompt(
        service=service, authenticated_tenant_id="alice", request_id="interrupt-native",
    )
    with pytest.raises(DispatchUncertain):
        service.execute_next(token_budget=2)
    assert len(calls) == 1


def test_queued_cleanup_failure_preserves_item_for_explicit_cancellation(private_files, monkeypatch):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred
    runtime, registry, journal, session, result_handle = build(private_files)
    service, _ = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1], journal=journal,
        result_key=RESULT_KEY, sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry, request_id="cleanup-native",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    service.submit(StreamRequest("cleanup-native", "alice", InferencePhase.PREFILL, 2, 16))
    before = session.verify()
    original = service._guard._cancel_cleanup

    def failed(request_id):
        original(request_id)
        raise OSError("cleanup response lost")

    with monkeypatch.context() as patch:
        patch.setattr(service._guard, "_cancel_cleanup", failed)
        with pytest.raises(DispatchDeferred, match="cleanup"):
            service.cancel("cleanup-native", tenant_id="alice")
    assert session.verify() == before
    assert registry.status()["staged"] == 0
    assert service.cancel("cleanup-native", tenant_id="alice").pending_leases == 0
    assert session.verify()["checkpoint"]["requests"] == []
    assert not journal.request_exists("cleanup-native")

@pytest.mark.parametrize("target", ["journal", "result", "independent"])
def test_unpinned_disk_session_refused_before_native_binding(private_files, tmp_path, target):
    runtime, registry, journal, _, result_handle = build(private_files)
    if target == "independent":
        path = tmp_path / "unpinned.db"
    else:
        handle = private_files[1] if target == "journal" else result_handle
        path = handle.connection.execute("PRAGMA database_list").fetchone()[2]
    connection = sqlite3.connect(path)
    try:
        store = DurableFairStreamStore(
            connection, custody_key=CUSTODY_KEY, execution_key=EXECUTION_KEY,
            session_id=SESSION, whole_request=True,
        )
        session = DurableFairStreamSession.bootstrap(store, SimulatedCAS())
        before = session.verify()
        with pytest.raises(ValueError, match="exact private handle"):
            bind_native_cpu_dispatch_service(
                session=session, runtime=runtime, registry=registry,
                result_handle=result_handle, journal_handle=private_files[1],
                journal=journal, result_key=RESULT_KEY,
                sampler=LiveStreamBudgetSampler(), storage_path=".",
            )
        assert journal._private_handle is None
        assert session.verify() == before
    finally:
        connection.close()


def test_invalid_native_sampler_does_not_stick_journal_binding(private_files):
    from skeleton.app.offline_native_fair_stream import bind_native_cpu_result_owner

    runtime, registry, journal, _, result_handle = build(private_files)
    kwargs = dict(runtime=runtime, registry=registry, journal=journal,
                  result_handle=result_handle, journal_handle=private_files[1],
                  result_key=RESULT_KEY, storage_path=".")
    with pytest.raises(ValueError, match="sampler"):
        bind_native_cpu_result_owner(**kwargs, sampler=object())
    assert journal._private_handle is None
    owner, vault = bind_native_cpu_result_owner(**kwargs, sampler=LiveStreamBudgetSampler())
    assert owner._journal is journal and owner._backend is vault
    assert journal._private_handle is private_files[1]


def test_existing_queued_replay_fence_blocks_new_admission_before_staging(private_files):
    from skeleton.app.offline_native_fair_stream import submit_authenticated_native_cpu_prompt
    from skeleton.ai.model_runtime.fair_stream_session import DispatchPermit
    from skeleton.ai.model_runtime.fair_stream_execution_journal import ExecutionOutcomeUnknown

    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    def submit(rid):
        return submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, registry=registry, runtime=runtime,
            authenticated_tenant_id="alice",
            request=StreamRequest(rid, "alice", InferencePhase.PREFILL, 2, 16),
            prompt="hello", max_output_tokens=2,
        )
    submit("earlier")
    before = session.verify()
    journal.begin(DispatchPermit("d" * 64, "earlier", 1, "c" * 64, 2, 32))
    with pytest.raises(ExecutionOutcomeUnknown, match="already executed"):
        submit("second")
    assert session.verify() == before
    assert registry.status()["staged"] == 1
    assert "second" not in registry._staged and "second" not in registry._used

def test_native_staging_callback_cannot_recursively_execute_or_submit(private_files, monkeypatch):
    from skeleton.app import offline_native_fair_stream as module
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain

    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    original = module.stage_native_cpu_prompt
    request = StreamRequest("outer-stage", "alice", InferencePhase.PREFILL, 2, 16)
    before = session.verify()

    def callback(**kwargs):
        with pytest.raises(DispatchUncertain):
            service.execute_next(token_budget=2)
        with pytest.raises(DispatchUncertain):
            service.submit(StreamRequest("nested-stage", "alice", InferencePhase.PREFILL, 2, 16))
        assert session._store._connection.execute(
            "SELECT generation FROM local_fair_stream_custody",
        ).fetchone() == (before["generation"],)
        original(**kwargs)

    monkeypatch.setattr(module, "stage_native_cpu_prompt", callback)
    status = module.submit_authenticated_native_cpu_prompt(
        service=service, vault=vault, runtime=runtime, registry=registry,
        authenticated_tenant_id="alice", request=request,
        prompt="hello", max_output_tokens=2,
    )
    after = session.verify()
    assert status.generation == before["generation"] + 1
    assert [row["request_id"] for row in after["checkpoint"]["requests"]] == ["outer-stage"]
    assert registry.status()["staged"] == 1
    assert not service._guard._executing
    assert not journal.request_exists("nested-stage")


def test_anchor_change_during_staging_burns_only_new_grant(private_files, monkeypatch):
    from skeleton.app import offline_native_fair_stream as module

    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    original = module.stage_native_cpu_prompt

    def moved(**kwargs):
        original(**kwargs)
        # Model a peer authenticated transition through a separate owner.
        # Direct session calls are an explicitly trusted low-level seam.
        session.plan(MeasuredStreamBudget(8192, 1024, 2, 1, 0, False, "os_probe"))

    monkeypatch.setattr(module, "stage_native_cpu_prompt", moved)
    with pytest.raises(ValueError, match="changed during prompt staging"):
        module.submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="alice",
            request=StreamRequest("moved-stage", "alice", InferencePhase.PREFILL, 2, 16),
            prompt="hello", max_output_tokens=2,
        )
    assert session.verify()["checkpoint"]["requests"] == []
    assert registry.status()["staged"] == 0
    assert "moved-stage" in registry._used
    assert not service._guard._executing
    assert not journal.request_exists("moved-stage")
