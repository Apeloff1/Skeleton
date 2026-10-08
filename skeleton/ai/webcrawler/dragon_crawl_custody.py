"""Content-addressed evidence custody for acquired crawler documents.

Constructs a narrow trust boundary from the real CrawlDocument contract into
Dragon's multi-pass evidence model. Evidence locators are exact character spans
of the captured UTF-8 document, never unverified citations or generated quotes.

Transport safety, publisher permission, robots admission and human approval
remain responsibilities of the upstream acquisition and governance planes.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable
from urllib.parse import urlsplit
import json

from .core import CrawlDocument, CrawlPolicy, canonicalize_url
from .dragon_probabilistic_distillation import EvidencePass, EvidencePolicy
from .dragon_source_independence import SourceProvenance


def _canonical_hash(payload: object) -> str:
    return sha256(json.dumps(
        payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CapturedSource:
    """A source identity bound to one immutable captured text revision."""

    source_id: str
    document: CrawlDocument
    parent_source_ids: tuple[str, ...] = ()
    lineage_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocatedReading:
    """A claimed observation anchored to an exact section of source text.

    The polarity and confidence are analyst claims, *not* automatic proof of
    the proposition. A pass_id names the analysis lens, not another source.
    """

    source_id: str
    pass_id: str
    claim_id: str
    supports: bool
    confidence: float
    reliability: float
    start: int
    end: int


@dataclass(frozen=True)
class CrawlCustodyBundle:
    """Immutable provenance/evidence mapping used by downstream assurance."""

    claim_id: str
    sources: tuple[SourceProvenance, ...]
    evidence: tuple[EvidencePass, ...]
    document_fingerprints: tuple[tuple[str, str], ...]
    custody_fingerprint: str


@dataclass(frozen=True)
class CustodyPolicy:
    max_sources: int = 1000
    max_evidence: int = 10000
    max_document_bytes: int = 4_000_000
    max_quote_chars: int = 2000
    max_relationships_per_source: int = 64


def _validate_policy(policy: CustodyPolicy) -> None:
    for name, ceiling in (
        ("max_sources", 100000),
        ("max_evidence", 1000000),
        ("max_document_bytes", 100_000_000),
        ("max_quote_chars", 2000),
        ("max_relationships_per_source", 1024),
    ):
        value = getattr(policy, name)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= ceiling:
            raise ValueError("invalid custody policy: " + name)


def _document(
    item: CapturedSource,
    policy: CustodyPolicy,
    crawl_policy: CrawlPolicy,
) -> SourceProvenance:
    if not isinstance(item, CapturedSource):
        raise ValueError("invalid captured source")
    if not isinstance(item.source_id, str) or not 1 <= len(item.source_id) <= 256:
        raise ValueError("invalid captured source identity")
    doc = item.document
    if not isinstance(doc, CrawlDocument):
        raise ValueError("captured source must contain CrawlDocument")
    if not isinstance(doc.canonical_url, str) or not crawl_policy.admits(doc.canonical_url):
        raise ValueError("untrusted document URL")
    parts = urlsplit(doc.canonical_url)
    if parts.username is not None or parts.password is not None:
        raise ValueError("credentialed document URL")
    if canonicalize_url(doc.canonical_url) != doc.canonical_url:
        raise ValueError("noncanonical document URL")
    if not isinstance(doc.fetched_url, str):
        raise ValueError("invalid fetched URL")
    if not crawl_policy.admits(doc.fetched_url):
        raise ValueError("untrusted fetched URL")
    fetched = urlsplit(doc.fetched_url)
    if fetched.username is not None or fetched.password is not None:
        raise ValueError("credentialed fetched URL")
    if not isinstance(doc.text, str) or not doc.text.strip():
        raise ValueError("empty captured document text")
    raw = doc.text.encode("utf-8")
    if len(raw) > policy.max_document_bytes:
        raise ValueError("captured document byte budget exceeded")
    if not isinstance(doc.content_hash, str) or sha256(raw).hexdigest() != doc.content_hash:
        raise ValueError("captured content hash mismatch")
    if not isinstance(doc.source_score, (float, int)) or not isfinite(doc.source_score):
        raise ValueError("invalid crawler score")
    if not 0 <= doc.source_score <= 1:
        raise ValueError("invalid crawler score")
    if not isinstance(doc.fetched_at, (float, int)) or not isfinite(doc.fetched_at):
        raise ValueError("invalid crawl timestamp")
    if doc.fetched_at < 0:
        raise ValueError("invalid crawl timestamp")
    if doc.content_type not in crawl_policy.allowed_content_types:
        raise ValueError("disallowed captured content type")
    if not isinstance(doc.provenance, dict) and not hasattr(doc.provenance, "get"):
        raise ValueError("missing acquisition provenance")
    actual = doc.provenance
    if any((
        actual.get("schema") != "skeleton.ai.crawl.provenance.v1",
        actual.get("canonical_url") != doc.canonical_url,
        actual.get("fetched_url") != doc.fetched_url,
        actual.get("content_hash") != doc.content_hash,
        actual.get("fetched_at") != doc.fetched_at,
        not isinstance(actual.get("status"), int),
        isinstance(actual.get("status"), bool),
        not (200 <= actual.get("status", 0) < 300)
            if isinstance(actual.get("status"), int) else True,
    )):
        raise ValueError("acquisition provenance mismatch")
    if not isinstance(item.parent_source_ids, tuple) or not isinstance(item.lineage_tokens, tuple):
        raise ValueError("invalid source relationships")
    if len(item.parent_source_ids) + len(item.lineage_tokens) > policy.max_relationships_per_source:
        raise ValueError("source relationship budget exceeded")
    for group in (item.parent_source_ids, item.lineage_tokens):
        if any(not isinstance(x, str) or not 1 <= len(x) <= 256 for x in group):
            raise ValueError("invalid source relationship")
        if len(group) != len(set(group)):
            raise ValueError("duplicate source relationship")
    return SourceProvenance(
        item.source_id, doc.content_hash, doc.canonical_url,
        item.parent_source_ids, item.lineage_tokens,
    )


def bind_crawl_evidence(
    claim_id: str,
    captured_sources: Iterable[CapturedSource],
    readings: Iterable[LocatedReading],
    *,
    authorized: bool,
    policy: CustodyPolicy = CustodyPolicy(),
    crawl_policy: CrawlPolicy = CrawlPolicy(),
    evidence_policy: EvidencePolicy = EvidencePolicy(),
) -> CrawlCustodyBundle:
    """Produce attributable, exact-span evidence without network access.

    All input must have been admitted at the upstream trusted ingestion
    boundary. This verifies internal hashes and matching metadata, not a
    cryptographic signature from the fetch transport or the reading analyst.
    """
    if not authorized:
        raise PermissionError("captured evidence binding requires authorization")
    _validate_policy(policy)
    if not isinstance(claim_id, str) or not 1 <= len(claim_id) <= 256:
        raise ValueError("invalid claim identity")
    sources = tuple(captured_sources)
    readings = tuple(readings)
    if len(sources) > policy.max_sources or len(readings) > min(
        policy.max_evidence, evidence_policy.max_evidence,
    ):
        raise ValueError("captured custody capacity exceeded")
    docs: dict[str, CrawlDocument] = {}
    manifest: list[SourceProvenance] = []
    for source in sources:
        record = _document(source, policy, crawl_policy)
        if record.source_id in docs:
            raise ValueError("duplicate captured source identity")
        docs[record.source_id] = source.document
        manifest.append(record)
    if any(parent not in docs for entry in manifest for parent in entry.parent_source_ids):
        raise ValueError("undeclared captured source parent")

    bound: list[EvidencePass] = []
    seen: set[tuple[str, str]] = set()
    per_source: dict[str, int] = {}
    for reading in readings:
        if not isinstance(reading, LocatedReading):
            raise ValueError("invalid located reading")
        doc = docs.get(reading.source_id)
        if doc is None:
            raise ValueError("located reading missing captured source")
        if reading.claim_id != claim_id:
            raise ValueError("cross-claim located reading")
        if not isinstance(reading.pass_id, str) or not 1 <= len(reading.pass_id) <= 128:
            raise ValueError("invalid pass identity")
        ident = (reading.source_id, reading.pass_id)
        if ident in seen:
            raise ValueError("duplicate located reading")
        seen.add(ident)
        if not isinstance(reading.start, int) or isinstance(reading.start, bool):
            raise ValueError("invalid evidence span")
        if not isinstance(reading.end, int) or isinstance(reading.end, bool):
            raise ValueError("invalid evidence span")
        if not 0 <= reading.start < reading.end <= len(doc.text):
            raise ValueError("invalid evidence span")
        excerpt = doc.text[reading.start:reading.end]
        if not excerpt.strip() or len(excerpt) > policy.max_quote_chars:
            raise ValueError("invalid anchored excerpt")
        per_source[reading.source_id] = per_source.get(reading.source_id, 0) + 1
        if per_source[reading.source_id] > evidence_policy.max_passes_per_source:
            raise ValueError("per-source reread budget exceeded")
        bound.append(EvidencePass(
            source_id=reading.source_id,
            source_revision=doc.content_hash,
            pass_id=reading.pass_id,
            claim_id=claim_id,
            supports=reading.supports,
            confidence=reading.confidence,
            reliability=reading.reliability,
            independence_group="untrusted:" + reading.source_id,
            evidence_locator=(
                f"sha256:{doc.content_hash}@{reading.start}:{reading.end}"
            ),
            observation=excerpt,
        ))
    # Apply the same validation as the knowledge distiller *before* producing
    # the custody certificate, including finite confidences and boolean stance.
    from .dragon_probabilistic_distillation import ProbabilisticKnowledgeDistiller
    distiller = ProbabilisticKnowledgeDistiller(evidence_policy)
    for item in bound:
        distiller._validate(item)
    # Make the custody result invariant to source and reading input order.
    ordered_sources = tuple(sorted(manifest, key=lambda x: x.source_id))
    ordered_evidence = tuple(sorted(
        bound, key=lambda x: (x.source_id, x.pass_id),
    ))
    fingerprints = tuple((s.source_id, s.content_digest) for s in ordered_sources)
    receipt = _canonical_hash({
        "schema": "skeleton.crawler.captured_custody.v1",
        "claim_id": claim_id,
        "sources": [
            (s.source_id, s.content_digest, s.canonical_uri,
             sorted(s.parent_source_ids), sorted(s.lineage_tokens))
            for s in ordered_sources
        ],
        "readings": [
            (r.source_id, r.source_revision, r.pass_id, r.claim_id,
             r.supports, r.confidence, r.reliability,
             r.evidence_locator, r.observation)
            for r in ordered_evidence
        ],
    })
    return CrawlCustodyBundle(
        claim_id, ordered_sources, ordered_evidence, fingerprints, receipt,
    )


@dataclass(frozen=True)
class CapturedCrawlReview:
    """Exact document receipts plus the derived, human-reviewed research proposal."""

    custody: CrawlCustodyBundle
    assurance: "ProvenanceAssurance"


def assure_captured_crawl(
    claim_id: str,
    captured_sources: Iterable[CapturedSource],
    readings: Iterable[LocatedReading],
    *,
    authorized: bool,
    custody_policy: CustodyPolicy = CustodyPolicy(),
    crawl_policy: CrawlPolicy = CrawlPolicy(),
    evidence_policy: EvidencePolicy = EvidencePolicy(),
    assurance_policy: "AssurancePolicy | None" = None,
    attestation_registry: "ProvenanceRegistry | None" = None,
) -> CapturedCrawlReview:
    """End-to-end local audit of real captured text and source dependency.

    This is *not* a background crawling or model execution endpoint. No
    acquisition or knowledge promotion occurs inside this function.
    """
    from .dragon_provenance_assurance import (
        AssurancePolicy, ProvenanceAssurance, assure_crawler_evidence,
    )
    from .dragon_provenance_registry import ProvenanceRegistry
    bound = bind_crawl_evidence(
        claim_id, captured_sources, readings, authorized=authorized,
        policy=custody_policy, crawl_policy=crawl_policy,
        evidence_policy=evidence_policy,
    )
    report = assure_crawler_evidence(
        claim_id, bound.evidence, bound.sources, authorized=authorized,
        evidence_policy=evidence_policy,
        assurance_policy=assurance_policy or AssurancePolicy(),
        attestation_registry=attestation_registry,
    )
    if report.belief.readings != len(bound.evidence):
        raise RuntimeError("captured evidence and assurance count mismatch")
    return CapturedCrawlReview(bound, report)
