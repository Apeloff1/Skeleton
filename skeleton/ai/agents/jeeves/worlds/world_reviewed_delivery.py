"""Source-bound reviewed world delivery, with no implicit publication.

The candidate is previewed under a source revision lease. Publication checks
both the original revision and an explicitly approved candidate digest.
Playable handoff is emitted only from the newly published canonical source.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, edit, prove,
)
from skeleton.jeeves.worlds.world_handoff_cli import build_handoff, verify_handoff


@dataclass(frozen=True)
class ReviewTicket:
    world_id: str
    expected_digest: str
    candidate_digest: str
    proof: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "expected_digest": self.expected_digest,
            "candidate_digest": self.candidate_digest,
            "proof": self.proof,
        }


def preview(root: str, world_id: str, operation: Mapping[str, Any]) -> ReviewTicket:
    """Pure preview: never writes an edit or grants authorization."""
    store = WorldStore(root)
    original = store.read(world_id)
    candidate = edit(original, operation)
    proof = prove(candidate)
    return ReviewTicket(
        world_id=world_id,
        expected_digest=digest(original),
        candidate_digest=proof.source_digest,
        proof=proof.as_dict(),
    )


def publish_approved(
    root: str,
    world_id: str,
    operation: Mapping[str, Any],
    *,
    expected_digest: str,
    approved_digest: str,
) -> dict[str, Any]:
    """Publish only the exact reviewed candidate, then verify playable output.

    Caller must retain the preview ticket outside this function. Both digests
    are mandatory; a stale lease or changed operation fails closed. No partial
    handoff is returned if publication fails.
    """
    if not isinstance(expected_digest, str) or not isinstance(approved_digest, str):
        raise CanonError("review_required")
    if len(expected_digest) != 64 or len(approved_digest) != 64:
        raise CanonError("review_required")
    if any(c not in "0123456789abcdef" for c in expected_digest + approved_digest):
        raise CanonError("review_required")
    store = WorldStore(root)
    source = store.read(world_id)
    if digest(source) != expected_digest:
        raise CanonError("stale_source")
    candidate = edit(source, operation)
    if candidate["id"] != world_id:
        raise CanonError("world_id_mismatch")
    if digest(candidate) != approved_digest:
        raise CanonError("review_mismatch")
    # Preflight compilation before publication so malformed artifacts cannot
    # be committed and then fail at the handoff stage.
    preflight = build_handoff(candidate, approved_digest)
    verify_handoff(canonical(preflight))
    published = store.publish(candidate, expected_digest=expected_digest)
    if published != approved_digest:
        raise CanonError("publication_digest_mismatch")
    # Re-read after the CAS publication. A concurrent subsequent edit must
    # never be represented as the approved handoff.
    current = store.read(world_id)
    if digest(current) != approved_digest:
        raise CanonError("handoff_source_changed")
    handoff = build_handoff(current, approved_digest)
    verify_handoff(canonical(handoff))
    return {
        "schema": "jeeves.world.reviewed.delivery.v1",
        "world_id": world_id,
        "previous_digest": expected_digest,
        "published_digest": published,
        "handoff": handoff,
    }
