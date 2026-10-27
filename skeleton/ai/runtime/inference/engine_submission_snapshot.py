"""Verified compiled-input bridge over the existing durable engine authorities.

A per-execution trusted composition provides the native request digest,
the real EngineExecutionService and a *live* source authority. Nothing here
stores a second copy of the conversation or promotes a user-provided root.

This is a scoped bridge, not a global context-id lookup. Engine execution
dispatch must bind the exact LocalInferenceRequest.digest before admission.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Protocol

from skeleton.ai.runtime.inference.canonical_snapshot_reader import (
    CanonicalCompiledInput, CanonicalCompiledSnapshotReader,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError,
    SealedContextIntegrityError,
)


@dataclass(frozen=True, slots=True)
class CurrentSourceCustody:
    tenant_id: str
    actor_id: str
    context_id: str
    source_snapshot: tuple[tuple[str, str], ...]
    version: int
    revoked: bool = False


class CurrentSourceAuthority(Protocol):
    async def inspect(
        self, *, tenant_id: str, actor_id: str, context_id: str
    ) -> CurrentSourceCustody: ...


class EngineSubmissionCompiledInputLoader:
    """Resolve ONE pinned request through canonical durable engine custody.

    A production caller constructs one per dispatched inference using the
    already-authenticated execution_id and independently materialized native
    request digest. The source inspector must read current conversation and
    segment custody; it cannot return a copy of the untrusted handoff.
    """

    def __init__(
        self, *,
        service: Any,
        execution_id: str,
        native_request_digest: str,
        source_authority: CurrentSourceAuthority,
    ) -> None:
        if (not isinstance(execution_id, str) or not execution_id
                or not isinstance(native_request_digest, str)
                or len(native_request_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in native_request_digest)):
            raise SealedContextBoundaryError("bound engine native request identity required")
        if not callable(getattr(getattr(service, "submissions", None),
                                 "get_by_execution_id", None)):
            raise SealedContextBoundaryError("canonical engine submission owner required")
        if not callable(getattr(getattr(service, "repository", None), "get", None)):
            raise SealedContextBoundaryError("canonical engine execution repository required")
        if not callable(getattr(source_authority, "inspect", None)):
            raise SealedContextBoundaryError("live canonical source authority required")
        self._service = service
        self._execution_id = execution_id
        self._native_request_digest = native_request_digest
        self._source_authority = source_authority

    @staticmethod
    def _read_owned(service: Any, execution_id: str):
        stored = service.submissions.get_by_execution_id(execution_id)
        execution = service.repository.get(execution_id)
        return stored, execution

    async def read(
        self, *, tenant_id: str, context_id: str, request_digest: str,
    ) -> CanonicalCompiledInput:
        if request_digest != self._native_request_digest:
            raise SealedContextBoundaryError("native request changed from admitted execution")
        try:
            stored, execution = await asyncio.to_thread(
                self._read_owned, self._service, self._execution_id,
            )
        except Exception as exc:
            raise SealedContextBoundaryError("durable engine execution unavailable") from exc
        if stored is None or execution is None:
            raise SealedContextBoundaryError("canonical engine submission missing")
        try:
            command = stored.command
            handoff = command.compiled_context
            operation = command.operation
            if (handoff.execution_id != self._execution_id
                    or execution.request.execution_id != self._execution_id
                    or command.execution_request.identity_digest != execution.request.identity_digest
                    or execution.operation_id != operation.operation_id
                    or handoff.operation_id != operation.operation_id
                    or handoff.tenant_id != tenant_id
                    or operation.tenant_id != tenant_id
                    or not isinstance(operation.actor_id, str)
                    or not operation.actor_id
                    or handoff.context_id != context_id
                    or execution.cancellation_requested
                    or execution.terminal):
                raise SealedContextBoundaryError("engine submission scope or lifecycle changed")
            # EngineContextHandoff has independently revalidated its canonical
            # digest when reconstructed from durable serialized bytes.
            if type(execution.version) is not int or execution.version < 1:
                raise SealedContextBoundaryError("durable execution version invalid")
            # Snapshot detached scalar identities BEFORE crossing an await.
            # Mutable ORM/fake objects can otherwise change underneath the
            # original reference and hide a concurrent cancellation.
            initial_owner = (
                execution.version,
                getattr(execution, "checkpoint_version", None),
                execution.cancellation_requested,
                execution.terminal,
                execution.operation_id,
                getattr(command, "submission_digest", None),
                handoff.handoff_digest,
            )
            custody = await self._source_authority.inspect(
                tenant_id=tenant_id, actor_id=operation.actor_id,
                context_id=context_id,
            )
            if (not isinstance(custody, CurrentSourceCustody)
                    or custody.revoked is not False
                    or custody.tenant_id != tenant_id
                    or custody.actor_id != operation.actor_id
                    or custody.context_id != context_id
                    or type(custody.version) is not int or custody.version < 1
                    or custody.source_snapshot != handoff.source_snapshot):
                raise SealedContextIntegrityError("canonical conversation custody changed or was revoked")
            # Source I/O is an async suspension point. Re-read the original
            # durable owners before admitting any prompt bytes. A changed
            # execution/checkpoint, cancellation, deletion, or replaced
            # submission must not inherit the earlier source inspection.
            try:
                verified_stored, verified_execution = await asyncio.to_thread(
                    self._read_owned, self._service, self._execution_id,
                )
                verified_command = verified_stored.command
                verified_handoff = verified_command.compiled_context
                confirmed_owner = (
                    verified_execution.version,
                    getattr(verified_execution, "checkpoint_version", None),
                    verified_execution.cancellation_requested,
                    verified_execution.terminal,
                    verified_execution.operation_id,
                    getattr(verified_command, "submission_digest", None),
                    verified_handoff.handoff_digest,
                )
                if (confirmed_owner != initial_owner
                        or verified_execution.cancellation_requested
                        or verified_execution.terminal
                        or verified_command.execution_request.identity_digest
                           != execution.request.identity_digest
                        or verified_command.operation.tenant_id != tenant_id
                        or verified_command.operation.actor_id != operation.actor_id
                        or verified_handoff.context_id != context_id):
                    raise SealedContextBoundaryError(
                        "durable engine owner changed during source inspection"
                    )
            except SealedContextBoundaryError:
                raise
            except Exception as exc:
                raise SealedContextBoundaryError("durable engine recheck unavailable") from exc
            # The owner recheck above awaits worker-thread I/O. The source
            # can independently change while that I/O runs, so a single
            # earlier source inspection is not a coherent two-owner snapshot.
            # Compare detached custody values after the owner recheck and
            # deny on version, revocation, actor, or segment replacement.
            try:
                confirmed_custody = await self._source_authority.inspect(
                    tenant_id=tenant_id, actor_id=operation.actor_id,
                    context_id=context_id,
                )
            except Exception as exc:
                raise SealedContextBoundaryError(
                    "canonical source custody recheck unavailable"
                ) from exc
            if (
                type(confirmed_custody) is not CurrentSourceCustody
                or confirmed_custody != custody
                or confirmed_custody.revoked is not False
            ):
                raise SealedContextIntegrityError(
                    "canonical source custody changed during durable owner recheck"
                )
            # A single integer pins BOTH independent version domains for
            # TrustedContextSnapshot. This is an opaque equality token, not
            # a strictly increasing counter.
            identity = json.dumps(
                [execution.version, custody.version, handoff.handoff_digest],
                separators=(",", ":"), ensure_ascii=True, allow_nan=False,
            ).encode("ascii")
            revision = int.from_bytes(sha256(identity).digest()[:16], "big") or 1
            return CanonicalCompiledInput(
                tenant_id=tenant_id, context_id=context_id,
                request_digest=request_digest,
                source_version=revision,
                instructions=handoff.instructions,
                history=handoff.history,
                prompt=handoff.prompt,
            )
        except (SealedContextBoundaryError, SealedContextIntegrityError):
            raise
        except Exception as exc:
            raise SealedContextBoundaryError("canonical engine binding verification failed") from exc


@dataclass(frozen=True, slots=True)
class _ExecutingScope:
    execution_id: str
    tenant_id: str
    context_id: str
    request_digest: str
    owner_task: asyncio.Task[Any]


class ScopedEngineCompiledSnapshotReader:
    """One startup-owned reader with per-task durable execution custody.

    A protected adapter opens the scope inside its own guarded-generation
    task. A child task inheriting the ContextVar cannot use the same binding,
    and the finally block revokes it after postflight, timeout or cancellation.
    No cross-request global mapping or user-supplied receipt is retained.
    """

    def __init__(
        self, *, service: Any, source_authority: CurrentSourceAuthority,
        policy_sha256: str,
    ) -> None:
        if not callable(getattr(getattr(service, "submissions", None),
                                 "get_by_execution_id", None)):
            raise SealedContextBoundaryError("durable engine submissions unavailable")
        if not callable(getattr(getattr(service, "repository", None), "get", None)):
            raise SealedContextBoundaryError("durable engine repository unavailable")
        if not callable(getattr(source_authority, "inspect", None)):
            raise SealedContextBoundaryError("current canonical source inspector required")
        if (not isinstance(policy_sha256, str) or len(policy_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in policy_sha256)):
            raise SealedContextBoundaryError("trusted instruction policy digest required")
        self._service = service
        self._source_authority = source_authority
        self._policy_sha256 = policy_sha256
        self._scope: ContextVar[_ExecutingScope | None] = ContextVar(
            "skeleton.engine.compiled_snapshot_scope", default=None,
        )

    async def prepare_provider(self, provider_request: Any) -> str:
        """Resolve the native Merkle root without equating it to compiler digest.

        The public provider context_digest remains the compiler's independent
        binding. The local model's context_digest must be derived only from
        owner-backed canonical bytes after checking the complete handoff and
        fresh source custody. The subsequent guarded read repeats that proof.
        """
        from skeleton.context.pre_delivery_guard import merkle_root, request_parts
        from skeleton.provider_runtime import ProviderRequest

        if not isinstance(provider_request, ProviderRequest):
            raise SealedContextBoundaryError("protected provider envelope required")
        tenant_id = provider_request.tenant_id
        context_id = provider_request.context_id
        execution_id = provider_request.execution_id
        compiled = provider_request.context_digest
        if any(not isinstance(v, str) or not v for v in (
            tenant_id, context_id, execution_id,
        )):
            raise SealedContextBoundaryError("provider execution authority incomplete")
        if (not isinstance(compiled, str) or len(compiled) != 64
                or any(ch not in "0123456789abcdef" for ch in compiled)):
            raise SealedContextBoundaryError("compiled handoff digest missing")
        try:
            stored, execution = await asyncio.to_thread(
                EngineSubmissionCompiledInputLoader._read_owned,
                self._service, execution_id,
            )
            if stored is None or execution is None:
                raise SealedContextBoundaryError("durable handoff missing")
            handoff = stored.command.compiled_context
            operation = stored.command.operation
            exact_history = tuple(
                (message.role, message.content) for message in provider_request.history
            )
            if (handoff.context_digest != compiled
                    or handoff.tenant_id != tenant_id
                    or handoff.context_id != context_id
                    or handoff.execution_id != execution_id
                    or operation.tenant_id != tenant_id
                    or (provider_request.operation_id is not None
                        and provider_request.operation_id != operation.operation_id)
                    or handoff.compiler_version != provider_request.context_compiler_version
                    or handoff.source_snapshot != provider_request.context_source_snapshot
                    or handoff.instructions != provider_request.instructions
                    or handoff.prompt != provider_request.prompt
                    or handoff.history != exact_history):
                raise SealedContextIntegrityError(
                    "provider prompt or compiler binding differs from durable handoff"
                )
            # This staging digest is not the native request digest: native
            # serialization happens AFTER the authenticated Merkle projection.
            staging_digest = sha256(
                ("skeleton.engine.bootstrap.v1:" + execution_id + ":" + compiled)
                .encode("utf-8")
            ).hexdigest()
            source_loader = EngineSubmissionCompiledInputLoader(
                service=self._service, execution_id=execution_id,
                native_request_digest=staging_digest,
                source_authority=self._source_authority,
            )
            snapshot = await CanonicalCompiledSnapshotReader(
                loader=source_loader, policy_sha256=self._policy_sha256,
            ).resolve(
                tenant_scope_id=tenant_id, context_id=context_id,
                request_digest=staging_digest,
            )
            return snapshot.root
        except (SealedContextBoundaryError, SealedContextIntegrityError):
            raise
        except Exception as exc:
            raise SealedContextBoundaryError("durable provider preflight unavailable") from exc

    @contextmanager
    def bind_execution(
        self, *, execution_id: str, tenant_id: str,
        context_id: str, request_digest: str,
    ):
        """Bind an exact native request for one guarded provider invocation."""
        if self._scope.get() is not None:
            raise SealedContextBoundaryError("nested durable snapshot scope is forbidden")
        task = asyncio.current_task()
        if task is None:
            raise SealedContextBoundaryError("durable snapshot scope requires asyncio task")
        if any(not isinstance(value, str) or not value for value in (
            execution_id, tenant_id, context_id,
        )):
            raise SealedContextBoundaryError("durable execution scope is incomplete")
        if (not isinstance(request_digest, str) or len(request_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in request_digest)):
            raise SealedContextBoundaryError("native request digest is invalid")
        token = self._scope.set(_ExecutingScope(
            execution_id, tenant_id, context_id, request_digest, task,
        ))
        try:
            yield
        finally:
            self._scope.reset(token)

    async def resolve(
        self, *, tenant_scope_id: str, context_id: str, request_digest: str,
    ):
        bound = self._scope.get()
        if (bound is None or asyncio.current_task() is not bound.owner_task
                or bound.tenant_id != tenant_scope_id
                or bound.context_id != context_id
                or bound.request_digest != request_digest):
            raise SealedContextBoundaryError("durable snapshot is not bound to executing request")
        loader = EngineSubmissionCompiledInputLoader(
            service=self._service, execution_id=bound.execution_id,
            native_request_digest=bound.request_digest,
            source_authority=self._source_authority,
        )
        return await CanonicalCompiledSnapshotReader(
            loader=loader, policy_sha256=self._policy_sha256,
        ).resolve(
            tenant_scope_id=tenant_scope_id, context_id=context_id,
            request_digest=request_digest,
        )


__all__ = [
    "CurrentSourceCustody", "CurrentSourceAuthority",
    "EngineSubmissionCompiledInputLoader",
    "ScopedEngineCompiledSnapshotReader",
]
