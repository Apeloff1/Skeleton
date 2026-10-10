"""Revision-aware evidence invalidation for captured crawler documents.

The review is deterministic and offline. New recrawls *never* silently inherit
earlier analysts' confidence: even when the old passage is still present, a
changed source requires renewed semantic and custody review.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Iterable
import json

from .dragon_crawl_custody import (
    CapturedSource, CustodyPolicy, LocatedReading, bind_crawl_evidence,
)
from .dragon_probabilistic_distillation import EvidencePolicy


class SourceChange(str, Enum):
    UNCHANGED = "unchanged"
    NEW = "new"
    MISSING = "missing"
    CHANGED = "changed"


class ReadingDisposition(str, Enum):
    REUSABLE = "reusable"
    MISSING_SOURCE = "missing_source"
    ORIGIN_CHANGED = "origin_changed"
    LINEAGE_CHANGED = "lineage_changed"
    DELIVERY_CHANGED = "delivery_changed"
    QUALITY_CHANGED = "quality_changed"
    QUOTE_ABSENT = "quote_absent"
    QUOTE_AMBIGUOUS = "quote_ambiguous"
    REASSESS_REVISED_DOCUMENT = "reassess_revised_document"


@dataclass(frozen=True)
class SourceRevisionDelta:
    source_id: str
    change: SourceChange
    previous_digest: str | None
    current_digest: str | None
    previous_origin: str | None
    current_origin: str | None
    content_changed: bool
    origin_changed: bool
    lineage_changed: bool
    delivery_changed: bool
    quality_changed: bool


@dataclass(frozen=True)
class ReadingRevalidation:
    source_id: str
    pass_id: str
    source_revision: str
    original_span: tuple[int, int]
    disposition: ReadingDisposition
    candidate_span: tuple[int, int] | None
    matching_quotes: int
    # matching_quotes is saturated at 2 (0, 1, or at least 2).
    requires_human_review: bool


@dataclass(frozen=True)
class RevisionRevalidation:
    claim_id: str
    original_custody_fingerprint: str
    current_custody_fingerprint: str
    sources: tuple[SourceRevisionDelta, ...]
    readings: tuple[ReadingRevalidation, ...]
    prior_readings_reusable: bool
    added_sources: tuple[str, ...]
    missing_sources: tuple[str, ...]
    invalidated_readings: int
    fingerprint: str


def _hash(payload: object) -> str:
    return sha256(json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()).hexdigest()


def _quote_location(text: str, quote: str) -> tuple[int, tuple[int, int] | None]:
    """Detect absent, unique, or multiply occurring quotes with two searches.

    Saturate at two occurrences rather than a potentially unbounded scan of
    overlapping matches. Distinct literal quotation locations are never
    automatically accepted as a semantic equivalence.
    """
    first = text.find(quote)
    if first < 0:
        return 0, None
    duplicate = text.find(quote, first + 1)
    if duplicate >= 0:
        return 2, None
    return 1, (first, first + len(quote))


def compare_crawl_revisions(
    claim_id: str,
    previous_sources: Iterable[CapturedSource],
    previous_readings: Iterable[LocatedReading],
    current_sources: Iterable[CapturedSource],
    *,
    authorized: bool,
    custody_policy: CustodyPolicy = CustodyPolicy(),
    evidence_policy: EvidencePolicy = EvidencePolicy(),
) -> RevisionRevalidation:
    """Audit a new crawl against content-anchored evidence of an older crawl.

    Both inventories are fully checked for internal custody integrity before
    comparison. A missing current source is a tracked invalidation, not an
    exception, and a changed source never causes old pass receipts to be
    rewritten. The caller owns actual recrawling, authorization and retention.
    """
    if not authorized:
        raise PermissionError("revision comparison requires authorization")
    originals = tuple(previous_sources)
    latest = tuple(current_sources)
    readings = tuple(previous_readings)
    old = bind_crawl_evidence(
        claim_id, originals, readings, authorized=True,
        policy=custody_policy, evidence_policy=evidence_policy,
    )
    new = bind_crawl_evidence(
        claim_id, latest, (), authorized=True, policy=custody_policy,
        evidence_policy=evidence_policy,
    )
    before = {s.source_id: s for s in originals}
    after = {s.source_id: s for s in latest}
    changes: list[SourceRevisionDelta] = []
    status: dict[str, SourceRevisionDelta] = {}
    for source_id in sorted(before.keys() | after.keys()):
        prior = before.get(source_id)
        current = after.get(source_id)
        previous_digest = prior.document.content_hash if prior else None
        current_digest = current.document.content_hash if current else None
        previous_origin = prior.document.canonical_url if prior else None
        current_origin = current.document.canonical_url if current else None
        changed_text = bool(prior and current and previous_digest != current_digest)
        changed_origin = bool(prior and current and previous_origin != current_origin)
        changed_lineage = (
            (sorted(prior.parent_source_ids), sorted(prior.lineage_tokens)) !=
            (sorted(current.parent_source_ids), sorted(current.lineage_tokens))
            if prior and current else False
        )
        changed_delivery = bool(prior and current and (
            prior.document.fetched_url != current.document.fetched_url
            or prior.document.content_type != current.document.content_type
        ))
        # Recrawl timestamp alone is not epistemic evidence of content drift.
        # Changes to source scoring or the acquisition's remaining policy
        # receipt do, however, require a fresh evidence-quality review.
        def stable_provenance(source: CapturedSource) -> dict[str, object]:
            return {
                key: value for key, value in source.document.provenance.items()
                if key != "fetched_at"
            }
        changed_quality = bool(prior and current and (
            prior.document.source_score != current.document.source_score
            or stable_provenance(prior) != stable_provenance(current)
        ))
        if prior is None:
            category = SourceChange.NEW
        elif current is None:
            category = SourceChange.MISSING
        elif (changed_text or changed_origin or changed_lineage
              or changed_delivery or changed_quality):
            category = SourceChange.CHANGED
        else:
            category = SourceChange.UNCHANGED
        delta = SourceRevisionDelta(
            source_id, category, previous_digest, current_digest,
            previous_origin, current_origin,
            changed_text, changed_origin, changed_lineage,
            changed_delivery, changed_quality,
        )
        changes.append(delta)
        status[source_id] = delta

    rechecks: list[ReadingRevalidation] = []
    # The binder already asserted these are exact valid spans in old captures.
    for reading in sorted(readings, key=lambda x: (x.source_id, x.pass_id)):
        delta = status[reading.source_id]
        initial_doc = before[reading.source_id].document
        origin_span = reading.start, reading.end
        new_doc = after.get(reading.source_id)
        if new_doc is None:
            disposition = ReadingDisposition.MISSING_SOURCE
            count, candidate = 0, None
        elif delta.origin_changed:
            disposition = ReadingDisposition.ORIGIN_CHANGED
            count, candidate = 0, None
        elif delta.lineage_changed:
            disposition = ReadingDisposition.LINEAGE_CHANGED
            count, candidate = 0, None
        elif delta.delivery_changed:
            disposition = ReadingDisposition.DELIVERY_CHANGED
            count, candidate = 0, None
        elif delta.quality_changed and not delta.content_changed:
            disposition = ReadingDisposition.QUALITY_CHANGED
            count, candidate = 0, None
        elif delta.change is SourceChange.UNCHANGED:
            disposition = ReadingDisposition.REUSABLE
            count, candidate = 1, origin_span
        else:
            count, candidate = _quote_location(
                new_doc.document.text,
                initial_doc.text[reading.start:reading.end],
            )
            if count == 0:
                disposition = ReadingDisposition.QUOTE_ABSENT
            elif count > 1:
                disposition = ReadingDisposition.QUOTE_AMBIGUOUS
            else:
                disposition = ReadingDisposition.REASSESS_REVISED_DOCUMENT
        rechecks.append(ReadingRevalidation(
            reading.source_id, reading.pass_id, initial_doc.content_hash,
            origin_span, disposition, candidate, count,
            disposition is not ReadingDisposition.REUSABLE,
        ))
    added = tuple(x.source_id for x in changes if x.change is SourceChange.NEW)
    missing = tuple(x.source_id for x in changes if x.change is SourceChange.MISSING)
    invalid = sum(x.requires_human_review for x in rechecks)
    # Every source in the custody inventory contributes to a claim's
    # provenance context, even when it provided no direct reading. A changed
    # unobserved parent or attestation-related source can invalidate the
    # dependency model without moving a single quoted passage.
    reusable = (
        bool(rechecks)
        and invalid == 0
        and all(delta.change is SourceChange.UNCHANGED for delta in changes)
    )
    fingerprint = revision_report_fingerprint(
        RevisionRevalidation(
            claim_id, old.custody_fingerprint, new.custody_fingerprint,
            tuple(changes), tuple(rechecks), reusable, added, missing,
            invalid, "",
        )
    )
    return RevisionRevalidation(
        claim_id, old.custody_fingerprint, new.custody_fingerprint,
        tuple(changes), tuple(rechecks), reusable, added, missing,
        invalid, fingerprint,
    )



def revision_report_fingerprint(review: RevisionRevalidation) -> str:
    """Recompute the complete, canonical typed review identity for custody.

    Used by durable journals to reject mutable/copied review objects whose
    displayed digest does not match the authoritative field values.
    """
    if not isinstance(review, RevisionRevalidation):
        raise ValueError("revision report required")
    if not isinstance(review.sources, tuple) or not isinstance(review.readings, tuple):
        raise ValueError("invalid revision report collections")
    for source in review.sources:
        if not isinstance(source, SourceRevisionDelta) or not isinstance(
            source.change, SourceChange
        ):
            raise ValueError("invalid source revision entry")
    for reading in review.readings:
        if not isinstance(reading, ReadingRevalidation) or not isinstance(
            reading.disposition, ReadingDisposition
        ):
            raise ValueError("invalid reading revision entry")
    return _hash({
        "schema": "skeleton.crawler.revision_revalidation.v2",
        "claim_id": review.claim_id,
        "previous": review.original_custody_fingerprint,
        "current": review.current_custody_fingerprint,
        "sources": [
            (x.source_id, x.change.value, x.previous_digest, x.current_digest,
             x.previous_origin, x.current_origin, x.content_changed,
             x.origin_changed, x.lineage_changed, x.delivery_changed,
             x.quality_changed)
            for x in review.sources
        ],
        "readings": [
            (x.source_id, x.pass_id, x.source_revision, x.original_span,
             x.disposition.value, x.candidate_span, x.matching_quotes,
             x.requires_human_review)
            for x in review.readings
        ],
        "reusable": review.prior_readings_reusable,
        "added": review.added_sources,
        "missing": review.missing_sources,
        "invalidated": review.invalidated_readings,
    })
