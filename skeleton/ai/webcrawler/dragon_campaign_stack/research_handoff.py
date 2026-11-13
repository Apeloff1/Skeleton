"""Least-authority Jeeves research handoff from the existing Dragon Atlas.

The handoff is a finite, metadata-only request for future human research work.
It never includes page text, secret material, model instructions, executable
tools or an autonomous browsing mandate. It does not call a provider. The
Jeeves application must obtain a new authenticated source-policy snapshot
and source-body access decision before reading any referenced evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .contracts import CampaignMandate, digest, integer
from .evidence_graph import EvidenceGraph
from .policy_matrix import SourcePolicyProjection
from .review_agenda import ReviewAgenda
from .review_replay import ReviewReplay
from .retrieval_fusion import RetrievalFusion


@dataclass(frozen=True)
class HandoffCitation:
    source_id: str
    source_content_hash: str
    passage_hash: str
    canonical_url: str
    start: int
    end: int
    objective_ids: tuple[str, ...]
    current_policy_required: bool = True
    contains_external_text: bool = False


@dataclass(frozen=True)
class HandoffTask:
    task_id: str
    task_type: str
    objective_id: str | None
    source_id: str | None
    priority: float
    required_human_review: bool = True
    executable: bool = False


@dataclass(frozen=True)
class ResearchHandoff:
    schema_version: str
    mandate_digest: str
    source_snapshot_digest: str
    source_policy_digest: str
    graph_digest: str
    review_agenda_digest: str
    review_replay_digest: str | None
    retrieval_digest: str
    objective_ids: tuple[str, ...]
    citations: tuple[HandoffCitation, ...]
    tasks: tuple[HandoffTask, ...]
    serialized_json: str
    serialized_bytes: int
    handoff_digest: str
    max_citations: int
    max_tasks: int
    max_json_bytes: int
    source_text_included: bool = False
    local_model_invoked: bool = False
    remote_model_invoked: bool = False
    task_execution_authorized: bool = False
    human_approval_present: bool = False


def compile_research_handoff(
    mandate: CampaignMandate,
    policy: SourcePolicyProjection,
    graph: EvidenceGraph,
    retrieval: RetrievalFusion,
    agenda: ReviewAgenda,
    *,
    now: float,
    authorized: bool,
    replay: ReviewReplay | None = None,
    max_citations: int = 32,
    max_tasks: int = 32,
    max_json_bytes: int = 32_768,
) -> ResearchHandoff:
    mandate.admit(now=now, authorized=authorized)
    integer(max_citations, "handoff citation capacity", 1, 64)
    integer(max_tasks, "handoff task capacity", 1, 128)
    integer(max_json_bytes, "handoff serialization bound", 1024, 65_536)
    if any(x != mandate.fingerprint for x in (
        policy.mandate_digest, graph.mandate_digest,
        retrieval.mandate_digest, agenda.mandate_digest
    )):
        raise PermissionError("cross-mandate research handoff")
    if any(x != policy.source_snapshot_digest for x in (
        graph.source_snapshot_digest, retrieval.source_snapshot_digest,
        agenda.source_snapshot_digest
    )):
        raise PermissionError("research handoff mixed snapshot revisions")
    if graph.source_policy_digest != policy.policy_digest or (
        agenda.policy_digest != policy.policy_digest
        or agenda.graph_digest != graph.graph_digest
        or agenda.retrieval_digest != retrieval.fusion_digest
    ):
        raise PermissionError("research handoff invalid graph or review custody")
    if replay and (
        replay.agenda_digest != agenda.agenda_digest
        or replay.policy_digest != policy.policy_digest
        or replay.source_snapshot_digest != graph.source_snapshot_digest
    ):
        raise PermissionError("research handoff stale review replay")
    allow = set(policy.allowed_source_ids)
    citations = []
    for hit in retrieval.results[:max_citations]:
        if hit.source_id not in allow:
            raise PermissionError("held source leaked into Jeeves handoff")
        citations.append(HandoffCitation(
            source_id=hit.source_id,
            source_content_hash=hit.source_hash,
            passage_hash=hit.passage_hash,
            canonical_url=hit.canonical_url,
            start=hit.start, end=hit.end,
            objective_ids=hit.matched_objective_ids,
        ))
    task_states = {x.task_id: x for x in replay.task_states} if replay else {}
    tasks = []
    for row in agenda.tasks:
        if len(tasks) >= max_tasks:
            break
        if replay and task_states[row.task_id].operator_reviewed:
            continue
        if row.source_id and row.source_id not in allow:
            # A withheld source is represented by task metadata only, but
            # its canonical URL and text are not exposed in this envelope.
            pass
        tasks.append(HandoffTask(
            task_id=row.task_id,
            task_type=row.task_type, objective_id=row.objective_id,
            source_id=row.source_id, priority=row.priority,
        ))
    objective_ids = tuple(x.objective_id for x in graph.objectives)
    payload = {
        "schema": "skeleton.dragon.jeeves_research_handoff.v1",
        "source_snapshot_digest": graph.source_snapshot_digest,
        "mandate_digest": mandate.fingerprint,
        "source_policy_digest": policy.policy_digest,
        "evidence_graph_digest": graph.graph_digest,
        "review_agenda_digest": agenda.agenda_digest,
        "review_replay_digest": replay.replay_digest if replay else None,
        "retrieval_digest": retrieval.fusion_digest,
        "objectives": objective_ids,
        "citation_anchors": [asdict(x) for x in citations],
        "review_tasks": [asdict(x) for x in tasks],
        "trust": "external_unreviewed_reference_metadata_only",
        "refetch_authority_before_any_source_use": True,
        "execution_authorized": False,
        "publication_authorized": False,
        "training_authorized": False,
    }
    encoded = json.dumps(payload, ensure_ascii=True,
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
    byte_count = len(encoded.encode("utf-8"))
    if byte_count > max_json_bytes:
        raise ValueError("handoff exceeds bounded metadata budget")
    return ResearchHandoff(
        schema_version=payload["schema"],
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=graph.source_snapshot_digest,
        source_policy_digest=policy.policy_digest,
        graph_digest=graph.graph_digest,
        review_agenda_digest=agenda.agenda_digest,
        review_replay_digest=replay.replay_digest if replay else None,
        retrieval_digest=retrieval.fusion_digest,
        objective_ids=objective_ids, citations=tuple(citations),
        tasks=tuple(tasks), serialized_json=encoded,
        serialized_bytes=byte_count,
        handoff_digest=digest({
            "payload": payload,
            "limits": (max_citations, max_tasks, max_json_bytes),
        }),
        max_citations=max_citations, max_tasks=max_tasks,
        max_json_bytes=max_json_bytes,
    )


def verify_research_handoff(
    mandate: CampaignMandate,
    policy: SourcePolicyProjection,
    graph: EvidenceGraph,
    retrieval: RetrievalFusion,
    agenda: ReviewAgenda,
    handoff: ResearchHandoff,
    *,
    now: float,
    authorized: bool,
    replay: ReviewReplay | None = None,
) -> None:
    """Independently rebuild the bounded payload, rejecting receipt tampering.

    The digest is not a signature and cannot authenticate the policy owner.
    """
    expected = compile_research_handoff(
        mandate, policy, graph, retrieval, agenda,
        now=now, authorized=authorized, replay=replay,
        max_citations=handoff.max_citations,
        max_tasks=handoff.max_tasks,
        max_json_bytes=handoff.max_json_bytes,
    )
    if expected.serialized_json != handoff.serialized_json:
        raise ValueError("Jeeves handoff JSON revision mismatch")
    body = json.loads(handoff.serialized_json)
    if any(body.get(x) is not False for x in (
        "execution_authorized", "publication_authorized", "training_authorized"
    )):
        raise PermissionError("research handoff attempts authority escalation")
    if not body.get("refetch_authority_before_any_source_use"):
        raise PermissionError("research source-policy recheck omitted")
    if (handoff.source_text_included or handoff.local_model_invoked
        or handoff.remote_model_invoked or handoff.task_execution_authorized
        or handoff.human_approval_present):
        raise PermissionError("research handoff cannot claim execution or approval")
    if any(x != y for x, y in (
        (expected.mandate_digest, handoff.mandate_digest),
        (expected.source_snapshot_digest, handoff.source_snapshot_digest),
        (expected.source_policy_digest, handoff.source_policy_digest),
        (expected.graph_digest, handoff.graph_digest),
        (expected.review_agenda_digest, handoff.review_agenda_digest),
        (expected.review_replay_digest, handoff.review_replay_digest),
        (expected.retrieval_digest, handoff.retrieval_digest),
        (expected.objective_ids, handoff.objective_ids),
        (expected.citations, handoff.citations),
        (expected.tasks, handoff.tasks),
        (expected.serialized_bytes, handoff.serialized_bytes),
    )):
        raise PermissionError("handoff manifest revision mismatch")
    if expected.handoff_digest != handoff.handoff_digest:
        raise ValueError("research handoff checksum mismatch")
