"""CAS-based in-memory ownership for one supervised producer-work graph.

Leases are local coordination proposals, not distributed, durable, or real
job-completion proof. Source identity is immutable for the lease lifetime.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_work import ready_work
from .studio_ecosystem_quest import StudioQuestError


@dataclass(frozen=True, slots=True)
class ProducerLease:
    project_id: str
    graph_digest: str
    revision: int
    assigned: tuple[tuple[str,str], ...]
    evidence_digest: str


def _digest(project: str, graph: str, revision: int,
            assigned: tuple[tuple[str,str], ...]) -> str:
    payload={"project":project,"graph":graph,"revision":revision,"assigned":assigned}
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             ensure_ascii=True).encode("ascii")).hexdigest()


def open_leases(graph: Mapping[str, Any], *, authorized: bool) -> ProducerLease:
    if not authorized:
        raise PermissionError("work lease requires operator authorization")
    ready_work(graph,[],authorized=True)
    project=graph["project_id"]
    digest=graph["work_graph_sha256"]
    if not isinstance(project,str) or not isinstance(digest,str):
        raise StudioQuestError("invalid producer graph identity")
    return ProducerLease(project,digest,0,(),_digest(project,digest,0,()))


def assign_lease(lease: ProducerLease, graph: Mapping[str, Any], *,
                 task_id: str, worker_id: str, expected_revision: int,
                 authorized: bool) -> ProducerLease:
    if not authorized:
        raise PermissionError("lease changes require operator authorization")
    if (not isinstance(lease,ProducerLease) or
            lease.project_id!=graph.get("project_id") or
            lease.graph_digest!=graph.get("work_graph_sha256") or
            lease.evidence_digest!=_digest(lease.project_id,lease.graph_digest,
                                           lease.revision,lease.assigned) or
            type(expected_revision) is not int or lease.revision!=expected_revision):
        raise StudioQuestError("stale or tampered producer lease")
    if not isinstance(worker_id,str) or not worker_id or len(worker_id)>128:
        raise StudioQuestError("invalid worker identity")
    if task_id not in ready_work(graph,[],authorized=True)["ready_for_operator_review"]:
        raise StudioQuestError("task is not ready for first-stage assignment")
    if any(item[0]==task_id for item in lease.assigned):
        raise StudioQuestError("duplicate task lease")
    updated=lease.assigned+((task_id,worker_id),)
    return ProducerLease(lease.project_id,lease.graph_digest,lease.revision+1,
                         updated,_digest(lease.project_id,lease.graph_digest,
                                         lease.revision+1,updated))
