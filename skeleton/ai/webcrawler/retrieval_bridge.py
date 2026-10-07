"""Fail-closed bridge from policy-bound crawl documents into FLGB-03 retrieval/context.

Crawler content is always treated as external data. This adapter verifies the
crawler's own provenance envelope, derives a stable provenance digest, and emits
only the canonical FLGB-03 contracts. It never grants instruction authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping

from skeleton.ai.context.flgb_context_runtime import ContextItem, RetrievalCandidate

from .core import CrawlDocument


class CrawlRetrievalBridgeError(ValueError):
    """Crawler evidence cannot safely enter retrieval."""


def _digest_json(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CrawlRetrievalBridgeError("crawler provenance is not canonical encodable") from exc
    return sha256(raw).hexdigest()


def _ppm(value: float, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CrawlRetrievalBridgeError(f"invalid {name}")
    if not 0.0 <= float(value) <= 1.0:
        raise CrawlRetrievalBridgeError(f"{name} outside [0,1]")
    return int(round(float(value) * 1_000_000))


@dataclass(frozen=True)
class CrawlRetrievalRecord:
    candidate: RetrievalCandidate
    context_item: ContextItem
    provenance_digest: str
    canonical_url: str

    def __post_init__(self) -> None:
        if self.candidate.content_digest != self.context_item.content_digest:
            raise CrawlRetrievalBridgeError("retrieval/context content identity mismatch")
        if self.candidate.provenance_digest != self.provenance_digest:
            raise CrawlRetrievalBridgeError("retrieval provenance identity mismatch")
        if self.context_item.provenance_digest != self.provenance_digest:
            raise CrawlRetrievalBridgeError("context provenance identity mismatch")


def _verified_provenance(doc: CrawlDocument) -> tuple[Mapping[str, object], str]:
    if not isinstance(doc, CrawlDocument):
        raise CrawlRetrievalBridgeError("CrawlDocument required")
    if not doc.text:
        raise CrawlRetrievalBridgeError("empty crawl document")
    observed = sha256(doc.text.encode("utf-8")).hexdigest()
    if observed != doc.content_hash:
        raise CrawlRetrievalBridgeError("crawl content hash mismatch")
    provenance = dict(doc.provenance)
    required = {
        "schema": "skeleton.ai.crawl.provenance.v1",
        "canonical_url": doc.canonical_url,
        "fetched_url": doc.fetched_url,
        "fetched_at": doc.fetched_at,
        "content_hash": doc.content_hash,
    }
    for key, expected in required.items():
        if provenance.get(key) != expected:
            raise CrawlRetrievalBridgeError(f"crawl provenance {key} mismatch")
    status = provenance.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or not 200 <= status < 300:
        raise CrawlRetrievalBridgeError("crawl provenance status is not successful")
    return provenance, _digest_json(provenance)


def bridge_crawl_document(
    doc: CrawlDocument,
    *,
    lexical_score: float = 0.0,
    semantic_score: float = 0.0,
    freshness_score: float = 1.0,
    token_cost: int,
    priority: int = 0,
) -> CrawlRetrievalRecord:
    """Verify crawler evidence and emit canonical retrieval/context contracts."""
    provenance, provenance_digest = _verified_provenance(doc)
    if isinstance(token_cost, bool) or not isinstance(token_cost, int) or token_cost < 0:
        raise CrawlRetrievalBridgeError("invalid token_cost")
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise CrawlRetrievalBridgeError("invalid priority")

    candidate = RetrievalCandidate(
        candidate_id=f"crawl:{doc.content_hash}",
        source=doc.canonical_url,
        content_digest=doc.content_hash,
        provenance_digest=provenance_digest,
        lexical_ppm=_ppm(lexical_score, "lexical_score"),
        semantic_ppm=_ppm(semantic_score, "semantic_score"),
        freshness_ppm=_ppm(freshness_score, "freshness_score"),
    )
    item = ContextItem(
        item_id=candidate.candidate_id,
        kind="external-crawl-data",
        content_digest=doc.content_hash,
        provenance_digest=provenance_digest,
        token_cost=token_cost,
        priority=priority,
        mandatory=False,
    )
    return CrawlRetrievalRecord(candidate, item, provenance_digest, doc.canonical_url)


__all__ = [
    "CrawlRetrievalBridgeError",
    "CrawlRetrievalRecord",
    "bridge_crawl_document",
]
