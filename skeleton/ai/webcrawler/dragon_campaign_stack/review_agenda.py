"""Review-only queue compiler over the canonical Dragon evidence graph.

Every item is a finite operator task, not an autonomous write order. Tasks
are source/version anchored, deterministically deduplicated, dependency
checked, and safely prioritized. External text has no authority to enqueue
work or set a task's outcome. This queue is ephemeral: persistent review
decisions belong to the existing reviewed-knowledge owner.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from .claims import ClaimReviewMatrix
from .contracts import CampaignMandate, bounded_text, digest, finite, integer
from .coverage import CoverageReport
from .evidence_graph import EvidenceGraph
from .independence_audit import IndependenceAudit
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion

_KINDS = frozenset((
    "source_policy", "passage_integrity", "source_provenance",
    "claim_contradiction", "claim_corroboration", "objective_gap",
    "human_fact_review",
))
_PRIORITIES = {
    "source_policy": 1.0,
    "claim_contradiction": .97,
    "source_provenance": .94,
    "passage_integrity": .84,
    "claim_corroboration": .82,
    "objective_gap": .76,
    "human_fact_review": .72,
}


@dataclass(frozen=True)
class ReviewTask:
    task_id: str
    task_type: str
    subject_id: str
    objective_id: str | None
    source_id: str | None
    passage_hash: str | None
    reason: str
    priority: float
    predecessors: tuple[str, ...]
    state: str = "pending_human_review"
    externally_executable: bool = False

    def __post_init__(self) -> None:
        if self.task_type not in _KINDS:
            raise ValueError("unsupported human review task")
        bounded_text(self.task_id, "review task id", 64)
        bounded_text(self.subject_id, "review task subject", 192)
        bounded_text(self.reason, "review reason", 192)
        finite(self.priority, "review urgency", 0, 1)
        if self.state != "pending_human_review" or self.externally_executable is not False:
            raise PermissionError("review tasks cannot authorize execution")
        if len(self.predecessors) > 128 or len(set(self.predecessors)) != len(self.predecessors):
            raise ValueError("invalid review prerequisite list")


@dataclass(frozen=True)
class ReviewAgenda:
    mandate_digest: str
    source_snapshot_digest: str
    graph_digest: str
    policy_digest: str
    retrieval_digest: str
    tasks: tuple[ReviewTask, ...]
    ready_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    counts_by_type: tuple[tuple[str, int], ...]
    max_working_set: int
    agenda_digest: str
    human_authorization_proven: bool = False
    knowledge_publication_authorized: bool = False


def _task_id(kind: str, subject: str, reason: str, snapshot: str) -> str:
    return "r" + digest({
        "kind": kind, "subject": subject, "reason": reason,
        "snapshot": snapshot,
    })[:46]


def compile_review_agenda(
    mandate: CampaignMandate,
    graph: EvidenceGraph,
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    coverage: CoverageReport,
    *,
    now: float,
    authorized: bool,
    claims: ClaimReviewMatrix | None = None,
    independence: IndependenceAudit | None = None,
    max_tasks: int = 256,
    ready_window: int = 32,
) -> ReviewAgenda:
    mandate.admit(now=now, authorized=authorized)
    integer(max_tasks, "review task budget", 1, 512)
    integer(ready_window, "review working set", 1, 128)
    if any(x != mandate.fingerprint for x in (
        graph.mandate_digest, policy.mandate_digest,
        retrieval.mandate_digest, coverage.mandate_digest,
    )):
        raise PermissionError("cross-mandate agenda")
    if graph.source_snapshot_digest != policy.source_snapshot_digest or (
        graph.source_snapshot_digest != retrieval.source_snapshot_digest
    ):
        raise PermissionError("agenda evidence revision mismatch")
    if graph.source_policy_digest != policy.policy_digest or (
        graph.retrieval_digest != retrieval.fusion_digest
    ):
        raise PermissionError("agenda attached to foreign policy or retrieval")
    if claims is not None and claims.mandate_digest != mandate.fingerprint:
        raise PermissionError("foreign agenda claim matrix")
    if independence is not None and (
        claims is None or independence.matrix_digest != claims.matrix_digest
        or independence.source_snapshot_digest != graph.source_snapshot_digest
    ):
        raise PermissionError("independence audit not attached to claim matrix")
    by_task = {}
    dependencies = defaultdict(set)
    by_subject = defaultdict(set)
    revision = graph.source_snapshot_digest
    def insert(kind: str, subject: str, reason: str, *,
               objective: str | None = None, source: str | None = None,
               passage: str | None = None, priority: float | None = None,
               after=()) -> str:
        identity = _task_id(kind, subject, reason, revision)
        if identity not in by_task and len(by_task) >= max_tasks:
            raise ValueError("review agenda task budget exceeded")
        urgency = _PRIORITIES[kind] if priority is None else priority
        row = ReviewTask(
            task_id=identity, task_type=kind, subject_id=subject,
            objective_id=objective, source_id=source, passage_hash=passage,
            reason=reason, priority=round(urgency, 8),
            predecessors=tuple(sorted(set(after))),
        )
        if identity in by_task and by_task[identity] != row:
            raise ValueError("ambiguous review queue task")
        by_task[identity] = row
        dependencies[identity].update(after)
        by_subject[(kind, subject)].add(identity)
        return identity
    source_review = {}
    for source_id in policy.excluded_source_ids:
        source_review[source_id] = insert(
            "source_policy", source_id, "current_source_policy_exclusion",
            source=source_id,
        )
    for source_id in graph.tainted_source_ids:
        if source_id not in source_review:
            source_review[source_id] = insert(
                "source_provenance", source_id,
                "derived_from_held_source_needs_origin_review",
                source=source_id,
            )
    passage_reviews = defaultdict(list)
    seen_passages = set()
    for hit in retrieval.results:
        identity = (hit.source_id, hit.passage_hash, hit.start, hit.end)
        if identity in seen_passages:
            raise ValueError("duplicate reviewed passage")
        seen_passages.add(identity)
        if hit.source_id in graph.tainted_source_ids:
            raise PermissionError("tainted passage leaked into review agenda")
        task = insert(
            "passage_integrity",
            f"{hit.source_id}:{hit.start}:{hit.end}:{hit.passage_hash}",
            "human_verify_source_and_exact_passage",
            source=hit.source_id, passage=hit.passage_hash,
            after=tuple([source_review[hit.source_id]]
                        if hit.source_id in source_review else ()),
        )
        for objective_id in hit.matched_objective_ids:
            passage_reviews[objective_id].append(task)
    corroboration = defaultdict(list)
    if independence is not None:
        for finding in independence.findings:
            subject = f"{finding.left_group}:{finding.right_group}"
            correlated = insert(
                "source_provenance", subject,
                "attested_groups_share_origin_or_content",
            )
            corroboration[finding.left_group].append(correlated)
            corroboration[finding.right_group].append(correlated)
    if claims is not None:
        for claim in claims.claims:
            prerequisites = []
            if claim.conflicted:
                prerequisites.append(insert(
                    "claim_contradiction", claim.claim_id,
                    "support_and_refutation_overlap",
                    objective=claim.objective_id,
                ))
            if claim.unconfirmed_citations or not claim.attested_support_groups:
                prerequisites.append(insert(
                    "claim_corroboration", claim.claim_id,
                    "source_citations_or_independence_unconfirmed",
                    objective=claim.objective_id,
                ))
            if independence is not None:
                for counter in independence.claims:
                    if counter.claim_id == claim.claim_id:
                        for group_id in counter.potentially_correlated_groups:
                            prerequisites.extend(corroboration[group_id])
            prerequisites.extend(passage_reviews[claim.objective_id][:16])
            insert(
                "human_fact_review", claim.claim_id,
                "no_automatic_knowledge_verification",
                objective=claim.objective_id,
                after=tuple(prerequisites),
            )
    for objective in coverage.objectives:
        if objective.evidence_coverage_ratio < 1.0 or objective.reasons:
            insert(
                "objective_gap", objective.objective_id,
                "research_objective_remains_unreviewed",
                objective=objective.objective_id,
                priority=round(min(1.0, .76 +
                    .2 * (1.0 - objective.evidence_coverage_ratio)), 8),
                after=tuple(passage_reviews[objective.objective_id][:16]),
            )
    if any(not keys.issubset(by_task) for keys in dependencies.values()):
        raise ValueError("dangling review prerequisites")
    indegree = {tid: len(keys) for tid, keys in dependencies.items()}
    for identity in by_task:
        indegree.setdefault(identity, 0)
    pending = sorted((tid for tid, degree in indegree.items() if not degree),
                     key=lambda tid: (-by_task[tid].priority, tid))
    visited = []
    outgoing = defaultdict(list)
    for tid, prerequisites in dependencies.items():
        for pred in prerequisites:
            outgoing[pred].append(tid)
    while pending:
        tid = pending.pop(0)
        visited.append(tid)
        for child in outgoing[tid]:
            indegree[child] -= 1
            if indegree[child] == 0:
                pending.append(child)
        pending.sort(key=lambda x: (-by_task[x].priority, x))
    if len(visited) != len(by_task):
        raise ValueError("cyclic human review dependencies")
    ordering = tuple(sorted(by_task.values(), key=lambda x: (-x.priority, x.task_id)))
    ready = tuple(t.task_id for t in ordering if not t.predecessors)[:ready_window]
    blocked = tuple(t.task_id for t in ordering if t.predecessors)
    counts = defaultdict(int)
    for row in ordering:
        counts[row.task_type] += 1
    payload = {
        "mandate": mandate.fingerprint, "snapshot": revision,
        "graph": graph.graph_digest, "policy": policy.policy_digest,
        "retrieval": retrieval.fusion_digest, "coverage": coverage.coverage_digest,
        "claims": claims.matrix_digest if claims else None,
        "independence": independence.audit_digest if independence else None,
        "tasks": [asdict(x) for x in ordering],
        "ready": ready, "blocked": blocked,
        "working_set": ready_window,
    }
    return ReviewAgenda(
        mandate_digest=mandate.fingerprint, source_snapshot_digest=revision,
        graph_digest=graph.graph_digest, policy_digest=policy.policy_digest,
        retrieval_digest=retrieval.fusion_digest,
        tasks=ordering, ready_task_ids=ready, blocked_task_ids=blocked,
        counts_by_type=tuple(sorted(counts.items())),
        max_working_set=ready_window, agenda_digest=digest(payload),
    )
