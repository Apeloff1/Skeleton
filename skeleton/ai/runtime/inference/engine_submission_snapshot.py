"""Verified compiled-input bridge over the existing durable engine authorities.

A per-execution trusted composition provides the native request digest,
the real EngineExecutionService and a *live* source authority. Nothing here
stores a second copy of the conversation or promotes a user-provided root.

This is a scoped bridge, not a global context-id lookup. Engine execution
dispatch must bind the exact LocalInferenceRequest.digest before admission.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Protocol

from skeleton.ai.runtime.inference.canonical_snapshot_reader import CanonicalCompiledInput
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError,
    SealedContextIntegrityError,
)


@dataclass(frozen=True, slots=True)
class CurrentSourceCustody:
    tenant_id: str
    context_id: str
    source_snapshot: tuple[tuple[str, str], ...]
    version: int
    revoked: bool = False


class CurrentSourceAuthority(Protocol):
    async def inspect(
        self, *, tenant_id: str, context_id: str
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
                tenant_id=tenant_id, context_id=context_id,
            )
            if (not isinstance(custody, CurrentSourceCustody)
                    or custody.revoked is not False
                    or custody.tenant_id != tenant_id
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
                        or verified_handoff.context_id != context_id):
                    raise SealedContextBoundaryError(
                        "durable engine owner changed during source inspection"
                    )
            except SealedContextBoundaryError:
                raise
            except Exception as exc:
                raise SealedContextBoundaryError("durable engine recheck unavailable") from exc
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


__all__ = [
    "CurrentSourceCustody", "CurrentSourceAuthority",
    "EngineSubmissionCompiledInputLoader",
]
