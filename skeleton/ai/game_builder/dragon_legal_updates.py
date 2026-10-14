"""Primary-source change triage for Dragon's existing legal-review matrix.

Consumes custodied crawler observations; never interprets a judgment as legal
clearance. Changed source bodies invalidate affected review cells. Recrawl
work is handed to the existing governed crawler, not fetched by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Iterable

from .contracts import EvaluatorProvenance, canonical_digest
from .dragon_porting import JurisdictionReview, REVIEW_AREAS


PRIMARY_HOSTS = frozenset({"www.copyright.gov", "copyright.gov", "eur-lex.europa.eu",
    "curia.europa.eu", "lovdata.no", "www.supremecourt.gov", "www.ca9.uscourts.gov",
    "www.judiciary.uk"})


@dataclass(frozen=True, slots=True)
class LegalSourceObservation:
    source_id: str
    url: str
    jurisdiction: str
    areas: frozenset[str]
    content_digest: str
    captured_at: int
    custody_evidence_digest: str
    provenance: EvaluatorProvenance

    def __post_init__(self) -> None:
        for value in (self.source_id, self.jurisdiction):
            if not isinstance(value, str) or not value.strip() or len(value) > 192:
                raise ValueError("bounded legal source identity and jurisdiction required")
        if not isinstance(self.url, str) or len(self.url) > 2048:
            raise ValueError("bounded primary-source URL required")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or parsed.hostname not in PRIMARY_HOSTS or parsed.username or parsed.password or parsed.port not in {None, 443} or parsed.fragment:
            raise ValueError("legal observation requires an approved primary-source HTTPS URL")
        if not isinstance(self.areas, frozenset) or not self.areas or not self.areas <= REVIEW_AREAS:
            raise ValueError("explicit applicable legal-review areas required")
        for value in (self.content_digest, self.custody_evidence_digest):
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("exact source content and custody identities required")
        if type(self.captured_at) is not int or self.captured_at < 0:
            raise ValueError("legal source capture time required")
        if not isinstance(self.provenance, EvaluatorProvenance) or self.custody_evidence_digest not in self.provenance.output_evidence_refs:
            raise ValueError("custodied crawler output evidence required")


def legal_update_impact(previous: Iterable[LegalSourceObservation],
                        current: Iterable[LegalSourceObservation],
                        reviews: Iterable[JurisdictionReview], *, now: int,
                        max_source_age_seconds: int = 86400) -> dict:
    """Fail closed for missing/stale sources and conservatively invalidate changes.

    A changed judgment, statutory text or guidance page requests human
    re-review. It does not automatically declare that the applicable law
    changed or determine a case's binding force, appeal status or scope.
    """
    if type(now) is not int or now < 0 or type(max_source_age_seconds) is not int or not 1 <= max_source_age_seconds <= 604800:
        raise ValueError("bounded legal-source freshness policy required")
    old_rows, new_rows, review_rows = tuple(previous), tuple(current), tuple(reviews)
    if not 1 <= len(old_rows) <= 128 or len(new_rows) > 128 or len(review_rows) > 448:
        raise ValueError("bounded nonempty baseline legal-source set required")
    for rows in (old_rows, new_rows):
        if any(not isinstance(r, LegalSourceObservation) for r in rows) or len({r.source_id for r in rows}) != len(rows):
            raise ValueError("unique typed legal source observations required")
    if any(not isinstance(r, JurisdictionReview) for r in review_rows):
        raise ValueError("typed jurisdiction reviews required")
    old = {r.source_id: r for r in old_rows}
    new = {r.source_id: r for r in new_rows}
    events = []
    affected = set()
    cutoffs = {}
    for source_id in sorted(set(old) | set(new)):
        before, after = old.get(source_id), new.get(source_id)
        reason = None
        if before is None:
            reason = "new_primary_source_requires_applicability_review"
        elif after is None:
            reason = "previous_primary_source_missing"
        elif (before.url, before.jurisdiction, before.areas) != (after.url, after.jurisdiction, after.areas):
            raise ValueError("legal source scope cannot be rebound")
        elif after.captured_at < before.captured_at:
            raise ValueError("legal source observation replay")
        elif after.captured_at > now or now-after.captured_at > max_source_age_seconds:
            reason = "source_observation_not_current"
        elif before.content_digest != after.content_digest:
            reason = "primary_source_body_changed"
        if reason:
            source = after or before
            affected.update((source.jurisdiction, area) for area in source.areas)
            cutoff = after.captured_at if after is not None and reason in {
                "primary_source_body_changed", "new_primary_source_requires_applicability_review"} else now+1
            for area in source.areas:
                cell = (source.jurisdiction, area)
                cutoffs[cell] = max(cutoffs.get(cell, 0), cutoff)
            events.append({"source_id": source_id, "reason": reason,
                "before_digest": before.content_digest if before else None,
                "after_digest": after.content_digest if after else None,
                "custody_evidence": source.custody_evidence_digest})
    invalidated = sorted({(r.artifact_digest, r.target_id, r.jurisdiction, r.area)
        for r in review_rows if (r.jurisdiction, r.area) in affected
        and r.checked_at < cutoffs[(r.jurisdiction, r.area)]})
    body = {"schema": "skeleton.dragon.legal_update_impact.v1", "checked_at": now,
        "events": events, "affected_cells": [list(cell) for cell in sorted(affected)],
        "invalidated_reviews": [list(cell) for cell in invalidated],
        "requires_human_review": bool(events), "release_authority": False,
        "claim_boundary": "primary-source change triage; no automatic legal interpretation"}
    return {**body, "impact_digest": canonical_digest(body)}


def legal_recrawl_plan(sources: Iterable[LegalSourceObservation], *, now: int,
                       interval_seconds: int = 86400) -> tuple[dict, ...]:
    rows = tuple(sources)
    if type(now) is not int or now < 0 or type(interval_seconds) is not int or not 3600 <= interval_seconds <= 604800:
        raise ValueError("bounded legal recrawl interval required")
    if not 1 <= len(rows) <= 128 or any(not isinstance(r, LegalSourceObservation) for r in rows) or len({r.source_id for r in rows}) != len(rows):
        raise ValueError("bounded unique legal source set required")
    return tuple({"source_id": row.source_id, "url": row.url,
        "due": row.captured_at > now or now >= row.captured_at+interval_seconds,
        "next_check_at": row.captured_at+interval_seconds, "expected_body_digest": row.content_digest,
        "acquisition_owner": "skeleton/ai/webcrawler", "requires_governed_acquisition": True}
        for row in sorted(rows, key=lambda row: row.source_id))
