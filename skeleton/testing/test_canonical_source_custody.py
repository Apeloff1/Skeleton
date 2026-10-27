"""Adversarial live compiler candidate recheck for protected engine snapshots."""

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

import pytest

from skeleton.ai.runtime.inference.canonical_source_custody import (
    CanonicalSegmentSourceAuthority, CurrentSourceCollection,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError, SealedContextLimitError,
)
from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust

TENANT = "tenant"
ACTOR = "actor"
CONTEXT = "00000000-0000-4000-8000-000000000001"


def segment(number: int, text: str, *, tenant: str = TENANT) -> ContextSegment:
    return ContextSegment.from_content(
        segment_id=str(UUID(int=number + 3)), kind=ContextKind.USER_MESSAGE,
        source_type="canonical-test", source_id=f"source-{number}",
        content=text, trust_level=ContextTrust.DERIVED_UNTRUSTED,
        data_class="internal", tenant_id=tenant, purpose="model-inference",
        priority=0, relevance=1.0, created_at=datetime.now(timezone.utc),
        provenance=(), retention_class="session",
    )


class Owner:
    def __init__(self, segments=None):
        self.reads = 0
        self.current = CurrentSourceCollection(
            TENANT, ACTOR, CONTEXT, 7,
            tuple(segments if segments is not None else (segment(1, "first"), segment(2, "second"))),
        )
        self.error = None

    async def read_current(self, **kwargs):
        self.reads += 1
        assert kwargs == {"tenant_id": TENANT, "actor_id": ACTOR, "context_id": CONTEXT}
        if self.error is not None:
            raise self.error
        return self.current


@pytest.mark.asyncio
async def test_full_live_source_inventory_matches_compiler_snapshot_and_detects_changes():
    owner = Owner()
    authority = CanonicalSegmentSourceAuthority(loader=owner)
    current = await authority.inspect(tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT)
    assert current.source_snapshot == tuple(sorted(
        ((s.segment_id, s.content_digest) for s in owner.current.segments),
    ))
    assert current.version == 7 and owner.reads == 1
    # The compiler snapshots even candidates later excluded by policy;
    # source deletion and substitution must change this full inventory.
    owner.current = replace(owner.current, segments=(owner.current.segments[0],), version=8)
    subsequent = await authority.inspect(tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT)
    assert subsequent.source_snapshot != current.source_snapshot
    assert subsequent.version != current.version
    owner.current = replace(owner.current, segments=(segment(1, "replaced"),), version=9)
    newer = await authority.inspect(tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT)
    assert newer.source_snapshot != subsequent.source_snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"tenant_id": "other"}, {"actor_id": "other"}, {"context_id": "other"},
    {"version": 0}, {"version": True}, {"revoked": True},
    {"segments": []},
])
async def test_deleted_foreign_or_invalid_source_owner_is_denied(change):
    owner = Owner()
    owner.current = replace(owner.current, **change)
    with pytest.raises((SealedContextBoundaryError, SealedContextLimitError)):
        await CanonicalSegmentSourceAuthority(loader=owner).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )


@pytest.mark.asyncio
async def test_cross_tenant_candidate_or_duplicate_is_denied():
    original = segment(1, "first")
    for candidates in ((original, original), (segment(1, "first", tenant="other"),)):
        owner = Owner(candidates)
        with pytest.raises((SealedContextBoundaryError, SealedContextIntegrityError)):
            await CanonicalSegmentSourceAuthority(loader=owner).inspect(
                tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
            )


@pytest.mark.asyncio
async def test_missing_content_and_tampered_hash_are_denied():
    original = segment(1, "first")
    owner = Owner([replace(original, content=None)])
    with pytest.raises(SealedContextBoundaryError, match="materialized"):
        await CanonicalSegmentSourceAuthority(loader=owner).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )
    # Simulate an untrusted storage layer returning a mutated dataclass
    # without rerunning the ContextSegment constructor.
    forged = replace(original)
    object.__setattr__(forged, "content", "substituted")
    owner.current = replace(owner.current, segments=(forged,))
    with pytest.raises(SealedContextIntegrityError, match="content"):
        await CanonicalSegmentSourceAuthority(loader=owner).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )


@pytest.mark.asyncio
async def test_source_owner_outage_fail_closed():
    owner = Owner()
    owner.error = ConnectionError("do not print private resource names")
    with pytest.raises(SealedContextBoundaryError, match="unavailable") as error:
        await CanonicalSegmentSourceAuthority(loader=owner).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )
    assert "private resource" not in str(error.value)


@pytest.mark.asyncio
async def test_candidate_count_and_total_bytes_are_bounded():
    owner = Owner()
    owner.current = replace(
        owner.current,
        segments=tuple(segment(i, "a") for i in range(2001)),
    )
    with pytest.raises(SealedContextLimitError, match="count"):
        await CanonicalSegmentSourceAuthority(loader=owner).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )
    # A normal segment is limited to 4 MiB; five distinct 4-MiB candidates
    # exceed the aggregate 16-MiB guard even if each passes individually.
    huge = "x" * (4 * 1024 * 1024)
    owner.current = replace(owner.current, segments=tuple(
        segment(i, huge) for i in range(5)
    ))
    with pytest.raises(SealedContextLimitError, match="inventory exceeds byte"):
        await CanonicalSegmentSourceAuthority(loader=owner).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )


def test_source_authority_requires_real_operator_loader():
    with pytest.raises(SealedContextBoundaryError):
        CanonicalSegmentSourceAuthority(loader=object())
