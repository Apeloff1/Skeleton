"""Canonical application seam for CPU-native encrypted fair-stream results.

The caller provides the authenticated NativeLLMRuntime, independent private
result/journal handles, external monotonic session anchor, and operator-owned
keys. No default secrets, GPU qualification or automatic restart replay.
"""
from __future__ import annotations

import hmac
import os

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
from skeleton.ai.model_runtime.fair_stream_queue import StreamRequest
from skeleton.ai.model_runtime.fair_stream_session import DurableFairStreamSession
from skeleton.app.offline_dispatch_bridge import OfflineAdaptiveDispatchService
from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteHandle
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.native_token_pressure import NativeTokenPressureGuard


def bind_native_cpu_result_owner(
    *, runtime: NativeLLMRuntime, registry: NativePromptRegistry,
    result_handle: PrivateSQLiteHandle, journal_handle: PrivateSQLiteHandle,
    journal: FairStreamExecutionJournal,
    result_key: bytes, sampler: LiveStreamBudgetSampler, storage_path: str,
) -> tuple[JournaledExecutionOwner, SealedFairStreamResultVault]:
    """Bind actual native CPU inference to signed journal + AES-GCM vault.

    The journal and result store must be different physical SQLite files.
    The app must also supply a durable high-watermark and an authenticated
    dispatch service, and must keep all handles alive until quiescent.
    """
    if type(journal) is not FairStreamExecutionJournal:
        raise ValueError("canonical signed execution journal required")
    if type(registry) is not NativePromptRegistry or type(runtime) is not NativeLLMRuntime:
        raise ValueError("canonical native runtime and prompt registry required")
    journal._require_owner_process()
    registry._require_owner_process()
    if type(result_key) is not bytes or len(result_key) != 32 or hmac.compare_digest(result_key, journal._key):
        raise ValueError("independent result encryption key required")
    if type(result_handle) is not PrivateSQLiteHandle or result_handle._closed:
        raise ValueError("canonical private result database required")
    if journal._connection is result_handle.connection:
        raise ValueError("result and execution journal must be separate connections")
    if type(journal_handle) is not PrivateSQLiteHandle or journal_handle._closed:
        raise ValueError("canonical private execution journal handle required")
    if journal_handle.connection is not journal._connection:
        raise ValueError("journal connection and pinned inode handle mismatch")
    # Both roles must be descriptor-pinned, not pathname-only stat checks.
    # Recheck the exact opened inode, parent directory and SQLite backing
    # before any model backend or encrypted result store is constructed.
    result_handle.assert_current()
    journal_handle.assert_current()
    journal_info = os.fstat(journal_handle._file_fd)
    result_info = os.fstat(result_handle._file_fd)
    if (journal_info.st_dev, journal_info.st_ino) == (
        result_info.st_dev, result_info.st_ino,
    ):
        raise ValueError("result and execution journal must use different inodes")
    if registry.session_id != journal.session_id:
        raise ValueError("native prompt and execution journal session mismatch")
    if journal._private_handle is not None:
        raise ValueError("journal already bound to native owner")
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
    # Bind only after all runtime, sampler and vault validation succeeds.
    # An invalid composition must not leave the journal permanently bound.
    journal.bind_private_handle(journal_handle)
    return JournaledExecutionOwner(journal, vault), vault


def stage_native_cpu_prompt(
    *, runtime: NativeLLMRuntime, registry: NativePromptRegistry,
    request_id: str, tenant_id: str, prompt: str, max_output_tokens: int,
) -> None:
    """Called only after the app authenticates tenant and request ownership.

    Register before submitting the matching StreamRequest. A failed submit
    must revoke this in-memory grant; never silently regenerate on restart.
    """
    if type(registry) is not NativePromptRegistry:
        raise ValueError("canonical native prompt registry required")
    registry._require_owner_process()
    pinned = pin_native_prompt(
        runtime, session_id=registry.session_id, request_id=request_id,
        tenant_id=tenant_id, prompt=prompt,
        max_output_tokens=max_output_tokens,
    )
    registry.stage(pinned)


