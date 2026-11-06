"""Portable, exact-span citation custody manifest without external page bodies.

The manifest binds only to approved-for-inspection current source revisions,
retained source-body hashes, exact Unicode offsets, current source-use policy,
and a fixed selection of research hits. It is an auditable *locator*, not a
web snapshot, legal license, rights grant, reviewed quote or live citation.
A consumer must ask the existing backend to reauthorize each source.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion


@dataclass(frozen=True)
class BoundedCitation:
    citation_id: str
    source_id: str
    canonical_url: str
    full_content_hash: str
    preserved_text_hash: str
    passage_hash: str
    start: int
    end: int
    unicode_length: int
    captured_at: float
    objective_ids: tuple[str, ...]
    source_policy_current_at_issuance: bool = True
    external_source_requires_fresh_review: bool = True
    publication_permission: bool = False


@dataclass(frozen=True)
class CitationManifest:
    schema_version: str
    mandate_digest: str
    source_snapshot_digest: str
    source_policy_digest: str
    retrieval_digest: str
    citations: tuple[BoundedCitation, ...]
    admitted: int
    rejected: int
    encoded_bytes: int
    serialized_json: str
    manifest_digest: str
    max_citations: int
    max_serialized_bytes: int
    source_text_retained_in_manifest: bool = False
    remotely_fresh: bool = False
    publishable: bool = False


def build_citation_manifest(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    *,
    now: float,
    authorized: bool,
    max_citations: int = 32,
    max_serialized_bytes: int = 24_000,
) -> CitationManifest:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_citations, "citation manifest count", 1, 64)
    integer(max_serialized_bytes, "citation manifest bytes", 1024, 65_536)
    if policy.mandate_digest != mandate.fingerprint or (
        retrieval.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("foreign citation manifest input")
    run = CrawlRun.from_snapshot(snapshot).snapshot()
    if policy.source_snapshot_digest != run["snapshot_digest"] or (
        retrieval.source_snapshot_digest != run["snapshot_digest"]
        or retrieval.excluded_sources != policy.excluded_source_ids
    ):
        raise PermissionError("manifest uses stale current source-policy snapshot")
    if len(retrieval.results) > max_citations:
        raise ValueError("excessive citation manifest universe")
    eligible = set(policy.allowed_source_ids)
    seen = set()
    citations = []
    for hit in retrieval.results:
        key = hit.source_id, hit.start, hit.end, hit.passage_hash
        if key in seen:
            raise ValueError("duplicate exact citation anchor")
        seen.add(key)
        source = run["sources"].get(hit.source_id)
        if hit.source_id not in eligible or source is None:
            raise PermissionError("citation source not currently accessible")
        text = source.get("text")
        if (not isinstance(text, str)
            or type(hit.start) is not int or type(hit.end) is not int
            or hit.start < 0 or hit.end <= hit.start or hit.end > len(text)):
            raise ValueError("invalid exact citation source span")
        source_hash = sha256(text.encode("utf-8")).hexdigest()
        text_span = text[hit.start:hit.end]
        if (
            source.get("review_state") != "unreviewed"
            or source.get("text_truncated") is not False
            or source_hash != source.get("preserved_text_hash")
            or source.get("content_hash") != hit.source_hash
            or source.get("canonical_url") != hit.canonical_url
            or text_span != hit.text
            or sha256(text_span.encode("utf-8")).hexdigest() != hit.passage_hash
        ):
            raise PermissionError("citation anchor not bound to current full source")
        anchor_digest = digest({
            "source": hit.source_id,
            "source_hash": hit.source_hash,
            "passage_hash": hit.passage_hash,
            "start": hit.start, "end": hit.end,
            "policy": policy.policy_digest,
            "snapshot": run["snapshot_digest"],
        })
        citations.append(BoundedCitation(
            citation_id="citation:" + anchor_digest[:40],
            source_id=hit.source_id,
            canonical_url=hit.canonical_url,
            full_content_hash=hit.source_hash,
            preserved_text_hash=source_hash,
            passage_hash=hit.passage_hash,
            start=hit.start, end=hit.end, unicode_length=len(text_span),
            captured_at=source["fetched_at"],
            objective_ids=hit.matched_objective_ids,
        ))
    payload = {
        "schema_version": "skeleton.dragon.citation_manifest.v1",
        "mandate": mandate.fingerprint,
        "snapshot": run["snapshot_digest"],
        "policy": policy.policy_digest,
        "retrieval": retrieval.fusion_digest,
        "citations": [asdict(x) for x in citations],
        "review_required": True,
        "license_conferred": False,
        "external_text_excluded": True,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False)
    byte_count = len(encoded.encode("utf-8"))
    if byte_count > max_serialized_bytes:
        raise ValueError("citation manifest exceeds bounded export bytes")
    return CitationManifest(
        schema_version=payload["schema_version"],
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=run["snapshot_digest"],
        source_policy_digest=policy.policy_digest,
        retrieval_digest=retrieval.fusion_digest,
        citations=tuple(citations), admitted=len(citations), rejected=0,
        encoded_bytes=byte_count,
        serialized_json=encoded,
        manifest_digest=digest({
            "payload": payload, "limits": (max_citations, max_serialized_bytes),
        }),
        max_citations=max_citations,
        max_serialized_bytes=max_serialized_bytes,
    )


def verify_citation_manifest(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    manifest: CitationManifest,
    *,
    now: float,
    authorized: bool,
    max_citations: int = 32,
    max_serialized_bytes: int = 24_000,
) -> None:
    if not isinstance(manifest, CitationManifest):
        raise TypeError("typed citation manifest required")
    rebuilt = build_citation_manifest(
        mandate, snapshot, policy, retrieval,
        now=now, authorized=authorized,
        max_citations=max_citations,
        max_serialized_bytes=max_serialized_bytes,
    )
    if rebuilt != manifest:
        raise PermissionError("citation manifest integrity or policy mismatch")
