"""Deterministic assembly of verified crawl evidence into an FLGB-03 context selection."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Sequence

from skeleton.ai.context.flgb_context_runtime import (
    CompiledContext,
    ContextContractError,
    compile_context,
    hybrid_rank,
)

from .core import CrawlDocument
from .evidence_retrieval_bridge import CrawlRetrievalBridgeError, CrawlRetrievalRecord, bridge_crawl_document


@dataclass(frozen=True)
class CrawlContextBundle:
    records: tuple[CrawlRetrievalRecord, ...]
    compiled: CompiledContext
    text: str
    text_digest: str

    def __post_init__(self) -> None:
        observed = sha256(self.text.encode("utf-8")).hexdigest()
        if observed != self.text_digest:
            raise CrawlRetrievalBridgeError("compiled crawl text digest mismatch")
        selected = set(self.compiled.selected_ids)
        record_ids = {record.context_item.item_id for record in self.records}
        if not selected <= record_ids:
            raise CrawlRetrievalBridgeError("compiled context references unknown crawl record")


def compile_crawl_context(
    operation_id: str,
    documents: Sequence[CrawlDocument],
    *,
    token_costs: Sequence[int],
    lexical_scores: Sequence[float] | None = None,
    semantic_scores: Sequence[float] | None = None,
    freshness_scores: Sequence[float] | None = None,
    token_budget: int,
    retrieval_limit: int = 20,
) -> CrawlContextBundle:
    """Bridge, rank and compile crawl data without granting it instruction authority."""
    count = len(documents)
    if len(token_costs) != count:
        raise CrawlRetrievalBridgeError("token_cost count mismatch")
    lexical = tuple(lexical_scores if lexical_scores is not None else (0.0,) * count)
    semantic = tuple(semantic_scores if semantic_scores is not None else (0.0,) * count)
    freshness = tuple(freshness_scores if freshness_scores is not None else (1.0,) * count)
    if any(len(values) != count for values in (lexical, semantic, freshness)):
        raise CrawlRetrievalBridgeError("retrieval score count mismatch")

    records = tuple(
        bridge_crawl_document(
            doc,
            lexical_score=lexical[index],
            semantic_score=semantic[index],
            freshness_score=freshness[index],
            token_cost=token_costs[index],
        )
        for index, doc in enumerate(documents)
    )
    ids = [record.candidate.candidate_id for record in records]
    if len(set(ids)) != len(ids):
        raise CrawlRetrievalBridgeError("duplicate crawl content identity")

    ranked = hybrid_rank(
        tuple(record.candidate for record in records),
        limit=retrieval_limit,
    )
    by_id = {record.candidate.candidate_id: record for record in records}
    ranked_records = tuple(by_id[candidate.candidate_id] for candidate in ranked)
    # Ranking order is reflected as priority while compile_context remains the
    # sole authority for budget admission.
    ranked_items = tuple(
        type(record.context_item)(
            item_id=record.context_item.item_id,
            kind=record.context_item.kind,
            content_digest=record.context_item.content_digest,
            provenance_digest=record.context_item.provenance_digest,
            token_cost=record.context_item.token_cost,
            priority=len(ranked_records) - index,
            mandatory=False,
        )
        for index, record in enumerate(ranked_records)
    )
    try:
        compiled = compile_context(operation_id, ranked_items, token_budget=token_budget)
    except ContextContractError as exc:
        raise CrawlRetrievalBridgeError("crawl context compilation failed") from exc

    selected = set(compiled.selected_ids)
    selected_records = tuple(
        record for record in ranked_records if record.candidate.candidate_id in selected
    )
    text = "\n\n".join(
        next(doc.text for doc in documents if doc.content_hash == record.candidate.content_digest)
        for record in selected_records
    )
    return CrawlContextBundle(
        records=ranked_records,
        compiled=compiled,
        text=text,
        text_digest=sha256(text.encode("utf-8")).hexdigest(),
    )


__all__ = ["CrawlContextBundle", "compile_crawl_context"]
