"""Knowledge architecture: canonical claim ontology, typed relations and audits.

Stores source-independent knowledge concepts separately from individual
evidence readings. Relations are typed and revisioned; no confidence is
silently propagated across an edge. Supports provenance-linked graph
traversal with strict budgets and owner isolation.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import sqlite3


class Relation(str, Enum):
    REQUIRES = "requires"
    CAUSES = "causes"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    EXEMPLIFIES = "exemplifies"
    ALTERNATIVE_TO = "alternative_to"
    TESTS = "tests"
    DERIVED_FROM = "derived_from"


@dataclass(frozen=True)
class KnowledgeConcept:
    concept_id: str
    domain: str
    statement: str
    schema_version: int = 1


@dataclass(frozen=True)
class KnowledgeRelation:
    source_id: str
    target_id: str
    relation: Relation
    evidence_digest: str
    rationale: str


@dataclass(frozen=True)
class KnowledgeAudit:
    concept_count: int
    relation_count: int
    dangling_relations: int
    contradictory_pairs: int
    graph_fingerprint: str


def _validate_concept(concept: KnowledgeConcept) -> None:
    if not isinstance(concept.concept_id, str) or not 1 <= len(concept.concept_id) <= 128:
        raise ValueError("invalid concept id")
    if not isinstance(concept.domain, str) or not 1 <= len(concept.domain) <= 128:
        raise ValueError("invalid knowledge domain")
    if not isinstance(concept.statement, str) or not 1 <= len(concept.statement) <= 2000:
        raise ValueError("invalid knowledge statement")
    if concept.schema_version != 1:
        raise ValueError("unsupported knowledge schema")


class DragonKnowledgeGraph:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_knowledge_concepts(
                owner TEXT NOT NULL,concept_id TEXT NOT NULL,
                domain TEXT NOT NULL,statement TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                PRIMARY KEY(owner,concept_id))
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_knowledge_relations(
                owner TEXT NOT NULL,source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,relation TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,rationale TEXT NOT NULL,
                PRIMARY KEY(owner,source_id,target_id,relation,evidence_digest))
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS dragon_knowledge_relations_reverse
            ON dragon_knowledge_relations(owner,target_id)
        """)
        db.commit()

    def put_concept(self, owner: str, concept: KnowledgeConcept, *,
                    authorized: bool) -> None:
        if not authorized:
            raise PermissionError("concept writing requires authorization")
        _validate_concept(concept)
        with self.db:
            existing = self.db.execute("""
                SELECT domain,statement,schema_version
                FROM dragon_knowledge_concepts
                WHERE owner=? AND concept_id=?
            """, (owner, concept.concept_id)).fetchone()
            expected = (concept.domain, concept.statement, concept.schema_version)
            if existing:
                if existing != expected:
                    raise ValueError("immutable concept identity conflict")
                return
            self.db.execute(
                "INSERT INTO dragon_knowledge_concepts VALUES(?,?,?,?,?)",
                (owner, concept.concept_id, *expected),
            )

    def put_relation(self, owner: str, edge: KnowledgeRelation, *,
                     authorized: bool) -> None:
        if not authorized:
            raise PermissionError("relation writing requires authorization")
        if not isinstance(edge.relation, Relation):
            raise ValueError("unsupported relation type")
        if edge.source_id == edge.target_id:
            raise ValueError("self relations are not permitted")
        if not isinstance(edge.evidence_digest, str) or len(edge.evidence_digest) != 64 or any(
            c not in "0123456789abcdef" for c in edge.evidence_digest
        ):
            raise ValueError("invalid evidence digest")
        if not isinstance(edge.rationale, str) or not 1 <= len(edge.rationale) <= 1000:
            raise ValueError("invalid relation rationale")
        with self.db:
            for key in (edge.source_id, edge.target_id):
                if not self.db.execute("""
                    SELECT 1 FROM dragon_knowledge_concepts
                    WHERE owner=? AND concept_id=?
                """, (owner, key)).fetchone():
                    raise ValueError("relation references missing concept")
            self.db.execute("""
                INSERT OR IGNORE INTO dragon_knowledge_relations
                VALUES(?,?,?,?,?,?)
            """, (owner, edge.source_id, edge.target_id,
                  edge.relation.value, edge.evidence_digest, edge.rationale))

    def neighborhood(self, owner: str, root: str, *,
                     authorized: bool, max_depth: int = 2,
                     max_nodes: int = 200) -> tuple[KnowledgeConcept, ...]:
        if not authorized:
            raise PermissionError("graph traversal requires authorization")
        if not 0 <= max_depth <= 10 or not 1 <= max_nodes <= 10000:
            raise ValueError("invalid traversal budget")
        visited = set()
        frontier = [root]
        for depth in range(max_depth + 1):
            upcoming = []
            for concept_id in sorted(frontier):
                if concept_id in visited:
                    continue
                row = self.db.execute("""
                    SELECT domain,statement,schema_version
                    FROM dragon_knowledge_concepts
                    WHERE owner=? AND concept_id=?
                """, (owner, concept_id)).fetchone()
                if row is None:
                    continue
                visited.add(concept_id)
                if len(visited) >= max_nodes:
                    break
                if depth < max_depth:
                    rows = self.db.execute("""
                        SELECT target_id FROM dragon_knowledge_relations
                        WHERE owner=? AND source_id=?
                        UNION SELECT source_id FROM dragon_knowledge_relations
                        WHERE owner=? AND target_id=?
                    """, (owner, concept_id, owner, concept_id)).fetchall()
                    upcoming.extend(x[0] for x in rows)
            if len(visited) >= max_nodes:
                break
            frontier = sorted(set(upcoming) - visited)
        if len(visited) >= max_nodes and frontier:
            raise ValueError("graph traversal budget exhausted")
        if not visited:
            return ()
        return tuple(KnowledgeConcept(concept_id, *self.db.execute("""
            SELECT domain,statement,schema_version
            FROM dragon_knowledge_concepts
            WHERE owner=? AND concept_id=?
        """, (owner, concept_id)).fetchone()) for concept_id in sorted(visited))

    def audit(self, owner: str, *, authorized: bool) -> KnowledgeAudit:
        if not authorized:
            raise PermissionError("knowledge audit requires authorization")
        concepts = self.db.execute("""
            SELECT concept_id,domain,statement,schema_version
            FROM dragon_knowledge_concepts WHERE owner=? ORDER BY concept_id
        """, (owner,)).fetchall()
        edges = self.db.execute("""
            SELECT source_id,target_id,relation,evidence_digest,rationale
            FROM dragon_knowledge_relations WHERE owner=?
            ORDER BY source_id,target_id,relation,evidence_digest
        """, (owner,)).fetchall()
        known = {x[0] for x in concepts}
        dangling = sum(
            1 for x in edges if x[0] not in known or x[1] not in known
        )
        contradictions = sum(1 for x in edges if x[2] == Relation.CONTRADICTS.value)
        digest = sha256(json.dumps(
            [concepts, edges], sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        return KnowledgeAudit(
            len(concepts), len(edges), dangling, contradictions, digest,
        )

    def erase(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("knowledge erasure requires authorization")
        with self.db:
            self.db.execute(
                "DELETE FROM dragon_knowledge_relations WHERE owner=?", (owner,),
            )
            return self.db.execute(
                "DELETE FROM dragon_knowledge_concepts WHERE owner=?", (owner,),
            ).rowcount