def bind_native_cpu_dispatch_service(
    *, session: DurableFairStreamSession, runtime: NativeLLMRuntime,
    registry: NativePromptRegistry, result_handle: PrivateSQLiteHandle,
    journal_handle: PrivateSQLiteHandle,
    journal: FairStreamExecutionJournal, result_key: bytes,
    sampler: LiveStreamBudgetSampler, storage_path: str,
    operator_recovery_key: bytes | None = None,
) -> tuple[OfflineAdaptiveDispatchService, SealedFairStreamResultVault]:
    """End-to-end app composition without manufacturing keys or CPU telemetry.

    Caller owns a verified session, an independent durable CAS anchor, and
    three distinct custody roles (session, journal, encrypted result).
    This method never bootstraps or resets durable state on restart. Operator
    recovery is disabled unless an independent key is provided by trusted
    composition and re-provisioned on restart.
    """
    if type(session) is not DurableFairStreamSession:
        raise ValueError("canonical authenticated dispatch session required")
    if type(registry) is not NativePromptRegistry or type(runtime) is not NativeLLMRuntime:
        raise ValueError("canonical native runtime and prompt registry required")
    registry._require_owner_process()
    state = session.verify()
    if not session.whole_request:
        raise ValueError("native CPU dispatch requires an authenticated whole-request session")
    if state.get("session_id") != registry.session_id:
        raise ValueError("app session and native prompt registry mismatch")
    # Three distinct stores are required, even when the session uses a
    # caller-owned trusted connection rather than a private file handle.
    if (type(journal) is not FairStreamExecutionJournal
            or type(result_handle) is not PrivateSQLiteHandle
            or type(journal_handle) is not PrivateSQLiteHandle):
        raise ValueError("canonical native custody components required")
    session_store = session._store
    if not hmac.compare_digest(session_store._execution_key, journal._key):
        raise ValueError("journal execution authority differs from authenticated session")
    keys = (session_store._custody_key, session_store._execution_key, journal._key)
    if (type(result_key) is not bytes or len(result_key) != 32
            or any(hmac.compare_digest(result_key, key) for key in keys)):
        raise ValueError("independent result encryption key required")
    if operator_recovery_key is not None and (
        type(operator_recovery_key) is not bytes or not 32 <= len(operator_recovery_key) <= 128
        or any(hmac.compare_digest(operator_recovery_key, key) for key in (*keys, result_key))
    ):
        raise ValueError("independent operator recovery key required")
    if (session_store._connection is journal._connection
            or session_store._connection is result_handle.connection
            or session_store._connection is journal_handle.connection):
        raise ValueError("session and execution custody must be separate connections")
    if session_store._private_handle is None:
        # The legacy in-memory test seam has no file identity. Disk-backed
        # custody must retain a verified descriptor, not merely a different
        # Python connection to a potentially identical SQLite file.
        databases = session_store._connection.execute("PRAGMA database_list").fetchall()
        main = [row for row in databases if row[1] == "main"]
        if (len(main) != 1 or main[0][2] != ""
                or any(row[1] not in {"main", "temp"} for row in databases)):
            raise ValueError("disk session custody requires an exact private handle")
    else:
        session_store._private_handle.assert_current()
        result_handle.assert_current()
        journal_handle.assert_current()
        session_info = os.fstat(session_store._private_handle._file_fd)
        for handle in (result_handle, journal_handle):
            info = os.fstat(handle._file_fd)
            if (session_info.st_dev, session_info.st_ino) == (info.st_dev, info.st_ino):
                raise ValueError("session and execution custody must use different inodes")
    owner, vault = bind_native_cpu_result_owner(
        runtime=runtime, registry=registry, result_handle=result_handle,
        journal_handle=journal_handle, journal=journal, result_key=result_key,
        sampler=sampler, storage_path=storage_path,
    )
    def verify_queued_authority(snapshot: dict[str, object]) -> None:
        requests = snapshot["checkpoint"]["requests"]
        registry.verify_queued(requests)
        # Capacity is checked once per ledger, not once per queued peer.
        # Both remain observational; transactional claims still fence races.
        identities = tuple(request["request_id"] for request in requests)
        if identities:
            journal.assert_requests_admissible(identities)
            vault.assert_requests_admissible(identities)

    def prepare_native_request(request: StreamRequest) -> StreamRequest:
        if journal.request_exists(request.request_id):
            raise ValueError("request already has durable execution custody")
        snapshot = session.verify()
        queued = snapshot["checkpoint"]["requests"]
        registry.verify_queued(queued)
        identities = tuple(row["request_id"] for row in queued) + (request.request_id,)
        journal.assert_requests_admissible(identities)
        vault.assert_requests_admissible(identities)
        return registry.bind_request(request)

    service = OfflineAdaptiveDispatchService(
        session, owner, sampler=sampler, storage_path=storage_path,
        whole_request=True, queued_authority=verify_queued_authority,
        cancel_cleanup=registry.discard_cancelled, prepare_request=prepare_native_request,
        operator_recovery_key=operator_recovery_key,
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


def submit_authenticated_native_cpu_prompt(
    *, service: OfflineAdaptiveDispatchService,
    vault: SealedFairStreamResultVault,
    runtime: NativeLLMRuntime, registry: NativePromptRegistry,
    authenticated_tenant_id: str, request: StreamRequest,
    prompt: str, max_output_tokens: int,
):
    """Stage and submit as one app operation, burning grants on submission error.

    authenticated_tenant_id MUST originate from the app's verified principal,
    never from a request body. This operation is not a replacement for the
    durable journal's one-use request identity or the live OS pressure guard.
    The returned status is derived from the authenticated admission transition.
    Any uncertain mutation burns the grant and requires reconciliation.
    """
    if (type(service) is not OfflineAdaptiveDispatchService
            or type(vault) is not SealedFairStreamResultVault
            or type(runtime) is not NativeLLMRuntime
            or type(registry) is not NativePromptRegistry
            or type(request) is not StreamRequest):
        raise ValueError("canonical authenticated native CPU app components required")
    if (type(authenticated_tenant_id) is not str
            or request.tenant_id != authenticated_tenant_id):
        raise ValueError("authenticated tenant does not own stream request")
    if (type(max_output_tokens) is not int
            or not 1 <= request.remaining_tokens <= min(max_output_tokens, 8192)):
        raise ValueError("native output grant cannot cover requested stream")
    # Reject an unrelated registry, runtime, vault or session BEFORE staging
    # plaintext. A caller must use the exact owner bound during app startup.
    owner = service._guard._owner
    if (type(owner) is not JournaledExecutionOwner
            or owner._backend is not vault
            or type(vault._backend) is not NativeFairStreamBackend
            or vault._backend.registry is not registry
            or vault._backend.runtime is not runtime):
        raise ValueError("native app ownership binding mismatch")
    # Serialize staging with planning/cancellation on this trusted service.
    # A peer CAS change is still fenced by the exact anchor during submit.
    with service._operation():
        guard = service._guard
        guard._require_no_pending()
        # RLock is deliberately shared with service.submit, but a callback
        # invoked during model admission must never recursively start work.
        guard._executing = True
        staged = False
        try:
            try:
                snapshot = service._session.verify()
                if snapshot.get("session_id") != registry.session_id:
                    raise ValueError("native app ownership binding mismatch")
                if (request.authorization_digest is not None
                        or any(row["request_id"] == request.request_id
                               for row in snapshot["checkpoint"]["requests"])
                        or owner._journal.request_exists(request.request_id)):
                    raise ValueError("request already has durable admission or execution custody")
                queued = snapshot["checkpoint"]["requests"]
                registry.verify_queued(queued)
                identities = tuple(row["request_id"] for row in queued) + (request.request_id,)
                owner._journal.assert_requests_admissible(identities)
                vault.assert_requests_admissible(identities)
                stage_native_cpu_prompt(
                    runtime=runtime, registry=registry, request_id=request.request_id,
                    tenant_id=authenticated_tenant_id, prompt=prompt,
                    max_output_tokens=max_output_tokens,
                )
                staged = True
                if service._session.verify() != snapshot:
                    raise ValueError("durable admission changed during prompt staging")
            finally:
                guard._executing = False
            return service.submit(request)
        except BaseException:
            if staged:
                # Do not burn a pre-existing grant when stage itself rejects
                # a duplicate acquisition. Our own successful stage must be
                # scrubbed even when the independent clock is unavailable.
                registry.discard_cancelled(request.request_id)
            raise


def interrupt_authenticated_native_cpu_prompt(
    *, service: OfflineAdaptiveDispatchService, authenticated_tenant_id: str,
    request_id: str,
) -> bool:
    """Request a cooperative stop without acquiring dispatch or database locks.

    True acknowledges the matching active generation's signal, not a durable
    cancellation. The running journal still requires explicit reconciliation.
    The tenant must be supplied by the verified application principal.
    """
    if type(service) is not OfflineAdaptiveDispatchService:
        raise ValueError("canonical native dispatch service required")
    if type(authenticated_tenant_id) is not str or not authenticated_tenant_id:
        raise ValueError("authenticated tenant required")
    service._guard._require_owner_process()
    owner = service._guard._owner
    if type(owner) is not JournaledExecutionOwner:
        raise ValueError("canonical native owner required")
    vault = owner._backend
    if type(vault) is not SealedFairStreamResultVault or type(vault._backend) is not NativeFairStreamBackend:
        raise ValueError("canonical native backend required")
    return vault._backend.request_interrupt(
        tenant_id=authenticated_tenant_id, request_id=request_id,
    )
