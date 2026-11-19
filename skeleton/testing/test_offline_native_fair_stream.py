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
        execution_key=EXECUTION_KEY, session_id=SESSION,
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
    monkeypatch.setattr(service._guard, "submit", broken)
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
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
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
    with pytest.raises(DispatchUncertain, match="uncertain"):
        service.execute_next(token_budget=2)
    assert registry.status()["staged"] == 1
    assert service.status().execution_uncertain


def test_native_queued_cancel_revokes_grant_and_rejects_foreign_owner(private_files):
    from skeleton.app.offline_native_fair_stream import (
        submit_authenticated_native_cpu_prompt, cancel_authenticated_native_cpu_prompt,
    )
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    request = StreamRequest("cancel-test", "alice", InferencePhase.PREFILL, 2, 16)
    submit_authenticated_native_cpu_prompt(
        service=service, vault=vault, runtime=runtime, registry=registry,
        authenticated_tenant_id="alice", request=request, prompt="hello", max_output_tokens=2,
    )
    before = session.verify()
    with pytest.raises(ValueError, match="authorized"):
        cancel_authenticated_native_cpu_prompt(
            service=service, authenticated_tenant_id="bob", request_id=request.request_id,
        )
    assert session.verify() == before
    assert registry.status()["staged"] == 1
    cancel_authenticated_native_cpu_prompt(
        service=service, authenticated_tenant_id="alice", request_id=request.request_id,
    )
    assert registry.status()["staged"] == 0
    assert registry.status()["consumed_or_revoked"] == 1
    assert session.verify()["checkpoint"]["requests"] == []
    assert journal._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 0


def test_interrupted_native_execution_preserves_running_journal_without_result(private_files, monkeypatch):
    from threading import Event, Thread

    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
    from skeleton.app.offline_native_fair_stream import (
        interrupt_authenticated_native_cpu_prompt, submit_authenticated_native_cpu_prompt,
    )

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    req = StreamRequest("stop-native", "alice", InferencePhase.PREFILL, 2, 16)
    submit_authenticated_native_cpu_prompt(
        service=service, vault=vault, runtime=runtime, registry=registry,
        authenticated_tenant_id="alice", request=req, prompt="hello", max_output_tokens=2,
    )
    entered, signalled = Event(), Event()
    outcomes = []
    original = NativeLLMRuntime.generate_sequence

    def paused(self, sequence, config, *, interrupt=None):
        entered.set()
        if not signalled.wait(5):
            raise RuntimeError("test synchronization timed out")
        interrupt()
        return original(self, sequence, config, interrupt=interrupt)

    def stop():
        if entered.wait(5):
            outcomes.append(interrupt_authenticated_native_cpu_prompt(
                service=service, authenticated_tenant_id="bob", request_id=req.request_id,
            ))
            outcomes.append(interrupt_authenticated_native_cpu_prompt(
                service=service, authenticated_tenant_id="alice", request_id=req.request_id,
            ))
        signalled.set()

    monkeypatch.setattr(NativeLLMRuntime, "generate_sequence", paused)
    worker = Thread(target=stop, daemon=True)
    worker.start()
    try:
        with pytest.raises(DispatchUncertain):
            service.execute_next(token_budget=2)
    finally:
        signalled.set()
        worker.join(5)
    assert outcomes == [False, True]
    assert journal._connection.execute(
        "SELECT state FROM local_fair_stream_execution_journal"
    ).fetchone() == ("running",)
    assert vault._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_sealed_results"
    ).fetchone()[0] == 0
    assert service.status().execution_uncertain
    with pytest.raises(DispatchUncertain):
        service.execute_next(token_budget=2)


