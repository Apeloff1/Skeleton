"""Snapshot-bound typed evidence graph for Dragon research operations.

This is a *projection*, not another graph database or a truth engine. The
authoritative Mongo CrawlRun, owner grant, and complete source-use policy
must be checked before assembling any graph node. The graph stores source
identities, exact anchored passage hashes, objective IDs, and claim IDs,
never untrusted passage bodies or model instructions.

Nodes and edges are uniquely identified, finite, deterministic, and scoped
to a snapshot. Source lineage is validated independently before insertion.
Withdrawn provenance propagates along derivation/revision edges but never
along mere citations; cited material cannot regain source-use rights.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .claims import ClaimReviewMatrix
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .independence_audit import IndependenceAudit
from .lineage import SourceLink, invalidation_closure, validate_lineage
from .objectives import ObjectivePlan
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion
from .source_index import EphemeralIndex


_NODE_TYPES = frozenset(("source", "passage", "objective", "claim"))
_EDGE_TYPES = frozenset((
    "contains_passage", "matches_objective", "addresses_objective",
    "supports_claim", "refutes_claim", "context_for_claim",
    "derived_from", "revision_of", "cites", "same_content",
))


@dataclass(frozen=True)
class EvidenceVertex:
    vertex_id: str
    kind: str
    reference: str
    status: str
    source_id: str | None = None
    origin: str | None = None
    review_required: bool = True

    def __post_init__(self):
        if self.kind not in _NODE_TYPES:
            raise ValueError("unsupported evidence vertex type")
        if not self.vertex_id.startswith(self.kind + ":"):
            raise ValueError("invalid evidence vertex identity")
        if self.status not in ("policy_held", "external_unreviewed", "operator_objective",
                               "claim_requires_review"):
            raise ValueError("unsupported evidence vertex state")
        if self.review_required is not True:
            raise PermissionError("evidence graph cannot clear human review")


@dataclass(frozen=True)
class EvidenceArc:
    origin_id: str
    target_id: str
    relation: str
    basis: str
    accepted_for_truth: bool = False

    def __post_init__(self):
        if self.relation not in _EDGE_TYPES:
            raise ValueError("unsupported evidence relation")
        if self.origin_id == self.target_id:
            raise ValueError("self-loop evidence relation")
        if self.accepted_for_truth:
            raise PermissionError("graph relation cannot certify facts")


@dataclass(frozen=True)
class ObjectiveNeighborhood:
    objective_id: str
    distinct_source_ids: tuple[str, ...]
    exact_passage_count: int
    distinct_hosts: tuple[str, ...]
    associated_claim_ids: tuple[str, ...]
    held_source_ids: tuple[str, ...]
    independence_attested: bool = False
    operator_review_complete: bool = False


@dataclass(frozen=True)
class GraphIntegrity:
    source_count: int
    held_source_count: int
    passage_count: int
    objective_count: int
    claim_count: int
    vertex_count: int
    edge_count: int
    orphan_count: int
    unique_hosts: int
    graph_digest: str
    knowledge_verified: bool = False


@dataclass(frozen=True)
class EvidenceGraph:
    mandate_digest: str
    source_snapshot_digest: str
    source_policy_digest: str
    source_index_digest: str
    retrieval_digest: str
    objective_plan_digest: str
    vertices: tuple[EvidenceVertex, ...]
    arcs: tuple[EvidenceArc, ...]
    objectives: tuple[ObjectiveNeighborhood, ...]
    tainted_source_ids: tuple[str, ...]
    integrity: GraphIntegrity
    graph_digest: str
    may_execute_network: bool = False
    may_publish: bool = False


def _vertex(kind: str, key: str) -> str:
    return kind + ":" + key


def _passage_key(source_id: str, start: int, end: int, passage_hash: str) -> str:
    return f"{source_id}:{start}:{end}:{passage_hash}"


def assemble_evidence_graph(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    objectives: ObjectivePlan,
    index: EphemeralIndex,
    retrieval: RetrievalFusion,
    *,
    now: float,
    authorized: bool,
    claims: ClaimReviewMatrix | None = None,
    independence: IndependenceAudit | None = None,
    links: Iterable[SourceLink] = (),
    max_vertices: int = 8192,
    max_arcs: int = 16_384,
) -> EvidenceGraph:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_vertices, "graph vertex cap", 1, 8192)
    integer(max_arcs, "graph arc cap", 1, 16_384)
    if any(x != mandate.fingerprint for x in (
        policy.mandate_digest, objectives.mandate_digest,
        index.mandate_digest, retrieval.mandate_digest
    )):
        raise PermissionError("foreign mandate evidence graph")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    revision = canonical["snapshot_digest"]
    if any(x != revision for x in (
        policy.source_snapshot_digest, index.source_snapshot_digest,
        retrieval.source_snapshot_digest,
    )):
        raise PermissionError("mixed source revisions in evidence graph")
    if retrieval.index_digest != index.index_digest or (
        retrieval.excluded_sources != policy.excluded_source_ids
    ):
        raise PermissionError("graph retrieval not bound to current policy and index")
    if len(set(policy.allowed_source_ids) | set(policy.excluded_source_ids)) != len(
        canonical["sources"]
    ):
        raise PermissionError("incomplete source-policy graph universe")
    if set(policy.allowed_source_ids) & set(policy.excluded_source_ids):
        raise PermissionError("source-policy graph overlap")
    if set(policy.allowed_source_ids) | set(policy.excluded_source_ids) != set(canonical["sources"]):
        raise PermissionError("unrecognized source-policy graph identity")
    if independence and (independence.mandate_digest != mandate.fingerprint
                         or independence.source_snapshot_digest != revision):
        raise PermissionError("foreign independence audit")
    if claims and claims.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign claim graph")
    if independence and (not claims or independence.matrix_digest != claims.matrix_digest):
        raise PermissionError("independence proof requires corresponding claims")
    lineage = validate_lineage(canonical["sources"], tuple(links), limits=mandate.limits)
    impact = invalidation_closure(
        canonical["sources"], lineage,
        revoked=policy.excluded_source_ids,
        limits=mandate.limits,
    )
    tainted = set(impact.affected_source_ids)
    by_vertex: dict[str, EvidenceVertex] = {}
    by_arc: dict[tuple[str, str, str, str], EvidenceArc] = {}
    def add_node(row: EvidenceVertex) -> None:
        if row.vertex_id in by_vertex:
            if by_vertex[row.vertex_id] != row:
                raise ValueError("ambiguous duplicate evidence vertex")
            return
        if len(by_vertex) >= max_vertices:
            raise ValueError("evidence vertex capacity exceeded")
        by_vertex[row.vertex_id] = row
    def add_edge(source: str, destination: str, relation: str, basis: str) -> None:
        if source not in by_vertex or destination not in by_vertex:
            raise PermissionError("evidence relation has dangling endpoint")
        row = EvidenceArc(source, destination, relation, basis)
        key = source, destination, relation, basis
        if key not in by_arc and len(by_arc) >= max_arcs:
            raise ValueError("evidence arc capacity exceeded")
        by_arc[key] = row
    for source_id, source in sorted(canonical["sources"].items()):
        add_node(EvidenceVertex(
            _vertex("source", source_id), "source", source_id,
            "policy_held" if source_id in tainted else "external_unreviewed",
            source_id=source_id,
            origin=source["canonical_url"],
        ))
    for objective in objectives.objectives:
        add_node(EvidenceVertex(
            _vertex("objective", objective.objective_id), "objective",
            objective.objective_id, "operator_objective",
        ))
    if claims:
        objectives_by_id = {x.objective_id for x in objectives.objectives}
        for claim in claims.claims:
            if claim.objective_id not in objectives_by_id:
                raise PermissionError("claim objective outside operator mandate")
            add_node(EvidenceVertex(
                _vertex("claim", claim.claim_id), "claim",
                claim.claim_id, "claim_requires_review",
            ))
            add_edge(_vertex("claim", claim.claim_id),
                     _vertex("objective", claim.objective_id),
                     "addresses_objective", claims.matrix_digest)
    index_keys = set()
    for item in index.passages:
        key = (item.source_id, item.passage_hash, item.start, item.end)
        if key in index_keys:
            raise ValueError("duplicate indexed passage")
        index_keys.add(key)
        if item.source_id not in policy.allowed_source_ids:
            raise PermissionError("held source leaked into graph index")
        source = canonical["sources"][item.source_id]
        if source["text"][item.start:item.end] != item.text:
            raise PermissionError("indexed graph span no longer matches captured text")
    by_objective: dict[str, dict[str, set]] = {
        x.objective_id: {"sources": set(), "hosts": set(), "passages": set(), "claims": set()}
        for x in objectives.objectives
    }
    for hit in retrieval.results:
        key = hit.source_id, hit.passage_hash, hit.start, hit.end
        if key not in index_keys:
            raise PermissionError("unindexed retrieval hit in evidence graph")
        if hit.source_id in tainted:
            raise PermissionError("lineage-tainted source may not enter evidence graph")
        source = canonical["sources"][hit.source_id]
        if source["canonical_url"] != hit.canonical_url:
            raise PermissionError("evidence graph source URL rebound")
        node = _vertex("passage", _passage_key(hit.source_id, hit.start, hit.end, hit.passage_hash))
        add_node(EvidenceVertex(
            node, "passage", hit.passage_hash, "external_unreviewed",
            source_id=hit.source_id, origin=hit.canonical_url,
        ))
        add_edge(_vertex("source", hit.source_id), node,
                 "contains_passage", index.index_digest)
        for oid in hit.matched_objective_ids:
            if oid not in by_objective:
                raise PermissionError("retrieval claimed undeclared objective")
            add_edge(node, _vertex("objective", oid),
                     "matches_objective", retrieval.fusion_digest)
            target = by_objective[oid]
            target["sources"].add(hit.source_id)
            target["hosts"].add(hit.host)
            target["passages"].add(key)
    if claims:
        for claim in claims.claims:
            for stance, ids in (
                ("supports_claim", claim.support_sources),
                ("refutes_claim", claim.refute_sources),
                ("context_for_claim", claim.context_sources),
            ):
                for source_id in ids:
                    if source_id not in canonical["sources"]:
                        raise PermissionError("claim cites unknown source")
                    if source_id in tainted:
                        # Suppress the edge and make it a held source; the
                        # original claim assessment is still never promoted.
                        continue
                    add_edge(_vertex("source", source_id),
                             _vertex("claim", claim.claim_id),
                             stance, claims.matrix_digest)
                    by_objective[claim.objective_id]["claims"].add(claim.claim_id)
    for link in lineage:
        add_edge(
            _vertex("source", link.child_source_id),
            _vertex("source", link.parent_source_id),
            link.relation, "caller_attested_lineage_not_fact_proof",
        )
    neighborhoods = []
    for oid, counts in sorted(by_objective.items()):
        affected = tuple(sorted(counts["sources"] & tainted))
        neighborhoods.append(ObjectiveNeighborhood(
            objective_id=oid,
            distinct_source_ids=tuple(sorted(counts["sources"])),
            exact_passage_count=len(counts["passages"]),
            distinct_hosts=tuple(sorted(counts["hosts"])),
            associated_claim_ids=tuple(sorted(counts["claims"])),
            held_source_ids=affected,
        ))
    orphan_count = 0
    used = {row.origin_id for row in by_arc.values()} | {
        row.target_id for row in by_arc.values()
    }
    for identity in by_vertex:
        if identity not in used and not identity.startswith("objective:"):
            orphan_count += 1
    vertices = tuple(sorted(by_vertex.values(), key=lambda x: x.vertex_id))
    arcs = tuple(sorted(by_arc.values(),
                        key=lambda x: (x.origin_id, x.target_id, x.relation, x.basis)))
    integrity_body = {
        "source_count": len(canonical["sources"]),
        "held_source_count": len(tainted),
        "passage_count": sum(x.kind == "passage" for x in vertices),
        "objective_count": len(objectives.objectives),
        "claim_count": len(claims.claims) if claims else 0,
        "vertex_count": len(vertices), "edge_count": len(arcs),
        "orphan_count": orphan_count,
        "unique_hosts": len({urlsplit(x.origin).hostname for x in vertices
                             if x.kind == "source"}),
    }
    integrity = GraphIntegrity(**integrity_body, graph_digest=digest(integrity_body))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": revision, "policy": policy.policy_digest,
        "objectives": objectives.plan_digest,
        "index": index.index_digest, "retrieval": retrieval.fusion_digest,
        "claims": claims.matrix_digest if claims else None,
        "independence": independence.audit_digest if independence else None,
        "vertices": [asdict(x) for x in vertices],
        "arcs": [asdict(x) for x in arcs],
        "neighborhoods": [asdict(x) for x in neighborhoods],
        "tainted": sorted(tainted),
        "integrity": asdict(integrity),
    }
    return EvidenceGraph(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=revision,
        source_policy_digest=policy.policy_digest,
        source_index_digest=index.index_digest,
        retrieval_digest=retrieval.fusion_digest,
        objective_plan_digest=objectives.plan_digest,
        vertices=vertices, arcs=arcs, objectives=tuple(neighborhoods),
        tainted_source_ids=tuple(sorted(tainted)),
        integrity=integrity, graph_digest=digest(payload),
    )
