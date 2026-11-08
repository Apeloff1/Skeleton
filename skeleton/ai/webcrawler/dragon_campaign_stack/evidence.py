"""Exact-span, consent-bound review of retained crawler source snapshots.

This module never upgrades external content into trusted instructions or
knowledge. Full-content hashes cannot be recomputed from truncated excerpts;
those captures are labelled limited rather than falsely revalidated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Iterable

from ..dragon_mission_quality import (
    measure_information_quality, rank_query_passages, scan_untrusted_instructions,
)
from ..core import canonicalize_url
from .contracts import CampaignMandate, digest, exact_digest, finite, validate_public_url


@dataclass(frozen=True)
class SourceInspection:
    source_id: str
    canonical_url: str
    full_content_hash: str
    preserved_text_hash: str
    text_truncated: bool
    full_text_revalidated: bool
    fetched_at: float
    risk_count: int
    low_information: bool
    inspectable: bool
    reason: str


@dataclass(frozen=True)
class CampaignPassage:
    source_id: str
    canonical_url: str
    source_content_hash: str
    preserved_text_hash: str
    start: int
    end: int
    passage_hash: str
    text: str
    query_score: float
    injection_risks: tuple[str, ...]
    eligible_for_review: bool
    authority: str = "unreviewed_external_evidence_only"


@dataclass(frozen=True)
class EvidenceInspection:
    sources: tuple[SourceInspection, ...]
    passages: tuple[CampaignPassage, ...]
    rejected_sources: tuple[tuple[str, str], ...]
    evidence_digest: str
    verified_knowledge: bool = False
    training_permission: bool = False


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _source(
    raw: dict[str, object], mandate: CampaignMandate, *,
    now: float,
) -> tuple[SourceInspection, str]:
    if not isinstance(raw, dict):
        raise ValueError("invalid retained source")
    source_id = exact_digest(raw.get("source_id"), "source id")
    url = raw.get("canonical_url")
    if not isinstance(url, str):
        raise ValueError("missing source URL")
    validate_public_url(url, mandate)
    fetched_url = raw.get("fetched_url")
    if not isinstance(fetched_url, str):
        raise ValueError("missing fetched URL")
    validate_public_url(canonicalize_url(fetched_url), mandate)
    text = raw.get("text")
    if not isinstance(text, str) or not 0 < len(text.encode("utf-8")) <= 24_000:
        raise ValueError("source text outside retention cap")
    preserved = exact_digest(raw.get("preserved_text_hash"), "preserved text hash")
    full = exact_digest(raw.get("content_hash"), "full content hash")
    if _hash_text(text) != preserved:
        raise ValueError("retained source text hash mismatch")
    truncated = raw.get("text_truncated")
    if type(truncated) is not bool:
        raise ValueError("missing truncation evidence")
    if not truncated and preserved != full:
        raise ValueError("untruncated text mismatches full digest")
    fetched = finite(raw.get("fetched_at"), "source fetch time")
    if fetched > now + 300:
        raise ValueError("future source capture")
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("missing crawl provenance")
    if (provenance.get("consent_id") != mandate.scope.consent_id
            or provenance.get("canonical_url") != url
            or provenance.get("content_hash") != full
            or provenance.get("source_status") != "unreviewed_external_capture"
            or provenance.get("training_permission") is not False):
        raise PermissionError("source provenance or consent mismatch")
    if provenance.get("fetched_url") != fetched_url or provenance.get("fetched_at") != fetched:
        raise ValueError("provenance transport identity mismatch")
    exact_digest(provenance.get("raw_body_hash"), "raw body hash")
    if raw.get("review_state") != "unreviewed":
        raise PermissionError("unsupported source review transition")
    if raw.get("source_id") != digest({"url": url, "content_hash": full}):
        raise ValueError("source id rebinding")
    risks = scan_untrusted_instructions(text, limit=64)
    quality = measure_information_quality(text)
    # A hostile page is still preserved as observed evidence, never allowed
    # to issue instructions or become training data by this inspection.
    limited = truncated or bool(risks) or quality.low_information
    reason = (
        "partial_content_only" if truncated else
        "instruction_risk_review" if risks else
        "low_information_review" if quality.low_information else
        "unreviewed_requires_human_review"
    )
    return SourceInspection(
        source_id=source_id, canonical_url=url,
        full_content_hash=full, preserved_text_hash=preserved,
        text_truncated=truncated, full_text_revalidated=not truncated,
        fetched_at=fetched, risk_count=len(risks),
        low_information=quality.low_information,
        inspectable=not limited, reason=reason,
    ), text


def inspect_campaign_evidence(
    mandate: CampaignMandate,
    sources: Iterable[dict[str, object]], *,
    now: float,
    authorized: bool,
    revoked_source_ids: Iterable[str] = (),
) -> EvidenceInspection:
    mandate.admit(now=now, authorized=authorized)
    revoked = set(revoked_source_ids)
    for source_id in revoked:
        exact_digest(source_id, "revoked source")
    data = tuple(sources)
    if len(data) > mandate.request.max_documents:
        raise ValueError("source review capacity exceeded")
    inspected: list[SourceInspection] = []
    passages: list[CampaignPassage] = []
    rejected: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for raw in data:
        # Source-specific withdrawal is applied BEFORE text/ranking inspection.
        # The application must derive this set from current Mongo source policy.
        if isinstance(raw, dict) and raw.get("source_id") in revoked:
            rejected.append((raw["source_id"], "source_policy_withdrawn"))
            continue
        try:
            result, text = _source(raw, mandate, now=now)
            if result.source_id in seen_ids:
                raise ValueError("duplicate source identity")
            seen_ids.add(result.source_id)
        except (ValueError, PermissionError, TypeError) as exc:
            source_ref = raw.get("source_id", "unknown") if isinstance(raw, dict) else "unknown"
            rejected.append((str(source_ref)[:80], type(exc).__name__ + ":" + str(exc)))
            continue
        inspected.append(result)
        if not mandate.query.strip():
            continue
        ranked = rank_query_passages(text, mandate.query, limit=8)
        for passage in ranked:
            if len(passages) >= mandate.limits.max_evidence:
                break
            span = passage.span
            if (span.end > len(text) or span.start < 0
                    or text[span.start:span.end] != span.text):
                raise ValueError("ranker returned non-anchored evidence")
            if len(span.text) > mandate.limits.max_evidence_chars:
                continue
            risks = scan_untrusted_instructions(span.text, limit=16)
            passages.append(CampaignPassage(
                source_id=result.source_id,
                canonical_url=result.canonical_url,
                source_content_hash=result.full_content_hash,
                preserved_text_hash=result.preserved_text_hash,
                start=span.start, end=span.end,
                passage_hash=_hash_text(span.text),
                text=span.text, query_score=passage.weighted_score,
                injection_risks=tuple(x.risk for x in risks),
                eligible_for_review=result.inspectable and not risks,
            ))
    passages.sort(key=lambda p: (-p.query_score, p.source_id, p.start))
    inspected.sort(key=lambda x: (x.source_id, x.canonical_url))
    payload = {
        "mandate": mandate.fingerprint,
        "sources": [asdict(x) for x in inspected],
        "passages": [asdict(x) for x in passages],
        "rejected": rejected,
        "trust": "external_unreviewed",
    }
    return EvidenceInspection(
        tuple(inspected), tuple(passages), tuple(rejected),
        digest(payload),
    )