def test_missing_queued_grant_is_rejected_before_lease_or_journal(private_files, monkeypatch):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred
    from skeleton.app.offline_native_fair_stream import cancel_authenticated_native_cpu_prompt

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    req = StreamRequest("lost-grant", "alice", InferencePhase.PREFILL, 2, 16)
    service.submit(req)
    before = session.verify()
    with pytest.raises(DispatchDeferred, match="prompt authorization"):
        service.execute_next(token_budget=2)
    assert session.verify() == before
    assert not service.status().execution_uncertain
    assert journal._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
    ).fetchone()[0] == 0
    cancel_authenticated_native_cpu_prompt(
        service=service, authenticated_tenant_id="alice", request_id=req.request_id,
    )
    assert service.execute_next(token_budget=2)["state"] == "idle"


def test_known_result_capacity_denial_precedes_plaintext_staging(private_files, monkeypatch):
    from skeleton.ai.model_runtime import fair_stream_result_vault
    from skeleton.app.offline_native_fair_stream import submit_authenticated_native_cpu_prompt

    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    monkeypatch.setattr(fair_stream_result_vault, "MAX_CIPHERTEXT_BYTES", 1)
    before = session.verify()
    with pytest.raises(fair_stream_result_vault.SealedResultUnavailable, match="admission capacity"):
        submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="alice",
            request=StreamRequest("no-room", "alice", InferencePhase.PREFILL, 2, 16),
            prompt="hello", max_output_tokens=2,
        )
    assert session.verify() == before
    assert registry.status()["staged"] == 0
    assert registry.status()["consumed_or_revoked"] == 0


