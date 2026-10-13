"""Non-executing, deterministic milestone readiness and dependency planning.

Jeeves may inspect and plan across canonical app and AI requirements but may
not infer permission from a model output, plan, source file or passing check.
"""
from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush
from typing import Any

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_completion_census import JeevesCompletionCensus, _json_object

SCHEMA = "skeleton.ai.jeeves_milestone_dag.v1"
MAX_NODES = 4096
MAX_PAGE = 80
MAX_EXPLICIT_EVIDENCE = 400
MAX_NOTE = 250


def _task_ref(value: Any) -> str:
    if type(value) is not str or not 1 <= len(value) <= 256:
        raise JeevesAppwideError("bounded task identifier required")
    if not all(c.isalnum() or c in "-._:" for c in value):
        raise JeevesAppwideError("noncanonical task identifier")
    return value


def _topological_ids(rows: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Deterministic topological ordering with cycle rejection.

    A prerequisite must appear before the consumer, regardless of lexical
    order or arbitrary user-supplied priority. Fail closed on ghost edges.
    """
    indegree = {key: 0 for key in rows}
    downstream: dict[str, set[str]] = defaultdict(set)
    for task_id, task in rows.items():
        deps = task.get("dependencies", [])
        if type(deps) is not list or any(type(dep) is not str for dep in deps):
            raise JeevesAppwideError("typed dependency list required")
        for dependency in deps:
            dep = _task_ref(dependency)
            if dep == task_id:
                raise JeevesAppwideError("self-dependent execution milestone")
            if dep not in rows:
                raise JeevesAppwideError("unknown milestone prerequisite: " + dep)
            if task_id not in downstream[dep]:
                downstream[dep].add(task_id)
                indegree[task_id] += 1
    queue = []
    for key, degree in indegree.items():
        if degree == 0:
            heappush(queue, (rows[key]["priority_sort"], key))
    order = []
    while queue:
        _, item = heappop(queue)
        order.append(item)
        for consumer in sorted(downstream[item]):
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                heappush(queue, (rows[consumer]["priority_sort"], consumer))
    if len(order) != len(rows):
        cyclic = sorted(key for key, degree in indegree.items() if degree)
        raise JeevesAppwideError("cycle in canonical milestone prerequisites: " +
                                 ", ".join(cyclic[:8]))
    return order, sorted(key for key in rows if not rows[key]["dependencies"])


class JeevesMilestonePlanner:
    """Plan receipts are source bound; neither code nor workflows are run."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical appwide inventory required")
        inventory._require_scanned()
        self.inventory = inventory

    def _plan(self, *, expected_snapshot=None, expected_census_digest=None):
        census = JeevesCompletionCensus(self.inventory)
        report = census.report(expected_snapshot=expected_snapshot)
        if (expected_census_digest is not None and
            expected_census_digest != report["digest"]):
            raise JeevesAppwideError("stale completion census for milestone plan")
        page = census.backlog(offset=0, limit=50,
                              expected_report_digest=report["digest"])
        rows = list(page["tasks"])
        # A hard cap is maintained even if the backlog grows over time.
        while page["next_offset"] is not None:
            page = census.backlog(offset=page["next_offset"], limit=50,
                                  expected_report_digest=report["digest"])
            rows.extend(page["tasks"])
            if len(rows) > MAX_NODES:
                raise JeevesAppwideError("milestone plan budget exceeded")
        plans = {}
        for row in rows:
            identity = _task_ref(row["id"])
            if identity in plans:
                raise JeevesAppwideError("duplicate milestone identity")
            required = row["evidence_required"]
            if type(required) is not list or not required:
                raise JeevesAppwideError("milestone lacks independent proof")
            plans[identity] = {**row, "priority_sort": {
                "P0": 0, "P1": 1, "P2": 2}.get(row["priority"], 3)}
        raw = self.inventory._safe_file("skeleton/app/manifest.json",
                                        max_size=200_000)
        manifest = _json_object(raw, "skeleton/app/manifest.json")
        services = manifest.get("services", [])
        if type(services) is not list:
            raise JeevesAppwideError("invalid service dependency authority")
        for service in services:
            if type(service) is not dict or type(service.get("name")) is not str:
                raise JeevesAppwideError("invalid service dependency row")
            identity = "APP-SERVICE-" + service["name"]
            if identity not in plans:
                raise JeevesAppwideError("service missing from canonical backlog")
            deps = service.get("depends_on", [])
            if type(deps) is not list:
                raise JeevesAppwideError("invalid manifest service prerequisites")
            for dep in deps:
                if type(dep) is not str:
                    raise JeevesAppwideError("invalid service prerequisite")
                plans[identity]["dependencies"].append("APP-SERVICE-" + dep)

        order, roots = _topological_ids(plans)
        reverse = defaultdict(list)
        for task in plans.values():
            task["dependencies"] = sorted(set(task["dependencies"]))
            task["evidence_required"] = [
                str(note)[:MAX_NOTE] for note in task["evidence_required"][:MAX_EXPLICIT_EVIDENCE]
            ]
            for dependency in task["dependencies"]:
                reverse[dependency].append(task["id"])
        stages = {}
        for identity in order:
            deps = plans[identity]["dependencies"]
            stages[identity] = 0 if not deps else 1 + max(stages[d] for d in deps)
        for identity in order:
            plans[identity]["stage"] = stages[identity]
            plans[identity]["blocked_by"] = plans[identity]["dependencies"]
            plans[identity]["dependent_count"] = len(reverse[identity])
            plans[identity]["declared_dependencies_are_not_proofs"] = True

        # A topological ordering does not mean a single task may be executed:
        # no CI proof, review receipt or real operator authorization is
        # loaded by this source-only planner.
        plan = {
            "schema": SCHEMA,
            "census_digest": report["digest"],
            "inventory_snapshot": report["inventory_snapshot"],
            "source_receipts": report["source_receipts"],
            "total_tasks": len(order),
            "stage_count": max(stages.values(), default=-1) + 1,
            "root_count": len(roots),
            "explicit_dependencies": sum(len(t["dependencies"]) for t in plans.values()),
            "order": order,
            "tasks": [plans[key] for key in order],
            "all_tasks_require_independent_evidence": True,
            "ready_for_automatic_execution": False,
            "completion_claims_created": 0,
            "source_mutations_performed": False,
        }
        return {**plan, "digest": digest(plan)}

    def overview(self, *, expected_snapshot=None, expected_census_digest=None):
        result = self._plan(expected_snapshot=expected_snapshot,
                            expected_census_digest=expected_census_digest)
        # Prevent duplicating all verbose acceptance criteria into a
        # supposedly short progress report; the page API supplies those.
        return {key: value for key, value in result.items()
                if key not in ("tasks", "order", "source_receipts")}

    def page(self, *, offset=0, limit=20, expected_plan_digest=None,
             expected_snapshot=None, expected_census_digest=None):
        if type(offset) is not int or not 0 <= offset <= MAX_NODES:
            raise JeevesAppwideError("bounded non-negative plan page offset needed")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded positive milestone page size needed")
        plan = self._plan(expected_snapshot=expected_snapshot,
                          expected_census_digest=expected_census_digest)
        if expected_plan_digest is not None and expected_plan_digest != plan["digest"]:
            raise JeevesAppwideError("stale plan digest")
        rows = plan["tasks"][offset:offset+limit]
        body = {
            "schema": SCHEMA + ".page",
            "plan_digest": plan["digest"],
            "census_digest": plan["census_digest"],
            "offset": offset,
            "limit": limit,
            "next_offset": offset+len(rows)
                if offset+len(rows) < len(plan["tasks"]) else None,
            "total_tasks": len(plan["tasks"]),
            "tasks": rows,
            "approval_cannot_be_granted_by_plan": True,
            "work_not_executed": True,
        }
        return {**body, "digest": digest(body)}
