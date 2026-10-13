"""Structural critical-path and owner capacity analysis for Jeeves milestones.

Dependency distance is a *graph property*, not an estimate of build hours,
implementation readiness, successful tests or release. This read-only planner
uses the existing canonical milestone DAG, not a new backlog authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_milestone_planner import JeevesMilestonePlanner, MAX_NODES, _task_ref

SCHEMA = "skeleton.ai.jeeves_critical_path.v1"


def _limit(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise JeevesAppwideError("bounded " + name + " expected")
    return value


class JeevesCriticalPath:
    """Deterministic critical-chain analysis of declared work dependencies."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("reviewed inventory required")
        inventory._require_scanned()
        self.inv = inventory

    def _analyze(self, *, expected_snapshot=None, expected_plan_digest=None):
        plan = JeevesMilestonePlanner(self.inv)._plan(
            expected_snapshot=expected_snapshot)
        if expected_plan_digest is not None and expected_plan_digest != plan["digest"]:
            raise JeevesAppwideError("stale milestone DAG identity")
        tasks = {row["id"]: row for row in plan["tasks"]}
        successors: dict[str, set[str]] = defaultdict(set)
        for row in tasks.values():
            for dependency in row["dependencies"]:
                if dependency not in tasks:
                    raise JeevesAppwideError("unresolved canonical dependency")
                successors[dependency].add(row["id"])
        # Existing planner ordering is topological. Descendant height is
        # computed backward and is not a speculative duration estimate.
        height = {}
        reach = {}
        for identity in reversed(plan["order"]):
            downstream = successors[identity]
            height[identity] = 0 if not downstream else 1 + max(
                height[child] for child in downstream)
            reach[identity] = set(downstream)
            for child in downstream:
                reach[identity].update(reach[child])
            if len(reach[identity]) > MAX_NODES:
                raise JeevesAppwideError("descendant closure exceeds work cap")
        deepest = max(plan["order"], key=lambda i: (
            tasks[i]["stage"], -tasks[i]["priority_sort"], i
        )) if plan["order"] else None
        critical_chain = []
        while deepest is not None:
            critical_chain.append(deepest)
            predecessors = tasks[deepest]["dependencies"]
            deepest = max(predecessors, key=lambda i: (
                tasks[i]["stage"], i
            )) if predecessors else None
        critical_chain.reverse()
        counts = Counter(row["owner"] for row in tasks.values())
        priorities = Counter(row["priority"] for row in tasks.values())
        return plan, tasks, successors, height, reach, critical_chain, counts, priorities

    def overview(self, *, limit=30, expected_snapshot=None,
                 expected_plan_digest=None):
        _limit(limit, "bottleneck limit", 1, 100)
        (plan, tasks, successors, height, reach, chain,
         counts, priorities) = self._analyze(
             expected_snapshot=expected_snapshot,
             expected_plan_digest=expected_plan_digest)
        ranking = sorted(
            tasks, key=lambda identity: (
                -len(reach[identity]),
                -height[identity],
                -len(successors[identity]),
                tasks[identity]["priority_sort"], identity
            )
        )
        projected = [{
            "task_id": identity,
            "owner": tasks[identity]["owner"],
            "priority": tasks[identity]["priority"],
            "stage": tasks[identity]["stage"],
            "direct_dependents": len(successors[identity]),
            "transitive_dependents": len(reach[identity]),
            "longest_downstream_dependency_steps": height[identity],
            "direct_prerequisites": tasks[identity]["dependencies"],
            "in_a_longest_structural_chain": identity in chain,
            "task_execution_verified": False,
        } for identity in ranking[:limit]]
        body = {
            "schema": SCHEMA + ".overview",
            "inventory_snapshot": plan["inventory_snapshot"],
            "plan_digest": plan["digest"],
            "total_tasks": len(tasks),
            "stage_count": plan["stage_count"],
            "longest_structural_chain_steps": max(
                0, len(chain) - 1
            ),
            "one_longest_chain": chain,
            "priority_counts": dict(sorted(priorities.items())),
            "owner_count": len(counts),
            "bottlenecks": projected,
            "ranking_truncated": len(ranking) > limit,
            "no_wall_clock_or_effort_estimates_fabricated": True,
            "all_task_states_still_require_execution_evidence": True,
            "source_mutated": False,
        }
        return {**body, "digest": digest(body)}

    def ownerload(self, *, offset=0, limit=30, expected_snapshot=None,
                  expected_plan_digest=None):
        _limit(offset, "owner offset", 0, MAX_NODES)
        _limit(limit, "owner page size", 1, 100)
        (plan, tasks, successors, height, reach, chain,
         counts, priorities) = self._analyze(
             expected_snapshot=expected_snapshot,
             expected_plan_digest=expected_plan_digest)
        grouped = defaultdict(list)
        for row in tasks.values():
            grouped[row["owner"]].append(row)
        ordered = sorted(grouped, key=lambda owner: (
            -len(grouped[owner]), owner
        ))
        pages = []
        for owner in ordered[offset:offset + limit]:
            rows = grouped[owner]
            pages.append({
                "owner": owner,
                "task_count": len(rows),
                "priority_counts": dict(sorted(
                    Counter(row["priority"] for row in rows).items()
                )),
                "direct_dependency_count": sum(
                    len(row["dependencies"]) for row in rows
                ),
                "highest_structural_stage": max(row["stage"] for row in rows),
                "task_ids": sorted(row["id"] for row in rows)[:80],
                "task_ids_truncated": len(rows) > 80,
                "owner_currently_executing_any_task": None,
                "owner_capacity_unknown": True,
            })
        body = {
            "schema": SCHEMA + ".owners",
            "inventory_snapshot": plan["inventory_snapshot"],
            "plan_digest": plan["digest"],
            "total_owners": len(ordered),
            "total_tasks": len(tasks),
            "offset": offset,
            "limit": limit,
            "next_offset": offset + len(pages)
                if offset + len(pages) < len(ordered) else None,
            "owners": pages,
            "resource_budget_or_worker_availability_not_inferred": True,
            "source_mutated": False,
        }
        return {**body, "digest": digest(body)}
