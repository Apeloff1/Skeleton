"""Canonical application seam for CPU-native encrypted fair-stream results.

The caller provides the authenticated NativeLLMRuntime, independent private
result/journal handles, external monotonic session anchor, and operator-owned
keys. No default secrets, GPU qualification or automatic restart replay.
"""
from __future__ import annotations

import os
import stat

from skeleton.ai.model_runtime.fair_stream_execution_journal import (
    FairStreamExecutionJournal, JournaledExecutionOwner,
)
from skeleton.ai.model_runtime.fair_stream_result_vault import (
    SealedFairStreamResultVault,
)
from skeleton.ai.model_runtime.native_fair_stream_backend import (
    NativeFairStreamBackend, NativePromptRegistry, pin_native_prompt,
)
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.fair_stream_session import DurableFairStreamSession
from skeleton.app.offline_dispatch_bridge import OfflineAdaptiveDispatchService
from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteHandle
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.native_token_pressure import NativeTokenPressureGuard


def bind_native_cpu_result_owner(
    *, runtime: NativeLLMRuntime, registry: NativePromptRegistry,
    result_handle: PrivateSQLiteHandle, journal: FairStreamExecutionJournal,
    result_key: bytes, sampler: LiveStreamBudgetSampler, storage_path: str,
) -> tuple[JournaledExecutionOwner, SealedFairStreamResultVault]:
    """Bind actual native CPU inference to signed journal + AES-GCM vault.

    The journal and result store must be different physical SQLite files.
    The app must also supply a durable high-watermark and an authenticated
    dispatch service, and must keep all handles alive until quiescent.
    """
    if type(journal) is not FairStreamExecutionJournal:
        raise ValueError("canonical signed execution journal required")
    if type(result_handle) is not PrivateSQLiteHandle or result_handle._closed:
        raise ValueError("canonical private result database required")
    if journal._connection is result_handle.connection:
        raise ValueError("result and execution journal must be separate connections")
    db_rows = journal._connection.execute("PRAGMA database_list").fetchall()
    if len(db_rows) != 1 or db_rows[0][1] != "main" or not db_rows[0][2]:
        raise ValueError("file-backed private execution journal required")
    result_handle.assert_current()
    journal_info = os.stat(db_rows[0][2], follow_symlinks=False)
    if (not stat.S_ISREG(journal_info.st_mode)
            or journal_info.st_uid != os.geteuid()
            or journal_info.st_nlink != 1
            or journal_info.st_mode & 0o777 != 0o600):
        raise ValueError("untrusted private execution journal inode")
    result_info = os.fstat(result_handle._file_fd)
    if (journal_info.st_dev, journal_info.st_ino) == (
        result_info.st_dev, result_info.st_ino,
    ):
        raise ValueError("result and execution journal must use different inodes")
    if registry.session_id != journal.session_id:
        raise ValueError("native prompt and execution journal session mismatch")
    backend = NativeFairStreamBackend(
        runtime, registry,
        pressure_guard=NativeTokenPressureGuard(sampler, storage_path=storage_path),
    )
    vault = SealedFairStreamResultVault(
        result_handle, session_id=journal.session_id,
        model_digest=backend.model_digest,
        tokenizer_digest=backend.tokenizer_digest,
        result_key=result_key, backend=backend,
    )
    return JournaledExecutionOwner(journal, vault), vault


def stage_native_cpu_prompt(
    *, runtime: NativeLLMRuntime, registry: NativePromptRegistry,
    request_id: str, tenant_id: str, prompt: str, max_output_tokens: int,
) -> None:
    """Called only after the app authenticates tenant and request ownership.

    Register before submitting the matching StreamRequest. A failed submit
    must revoke this in-memory grant; never silently regenerate on restart.
    """
    pinned = pin_native_prompt(
        runtime, session_id=registry.session_id, request_id=request_id,
        tenant_id=tenant_id, prompt=prompt,
        max_output_tokens=max_output_tokens,
    )
    registry.stage(pinned)


def bind_native_cpu_dispatch_service(
    *, session: DurableFairStreamSession, runtime: NativeLLMRuntime,
    registry: NativePromptRegistry, result_handle: PrivateSQLiteHandle,
    journal: FairStreamExecutionJournal, result_key: bytes,
    sampler: LiveStreamBudgetSampler, storage_path: str,
) -> tuple[OfflineAdaptiveDispatchService, SealedFairStreamResultVault]:
    """End-to-end app composition without manufacturing keys or CPU telemetry.

    Caller owns a verified session, an independent durable CAS anchor, and
    three distinct custody roles (session, journal, encrypted result).
    This method never bootstraps or resets durable state on restart.
    """
    if type(session) is not DurableFairStreamSession:
        raise ValueError("canonical authenticated dispatch session required")
    state = session.verify()
    if state.get("session_id") != registry.session_id:
        raise ValueError("app session and native prompt registry mismatch")
    owner, vault = bind_native_cpu_result_owner(
        runtime=runtime, registry=registry, result_handle=result_handle,
        journal=journal, result_key=result_key,
        sampler=sampler, storage_path=storage_path,
    )
    service = OfflineAdaptiveDispatchService(
        session, owner, sampler=sampler, storage_path=storage_path,
    )
    return service, vault


def native_cpu_prompt_memory_status(
    registry: NativePromptRegistry,
) -> dict[str, int | str]:
    """Read only aggregate staged RAM use, never tenant IDs or plaintext.

    The app authenticates the operator before exposing this telemetry. This
    snapshot does not reserve physical memory or certify CPU/GPU hardware.
    """
    if type(registry) is not NativePromptRegistry:
        raise ValueError("canonical native prompt registry required")
    return registry.budget_status()
