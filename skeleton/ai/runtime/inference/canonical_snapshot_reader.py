"""Bounded, revocation-aware snapshot projection from canonical compiled input.

The application supplies a scoped loader that reads immutable **server-owned**
compiled-inference state. This module never trusts a client-provided Merkle
root, policy digest, transcript, or context version. It also does not create
a replacement conversation database or assign source authority to an archive.

A production loader must bind request_digest to the exact admitted inference
request and read the current canonical thread/execution version on every call.
A missing, deleted, revoked or concurrently changed record denies delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol

from skeleton.context.pre_delivery_guard import (
    TrustedContextSnapshot, merkle_root,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError,
)


@dataclass(frozen=True, slots=True)
class CanonicalCompiledInput:
    """Server-persisted input fields, not a client-supplied snapshot proof."""

    tenant_id: str
    context_id: str
    request_digest: str
    source_version: int
    instructions: str
    history: tuple[tuple[str, str], ...]
    prompt: str
    revoked: bool = False


class CanonicalCompiledInputLoader(Protocol):
    async def read(
        self, *, tenant_id: str, context_id: str, request_digest: str,
    ) -> CanonicalCompiledInput | None: ...


class CanonicalCompiledSnapshotReader:
    """Rebuild a snapshot from exact persisted prompt spans at EACH admission.

    This reader is a derived verifier. The application's loader retains tenant
    authorization, version and revocation authority. A trusted policy digest is
    pinned outside the client/model input, so canonical data may not quietly
    rewrite the system instruction policy.
    """

    def __init__(self, *, loader: CanonicalCompiledInputLoader, policy_sha256: str) -> None:
        if not callable(getattr(loader, "read", None)):
            raise SealedContextBoundaryError("canonical compiled input loader required")
        if (not isinstance(policy_sha256, str) or len(policy_sha256) != 64
                or any(c not in "0123456789abcdef" for c in policy_sha256)):
            raise SealedContextBoundaryError("independently pinned policy digest required")
        self._loader = loader
        self._policy_sha256 = policy_sha256

    async def resolve(
        self, *, tenant_scope_id: str, context_id: str, request_digest: str,
    ) -> TrustedContextSnapshot:
        for value in (tenant_scope_id, context_id):
            if not isinstance(value, str) or not value or len(value) > 512:
                raise SealedContextBoundaryError("canonical snapshot scope invalid")
        if (not isinstance(request_digest, str) or len(request_digest) != 64
                or any(c not in "0123456789abcdef" for c in request_digest)):
            raise SealedContextBoundaryError("canonical request identity invalid")
        try:
            record = await self._loader.read(
                tenant_id=tenant_scope_id, context_id=context_id,
                request_digest=request_digest,
            )
        except Exception as exc:
            raise SealedContextBoundaryError("canonical compiled input unavailable") from exc
        if (not isinstance(record, CanonicalCompiledInput)
                or record.revoked is not False
                or record.tenant_id != tenant_scope_id
                or record.context_id != context_id
                or record.request_digest != request_digest
                or type(record.source_version) is not int or record.source_version < 1):
            raise SealedContextBoundaryError("canonical compiled context missing or revoked")
        if (not isinstance(record.instructions, str)
                or not isinstance(record.prompt, str)
                or not isinstance(record.history, tuple)
                or len(record.history) > 2000):
            raise SealedContextBoundaryError("canonical compiled input has invalid structure")
        # Bound allocations *before* materializing a page of Merkle leaves.
        # Policy and prompt bytes are measured independently of Python's
        # variable-width text representation.
        try:
            instructions = record.instructions.encode("utf-8", "strict")
            prompt = record.prompt.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise SealedContextBoundaryError("canonical compiled input has invalid Unicode") from exc
        if len(instructions) > 4 * 1024 * 1024 or len(prompt) > 4 * 1024 * 1024:
            raise SealedContextBoundaryError("canonical prompt exceeds bounded admission")
        total_bytes = len(instructions) + len(prompt)
        if total_bytes > 16 * 1024 * 1024:
            raise SealedContextBoundaryError("canonical input exceeds aggregate byte budget")
        digest = hashlib.sha256(instructions).hexdigest()
        if digest != self._policy_sha256:
            raise SealedContextIntegrityError("canonical instruction policy changed")
        parts: list[tuple[str, bytes]] = [("system", instructions)]
        for item in record.history:
            if (not isinstance(item, tuple) or len(item) != 2
                    or item[0] not in ("user", "assistant")
                    or not isinstance(item[1], str)):
                raise SealedContextBoundaryError("canonical history role or span invalid")
            try:
                span = item[1].encode("utf-8", "strict")
            except UnicodeError as exc:
                raise SealedContextBoundaryError("canonical history has invalid Unicode") from exc
            if len(span) > 4 * 1024 * 1024:
                raise SealedContextBoundaryError("canonical history span exceeds admission")
            total_bytes += len(span)
            if total_bytes > 16 * 1024 * 1024:
                raise SealedContextBoundaryError("canonical input exceeds aggregate byte budget")
            parts.append((item[0], span))
        parts.append(("user", prompt))
        root = merkle_root(tuple(parts))
        return TrustedContextSnapshot(
            root=root, policy_sha256=self._policy_sha256,
            snapshot_version=record.source_version,
            tenant_id=tenant_scope_id, context_id=context_id,
        )
