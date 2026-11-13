"""Current context-source custody from independently reloaded compiler inputs.

The canonical context compiler records the digest of *every* candidate segment,
including omitted ones. An operator-owned source loader must therefore re-read
the full authorized candidate set, not just selected messages or a saved
compiled handoff. This verifies exactly that inventory without creating a new
persistence owner or trusting a caller-supplied list of digests.

The source loader must read the actual current records and revocation/version
state from canonical source owners. This adapter checks their shape and content;
it cannot replace source-owner authorization or make a cross-database snapshot
transactional. The engine bridge rechecks both authorities before delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from skeleton.contracts.context import ContextSegment
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError, SealedContextLimitError,
)
from .engine_submission_snapshot import CurrentSourceCustody

_MAX_SEGMENTS = 2000
_MAX_CONTENT_BYTES = 4 * 1024 * 1024
_MAX_TOTAL_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CurrentSourceCollection:
    tenant_id: str
    actor_id: str
    context_id: str
    version: int
    segments: tuple[ContextSegment, ...]
    revoked: bool = False


class CanonicalSourceCollectionLoader(Protocol):
    async def read_current(
        self, *, tenant_id: str, actor_id: str, context_id: str,
    ) -> CurrentSourceCollection: ...


class CanonicalSegmentSourceAuthority:
    """Check every current compiler candidate and reconstruct its inventory."""

    def __init__(self, *, loader: CanonicalSourceCollectionLoader) -> None:
        if not callable(getattr(loader, "read_current", None)):
            raise SealedContextBoundaryError("canonical source owner loader required")
        self._loader = loader

    async def inspect(
        self, *, tenant_id: str, actor_id: str, context_id: str,
    ) -> CurrentSourceCustody:
        for value in (tenant_id, actor_id, context_id):
            if (not isinstance(value, str) or not value
                    or len(value.encode("utf-8", "strict")) > 512):
                raise SealedContextBoundaryError("canonical source scope invalid")
        try:
            source = await self._loader.read_current(
                tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
            )
        except Exception as exc:
            raise SealedContextBoundaryError("canonical source owner unavailable") from exc
        if (type(source) is not CurrentSourceCollection
                or source.tenant_id != tenant_id
                or source.actor_id != actor_id
                or source.context_id != context_id
                or source.revoked is not False
                or type(source.version) is not int
                or source.version < 1
                or type(source.segments) is not tuple):
            raise SealedContextBoundaryError("canonical source scope/version revoked or invalid")
        if not 1 <= len(source.segments) <= _MAX_SEGMENTS:
            raise SealedContextLimitError("canonical candidate inventory exceeds bounded count")
        inventory: list[tuple[str, str]] = []
        seen: set[str] = set()
        total = 0
        for segment in source.segments:
            if type(segment) is not ContextSegment or segment.tenant_id != tenant_id:
                raise SealedContextBoundaryError("candidate is not an authorized context segment")
            if segment.segment_id in seen:
                raise SealedContextIntegrityError("canonical candidate inventory contains duplicate identities")
            seen.add(segment.segment_id)
            if segment.content is None:
                # Hash-only placeholders cannot prove live content or deletion.
                raise SealedContextBoundaryError("canonical candidate content was not independently materialized")
            # Unicode code points never take fewer than one UTF-8 byte;
            # reject grossly oversized strings before allocating their
            # potentially much larger encoded representation.
            if len(segment.content) > _MAX_CONTENT_BYTES:
                raise SealedContextLimitError("canonical candidate exceeds byte admission")
            try:
                body = segment.content.encode("utf-8", "strict")
            except UnicodeError as exc:
                raise SealedContextBoundaryError("canonical candidate contains invalid Unicode") from exc
            if len(body) > _MAX_CONTENT_BYTES:
                raise SealedContextLimitError("canonical candidate exceeds byte admission")
            total += len(body)
            if total > _MAX_TOTAL_BYTES:
                raise SealedContextLimitError("canonical candidate inventory exceeds byte admission")
            if sha256(body).hexdigest() != segment.content_digest:
                raise SealedContextIntegrityError("canonical candidate content differs from admitted digest")
            inventory.append((segment.segment_id, segment.content_digest))
        return CurrentSourceCustody(
            tenant_id=tenant_id,
            actor_id=actor_id,
            context_id=context_id,
            source_snapshot=tuple(sorted(inventory, key=lambda item: item[0])),
            version=source.version,
            revoked=False,
        )


__all__ = [
    "CurrentSourceCollection", "CanonicalSourceCollectionLoader",
    "CanonicalSegmentSourceAuthority",
]