@pytest.mark.parametrize("tamper", [False, True])
def test_native_recovery_after_vault_commit_before_journal_commit(private_files, monkeypatch, tamper):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
    from skeleton.ai.model_runtime.fair_stream_recovery import issue_recovery_authorization
    from skeleton.app.offline_native_fair_stream import submit_authenticated_native_cpu_prompt

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    req = StreamRequest("lost-journal-commit", "alice", InferencePhase.PREFILL, 2, 16)
    submit_authenticated_native_cpu_prompt(
        service=service, vault=vault, runtime=runtime, registry=registry,
        authenticated_tenant_id="alice", request=req, prompt="hello", max_output_tokens=2,
    )

    def fail_commit(*args, **kwargs):
        raise OSError("simulated journal commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(journal, "commit", fail_commit)
        with pytest.raises(DispatchUncertain):
            service.execute_next(token_budget=2)
    assert journal._connection.execute(
        "SELECT state FROM local_fair_stream_execution_journal"
    ).fetchone() == ("running",)
    before = session.verify()
    pending = before["checkpoint"]["pending"][0]
    key = b"z" * 32
    approval = issue_recovery_authorization(
        recovery_key=key, session_id=SESSION, generation=before["generation"],
        checkpoint_digest=before["checkpoint_digest"], lease_id=pending["lease_id"],
        nonce="f" * 32,
    )
    if tamper:
        vault._connection.execute(
            "UPDATE local_fair_stream_sealed_results SET nonce = ?", (b"x" * 12,)
        )
    def never_generate(*args, **kwargs):
        pytest.fail("recovery must not invoke native inference")

    monkeypatch.setattr(NativeLLMRuntime, "generate_sequence", never_generate)
    if tamper:
        with pytest.raises(DispatchUncertain):
            service.reconcile_committed(journal=journal, authorization=approval, recovery_key=key)
        assert session.verify() == before
        assert journal._connection.execute(
            "SELECT state FROM local_fair_stream_execution_journal"
        ).fetchone() == ("running",)
    else:
        status = service.reconcile_committed(journal=journal, authorization=approval, recovery_key=key)
        assert status.pending_leases == 0 and not status.execution_uncertain
        assert journal._connection.execute(
            "SELECT state FROM local_fair_stream_execution_journal"
        ).fetchone() == ("committed",)
        assert session.verify()["checkpoint"]["requests"] == []
        with pytest.raises(DispatchUncertain):
            service.reconcile_committed(journal=journal, authorization=approval, recovery_key=key)


@pytest.mark.parametrize("failure_boundary", ["model", "pressure_clock"])
def test_abandoned_native_failure_unblocks_next_authorized_request(private_files, monkeypatch, failure_boundary):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchUncertain
    from skeleton.ai.model_runtime.fair_stream_execution_journal import ExecutionOutcomeUnknown
    from skeleton.ai.model_runtime.fair_stream_recovery import issue_abandonment_authorization
    from skeleton.app.offline_native_fair_stream import submit_authenticated_native_cpu_prompt

    install_probe(monkeypatch)
    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )

    def submit(request_id):
        return submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="alice",
            request=StreamRequest(request_id, "alice", InferencePhase.PREFILL, 2, 16),
            prompt="hello", max_output_tokens=2,
        )

    submit("failed-native")
    submit("next-native")
    def failure(*args, **kwargs):
        raise RuntimeError("simulated model interruption before durable publication")

    with monkeypatch.context() as patch:
        if failure_boundary == "model":
            patch.setattr(NativeLLMRuntime, "generate_sequence", failure)
        else:
            from skeleton.ai.model_runtime import native_token_pressure
            patch.setattr(native_token_pressure, "monotonic_ns", failure)
        with pytest.raises(DispatchUncertain):
            service.execute_next(token_budget=2)
    state = session.verify()
    lease = state["checkpoint"]["pending"][0]
    assert lease["request_id"] == "failed-native"
    key = b"k" * 32
    approval = issue_abandonment_authorization(
        recovery_key=key, session_id=SESSION, generation=state["generation"],
        checkpoint_digest=state["checkpoint_digest"], lease_id=lease["lease_id"],
        nonce="a" * 32, evidence_digest="b" * 64,
    )
    status = service.abandon_uncertain(authorization=approval, recovery_key=key)
    assert not status.execution_uncertain and status.pending_leases == 0
    assert journal._connection.execute(
        "SELECT state, result_digest, receipt FROM local_fair_stream_execution_journal "
        "WHERE request_id='failed-native'"
    ).fetchone()[:2] == ("running", None)
    assert vault._connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_sealed_results"
    ).fetchone()[0] == 0
    with pytest.raises(ExecutionOutcomeUnknown, match="already executed"):
        submit("failed-native")
    result = service.execute_next(token_budget=2)
    assert result["executed"] is True
    assert result["state"] == "durably_acknowledged"
    assert session.verify()["checkpoint"]["requests"] == []
    assert vault._connection.execute(
        "SELECT request_id FROM local_fair_stream_sealed_results"
    ).fetchall() == [("next-native",)]


def test_native_admission_contention_never_stages_or_burns_prompt(private_files):
    from skeleton.ai.model_runtime.fair_stream_dispatch import DispatchDeferred
    from skeleton.app.offline_native_fair_stream import submit_authenticated_native_cpu_prompt

    runtime, registry, journal, session, result_handle = build(private_files)
    service, vault = bind_native_cpu_dispatch_service(
        session=session, runtime=runtime, registry=registry,
        result_handle=result_handle, journal_handle=private_files[1],
        journal=journal, result_key=RESULT_KEY,
        sampler=LiveStreamBudgetSampler(), storage_path=".",
    )
    before = session.verify()
    def submit():
        return submit_authenticated_native_cpu_prompt(
            service=service, vault=vault, runtime=runtime, registry=registry,
            authenticated_tenant_id="alice",
            request=StreamRequest("contended", "alice", InferencePhase.PREFILL, 2, 16),
            prompt="hello", max_output_tokens=2,
        )
    with service._operation():
        with pytest.raises(DispatchDeferred):
            submit()
    assert registry.status()["staged"] == 0
    assert registry.status()["consumed_or_revoked"] == 0
    assert session.verify() == before
    assert submit().generation == before["generation"] + 1
    assert registry.status()["staged"] == 1
