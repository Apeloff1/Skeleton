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
