"""Bounded, indexed Dragon microknowledge projections of canonical concepts.

Quantized relevance coefficients are retrieval weights, NOT trained neural
parameters. No raw conversation or public text is silently promoted to truth.
SQLite holds rebuildable projections under the crawler's existing store owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
import sqlite3

from .dragon_knowledge_graph import DragonKnowledgeGraph
from .dragon_resource_session import ResourcePlan

_WORD = re.compile(r"[a-z0-9_]{2,48}", re.I)
FACTORS = frozenset(("genre", "era", "engine", "platform", "story", "timesetting",
                     "mechanic", "rendering", "input", "audio", "accessibility"))


def _id(value: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
        raise ValueError("invalid microknowledge identity")


def _terms(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(_WORD.findall(text.lower()))))[:128]


@dataclass(frozen=True, slots=True)
class MicroHit:
    concept_id: str
    statement: str
    relevance_weight: int
    evidence_ref: str
    trust: str = "untrusted_reference"


@dataclass(frozen=True, slots=True)
class MicroContext:
    hits: tuple[MicroHit, ...]
    bytes_used: int
    candidates_examined: int
    missing_factors: tuple[str, ...]
    context_digest: str


class DragonMicroKnowledge:
    def __init__(self, graph: DragonKnowledgeGraph) -> None:
        self.graph, self.db = graph, graph.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS dragon_microknowledge(
                owner TEXT NOT NULL, concept_id TEXT NOT NULL, evidence_ref TEXT NOT NULL,
                expires_at REAL NOT NULL, content_digest TEXT NOT NULL,
                PRIMARY KEY(owner,concept_id));
            CREATE TABLE IF NOT EXISTS dragon_micro_postings(
                owner TEXT NOT NULL, term TEXT NOT NULL, concept_id TEXT NOT NULL,
                PRIMARY KEY(owner,term,concept_id));
            CREATE TABLE IF NOT EXISTS dragon_micro_facets(
                owner TEXT NOT NULL, factor TEXT NOT NULL, value TEXT NOT NULL,
                concept_id TEXT NOT NULL, PRIMARY KEY(owner,factor,value,concept_id));
        """)

    def index(self, owner: str, concept_id: str, facets: dict[str, str], *,
              evidence_ref: str, expires_at: float, authorized: bool) -> None:
        from math import isfinite
        if authorized is not True:
            raise PermissionError("microknowledge indexing requires authorization")
        _id(owner); _id(concept_id); _id(evidence_ref)
        if isinstance(expires_at, bool) or not isfinite(expires_at):
            raise ValueError("invalid evidence expiry")
        self._facets(facets)
        row = self.db.execute("SELECT domain,statement FROM dragon_knowledge_concepts WHERE owner=? AND concept_id=?",
                              (owner, concept_id)).fetchone()
        if row is None:
            raise ValueError("index requires canonical concept")
        if len(row[1].encode()) > 4096:
            raise ValueError("concept exceeds microchunk budget")
        terms = _terms(concept_id + " " + row[0] + " " + row[1])
        digest = sha256(row[1].encode()).hexdigest()
        with self.db:
            # Acquire the writer lock before capacity checks, including across
            # separate connections. Failure rolls back the old projection.
            self.db.execute("DELETE FROM dragon_micro_postings WHERE owner=? AND concept_id=?", (owner, concept_id))
            if not self.db.execute("SELECT 1 FROM dragon_microknowledge WHERE owner=? AND concept_id=?", (owner, concept_id)).fetchone():
                count = self.db.execute("SELECT count(*) FROM dragon_microknowledge WHERE owner=?", (owner,)).fetchone()[0]
                if count >= 10000:
                    raise ValueError("microknowledge owner capacity reached")
            self.db.execute("DELETE FROM dragon_micro_facets WHERE owner=? AND concept_id=?", (owner, concept_id))
            self.db.execute("INSERT OR REPLACE INTO dragon_microknowledge VALUES(?,?,?,?,?)",
                            (owner, concept_id, evidence_ref, expires_at, digest))
            self.db.executemany("INSERT INTO dragon_micro_postings VALUES(?,?,?)",
                                ((owner, t, concept_id) for t in terms))
            self.db.executemany("INSERT INTO dragon_micro_facets VALUES(?,?,?,?)",
                                ((owner, k, v, concept_id) for k, v in sorted(facets.items())))

    @staticmethod
    def _facets(facets: dict[str, str]) -> None:
        if not isinstance(facets, dict) or len(facets) > len(FACTORS):
            raise ValueError("invalid facets")
        for key, value in facets.items():
            if key not in FACTORS:
                raise ValueError("unsupported knowledge factor")
            _id(value)

    def retrieve(self, owner: str, query: str, facets: dict[str, str], plan: ResourcePlan,
                 *, now: float, authorized: bool) -> MicroContext:
        from math import isfinite
        if authorized is not True:
            raise PermissionError("microknowledge retrieval requires authorization")
        _id(owner); self._facets(facets)
        if not isinstance(query, str) or not 1 <= len(query) <= 512 or isinstance(now, bool) or not isfinite(now):
            raise ValueError("invalid microknowledge query")
        if not 0 <= plan.retrieval_candidates <= 256 or not 0 <= plan.context_bytes <= 65536 or not 1 <= plan.chunk_bytes <= 4096:
            raise ValueError("invalid retrieval plan")
        terms = _terms(query)[:16]
        if not terms or not plan.retrieval_candidates or not plan.context_bytes:
            return MicroContext((), 0, 0, tuple(sorted(facets)), sha256(b"[]").hexdigest())
        # Covering posting indexes avoid loading the complete graph. Facet gates
        # occur BEFORE candidate LIMIT, so incompatible eras cannot hide matches.
        params: list[object] = [owner, *terms, now]
        predicates = []
        for k, v in sorted(facets.items()):
            predicates.append("EXISTS(SELECT 1 FROM dragon_micro_facets f WHERE f.owner=p.owner AND f.concept_id=p.concept_id AND f.factor=? AND f.value=?)")
            params.extend((k, v))
        sql = f"""SELECT p.concept_id,count(*) FROM dragon_micro_postings p
            JOIN dragon_microknowledge m ON m.owner=p.owner AND m.concept_id=p.concept_id
            WHERE p.owner=? AND p.term IN ({','.join('?' for _ in terms)}) AND m.expires_at>?
            {'AND ' + ' AND '.join(predicates) if predicates else ''}
            GROUP BY p.concept_id ORDER BY count(*) DESC,p.concept_id LIMIT ?"""
        params.append(plan.retrieval_candidates)
        # SQLite's VM instruction budget bounds pathological high-frequency terms.
        instructions = [0]
        def progress() -> int:
            instructions[0] += 1000
            return int(instructions[0] > 200000)
        self.db.set_progress_handler(progress, 1000)
        try:
            rows = self.db.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if instructions[0] > 200000:
                raise ValueError("microknowledge search instruction budget exceeded; narrow query") from exc
            raise
        finally:
            self.db.set_progress_handler(None, 0)
        hits = []; used = 2  # Serialized context list brackets.
        for concept_id, count in rows:
            row = self.db.execute("""SELECT c.statement,m.evidence_ref,m.content_digest
                FROM dragon_microknowledge m JOIN dragon_knowledge_concepts c
                ON c.owner=m.owner AND c.concept_id=m.concept_id WHERE m.owner=? AND m.concept_id=?""",
                (owner, concept_id)).fetchone()
            if row is None or sha256(row[0].encode()).hexdigest() != row[2]:
                raise ValueError("microknowledge projection drift; rebuild required")
            hit = MicroHit(concept_id, row[0], min(255, count * 255 // len(terms)), row[1])
            encoded = json.dumps([hit.concept_id, hit.statement, hit.relevance_weight, hit.evidence_ref, hit.trust], ensure_ascii=True, separators=(",", ":")).encode()
            delta = len(encoded) + (1 if hits else 0)
            if len(encoded) > plan.chunk_bytes or used + delta > plan.context_bytes:
                continue
            used += delta
            hits.append(hit)
        digest = sha256(json.dumps([(h.concept_id, h.statement, h.relevance_weight, h.evidence_ref) for h in hits], separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        return MicroContext(tuple(hits), used, len(rows), () if hits else tuple(sorted(facets)), digest)

    def remove(self, owner: str, concept_id: str, *, authorized: bool) -> None:
        if authorized is not True:
            raise PermissionError("microknowledge deletion requires authorization")
        _id(owner); _id(concept_id)
        with self.db:
            for table in ("dragon_microknowledge", "dragon_micro_postings", "dragon_micro_facets"):
                self.db.execute(f"DELETE FROM {table} WHERE owner=? AND concept_id=?", (owner, concept_id))
