"""Plan finite, resource-aware producer batches without a file-count ceiling."""
from __future__ import annotations
from typing import Any, Mapping, Sequence

from .studio_ecosystem_capacity import ProducerCapacity,plan_producer_admission
from .studio_ecosystem_work import ready_work
from .studio_ecosystem_quest import StudioQuestError


def plan_work_batch(graph: Mapping[str, Any], completed: Sequence[str],
                    capacity: ProducerCapacity, *, working_set_bytes: int,
                    output_bytes: int, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("studio batch dispatch requires operator authorization")
    eligibility=ready_work(graph,completed,authorized=True)
    capacity_plan=plan_producer_admission(capacity,
                                          working_set_bytes=working_set_bytes,
                                          output_bytes=output_bytes)
    slots=capacity_plan["admitted_worker_slots"]
    ready=eligibility["ready_for_operator_review"]
    return {"schema":"skeleton.game_builder.studio_producer_batch.v1",
            "project_id":graph.get("project_id"),
            "work_graph_sha256":graph.get("work_graph_sha256"),
            "admitted":[{"task_id":task,"slot":i} for i,task in
                        enumerate(ready[:slots])],
            "deferred":ready[slots:],
            "requested_ready":len(ready),
            "resource_capacity":capacity_plan,
            "work_executed":False,
            "completion_proof_verified":False,"release_certified":False}
