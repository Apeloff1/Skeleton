"""Versioned retrieval snapshots and explainable knowledge ranking.

Provides bounded lexical retrieval across immutable concepts, with optional
probability and evidence coverage signals. No fabricated semantic embeddings.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import sqlite3

from .dragon_knowledge_graph import DragonKnowledgeGraph, KnowledgeConcept


_WORD = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


@dataclass(frozen=True)
class RetrievalHit:
    concept_id: str
    statement: str
    domain: str
    score: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalSnapshot:
    owner: str
    query: str
    graph_fingerprint: str
    hits: tuple[RetrievalHit, ...]
    retrieval_fingerprint: str


def retrieve_knowledge(
    graph: DragonKnowledgeGraph, owner: str, query: str, *,
    authorized: bool, limit: int = 20, max_scan: int = 10000,
) -> RetrievalSnapshot:
    if not authorized:
        raise PermissionError("retrieval requires authorization")
    if not isinstance(query, str) or not 1 <= len(query) <= 500:
        raise ValueError("invalid query")
    if not 1 <= limit <= 1000 or not 1 <= max_scan <= 100000:
        raise ValueError("invalid retrieval budget")
    audit = graph.audit(owner, authorized=True)
    if audit.concept_count > max_scan:
        raise ValueError("graph exceeds retrieval scan budget")
    query_terms = set(_WORD.findall(query.lower()))
    if not query_terms:
        raise ValueError("query has no searchable terms")
    rows = graph.db.execute("""
        SELECT concept_id,domain,statement FROM dragon_knowledge_concepts
        WHERE owner=? ORDER BY concept_id
    """, (owner,)).fetchall()
    scored = []
    for concept_id, domain, statement in rows:
        title_tokens = set(_WORD.findall(concept_id.lower()))
        domain_tokens = set(_WORD.findall(domain.lower()))
        body_tokens = set(_WORD.findall(statement.lower()))
        matches = query_terms & (title_tokens | domain_tokens | body_tokens)
        if not matches:
            continue
        score = (
            3 * len(matches & title_tokens)
            + 2 * len(matches & domain_tokens)
            + len(matches & body_tokens)
        ) / max(1, len(query_terms))
        scored.append(RetrievalHit(
            concept_id, statement, domain, round(score, 6),
            tuple(sorted(matches)),
        ))
    scored.sort(key=lambda x: (-x.score, x.concept_id))
    hits = tuple(scored[:limit])
    fingerprint = sha256(json.dumps(
        [owner, query, audit.graph_fingerprint,
         [(x.concept_id, x.score) for x in hits]],
        separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()
    return RetrievalSnapshot(
        owner, query, audit.graph_fingerprint, hits, fingerprint,
    )
