"""Current-source citation verification before a reviewed reference is reused.

Reference checks reject missing, withdrawn, revised, truncated, tampered or
out-of-bounds retained evidence. This is a review gate only, not publication
authority, source licensing, corroboration or factual verification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Iterable

from ..dragon_mission_quality import scan_untrusted_instructions
from ..operations import CrawlRun
from .contracts import (
    CampaignMandate, digest, ensure_snapshot_scope, exact_digest,
)
from .evidence import CampaignPassage


@dataclass(frozen=True)
class CitationCheck:
    source_id: str
    passage_hash: str
    source_revision: str
    valid_for_review: bool
    reason: str
    observed_snapshot_digest: str


@dataclass(frozen=True)
class CitationReport:
    entries: tuple[CitationCheck, ...]
    accepted: int
    held: int
    report_digest: str
    knowledge_publication_authorized: bool = False
    training_permission: bool = False


def verify_current_citations(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    passages: Iterable[CampaignPassage],
    *,
    revoked_source_ids: Iterable[str] = (),
    now: float,
    authorized: bool,
) -> CitationReport:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    run = CrawlRun.from_snapshot(snapshot)
    canonical = run.snapshot()
    citations = tuple(passages)
    if len(citations) > min(128, mandate.limits.max_evidence):
        raise ValueError("citation verification capacity exceeded")
    revoked = set(revoked_source_ids)
    for source_id in revoked:
        exact_digest(source_id, "revoked source")
    current = {record["source_id"]: record for record in run.sources()}
    findings = []
    seen = set()
    for anchor in citations:
        if not isinstance(anchor, CampaignPassage):
            raise TypeError("citation must be a typed retained passage")
        exact_digest(anchor.source_id, "source")
        exact_digest(anchor.source_content_hash, "full content")
        exact_digest(anchor.preserved_text_hash, "preserved content")
        exact_digest(anchor.passage_hash, "passage")
        identity = (anchor.source_id, anchor.start, anchor.end, anchor.passage_hash)
        if identity in seen:
            raise ValueError("duplicate citation")
        seen.add(identity)
        row = current.get(anchor.source_id)
        status = "reviewable_current_excerpt"
        if anchor.source_id in revoked:
            status = "source_withdrawn"
        elif row is None:
            status = "source_missing"
        elif row.get("content_hash") != anchor.source_content_hash:
            status = "content_revision_mismatch"
        elif row.get("preserved_text_hash") != anchor.preserved_text_hash:
            status = "retained_text_revision_mismatch"
        elif row.get("review_state") != "unreviewed":
            status = "unexpected_review_state"
        elif row.get("text_truncated") is not False:
            status = "incomplete_original_source"
        elif (not isinstance(anchor.start, int) or isinstance(anchor.start, bool)
              or not isinstance(anchor.end, int) or isinstance(anchor.end, bool)
              or anchor.start < 0 or anchor.end <= anchor.start
              or anchor.end > len(row.get("text", ""))):
            status = "invalid_unicode_span"
        elif not isinstance(anchor.text, str):
            status = "invalid_citation_text"
        else:
            retained = row["text"]
            raw_span = retained[anchor.start:anchor.end]
            if (
                raw_span != anchor.text
                or sha256(raw_span.encode("utf-8")).hexdigest() != anchor.passage_hash
                or sha256(retained.encode("utf-8")).hexdigest() != row["preserved_text_hash"]
            ):
                status = "passage_integrity_mismatch"
            elif scan_untrusted_instructions(raw_span, limit=16):
                status = "untrusted_instructions_require_review"
            elif anchor.injection_risks or not anchor.eligible_for_review:
                status = "original_screening_hold"
        findings.append(CitationCheck(
            source_id=anchor.source_id,
            passage_hash=anchor.passage_hash,
            source_revision=anchor.source_content_hash,
            valid_for_review=(status == "reviewable_current_excerpt"),
            reason=status,
            observed_snapshot_digest=canonical["snapshot_digest"],
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "checks": [asdict(x) for x in findings],
    }
    return CitationReport(
        entries=tuple(findings),
        accepted=sum(x.valid_for_review for x in findings),
        held=sum(not x.valid_for_review for x in findings),
        report_digest=digest(payload),
    )
