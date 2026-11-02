"""Typed Jeeves production DAG from actual canonical source and engine evidence."""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import os
from typing import Any

from .asset_briefs import validate_briefs
from .bundle import PlayableBundleStore
from .timeline import validate_timeline
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical, digest,
    prove, strict_json,
)

SCHEMA = "jeeves.world.production_plan.v1"
MAX_TASKS = 512
KINDS = frozenset({
    "scene_canon", "choice_consequence", "ending_witness",
    "asset_rights", "temporal_event", "playable_handoff",
})
STATUSES = frozenset({"proposed", "approved", "blocked"})


def _sources(fd: int, store: WorldStore, world_id: str):
    _id(world_id, "world_id")
    world = strict_json(store._read(fd, world_id + ".json"))
    assets = strict_json(store._read(fd, world_id + ".assets.json"))
    timeline = strict_json(store._read(fd, world_id + ".timeline.json"))
    prove(world)
    validate_briefs(assets, world)
    validate_timeline(timeline, world)
    if world["id"] != world_id:
        raise CanonError("identity_mismatch")
    return world, assets, timeline


def _tid(prefix: str, source_id: str) -> str:
    """Stable bounded task identifier, even for maximal valid source IDs."""
    raw = prefix + source_id
    if len(raw) <= 48:
        return raw
    return prefix + source_id[:16] + "_" + sha256(source_id.encode()).hexdigest()[:12]


def _task(task_id: str, kind: str, source_id: str, dependencies: list[str],
          description: str) -> dict[str, Any]:
    return {"id": task_id, "kind": kind, "source_id": source_id,
            "depends_on": sorted(dependencies), "description": description,
            "status": "proposed", "review_note": ""}


def propose_plan(world: Any, assets: Any, timeline: Any) -> dict[str, Any]:
    """Generate a source-specific review DAG; no fabricated AI actions."""
    proof = prove(world)
    validate_briefs(assets, world)
    validate_timeline(timeline, world)
    tasks = propose_plan_unreviewed(world, assets, timeline)
    if len(tasks) > MAX_TASKS:
        raise CanonError("plan_task_budget_exhausted")
    result = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest,
        "asset_digest": digest(assets), "timeline_digest": digest(timeline),
        "tasks": tasks,
    }
    validate_plan(result, world, assets, timeline)
    return result

def validate_plan(plan: Any, world: Any, assets: Any, timeline: Any) -> dict[str, Any]:
    _keys(plan, {"schema", "world_id", "world_digest", "asset_digest",
                 "timeline_digest", "tasks"})
    if plan["schema"] != SCHEMA:
        raise CanonError("plan_schema_mismatch")
    if (plan["world_id"] != world["id"] or
        plan["world_digest"] != prove(world).source_digest or
        plan["asset_digest"] != digest(validate_briefs(assets, world)) or
        plan["timeline_digest"] != digest(validate_timeline(timeline, world))):
        raise CanonError("plan_source_lease_mismatch")
    tasks = _list(plan["tasks"], "tasks", MAX_TASKS)
    if not tasks:
        raise CanonError("empty_plan")
    by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        _keys(task, {"id", "kind", "source_id", "depends_on",
                     "description", "status", "review_note"})
        tid = _id(task["id"], "task.id")
        if tid in by_id:
            raise CanonError("duplicate_task", tid)
        by_id[tid] = task
        if task["kind"] not in KINDS:
            raise CanonError("invalid_task_kind", tid)
        _id(task["source_id"], "task.source_id")
        _text(task["description"], "task.description", 512)
        if task["status"] not in STATUSES:
            raise CanonError("invalid_task_status", tid)
        if type(task["review_note"]) is not str or len(task["review_note"]) > 512:
            raise CanonError("invalid_review_note", tid)
        deps = [_id(d, "task.depends_on") for d in
                _list(task["depends_on"], "task.depends_on", MAX_TASKS)]
        if deps != sorted(set(deps)):
            raise CanonError("noncanonical_task_dependencies", tid)
    if set(by_id) != {t["id"] for t in propose_plan_unreviewed(world, assets, timeline)}:
        raise CanonError("plan_task_inventory_mismatch")
    expected = {t["id"]: t for t in propose_plan_unreviewed(world, assets, timeline)}
    for tid, task in by_id.items():
        if any(task[field] != expected[tid][field] for field in
               ("kind", "source_id", "depends_on", "description")):
            raise CanonError("plan_task_tampered", tid)
        if task["status"] != "proposed" and not task["review_note"]:
            raise CanonError("review_note_required", tid)
        for dep in task["depends_on"]:
            if dep not in by_id:
                raise CanonError("unknown_task_dependency", dep)
            if task["status"] == "approved" and by_id[dep]["status"] != "approved":
                raise CanonError("unapproved_dependency", tid)
    # Source-specific DAG must be complete and acyclic.
    ordered = topological_tasks(tasks)
    if len(ordered) != len(tasks):
        raise CanonError("plan_cycle")
    if len(canonical(plan)) > 524288:
        raise CanonError("source_too_large")
    return plan


def propose_plan_unreviewed(world: Any, assets: Any, timeline: Any) -> list[dict[str, Any]]:
    """Deterministic inventory helper that never recursively calls validation."""
    tasks: list[dict[str, Any]] = []
    scene_tasks = {s["id"]: _tid("scene_", s["id"]) for s in world["scenes"]}
    for scene in sorted(world["scenes"], key=lambda x: x["id"]):
        tasks.append(_task(scene_tasks[scene["id"]], "scene_canon", scene["id"], [],
                           "Review authored scene continuity: " + scene["title"]))
    for choice in sorted(world["choices"], key=lambda x: x["id"]):
        tasks.append(_task(_tid("choice_", choice["id"]), "choice_consequence",
                           choice["id"], [scene_tasks[choice["from"]],
                                          scene_tasks[choice["to"]]],
                           "Verify earned choice consequences: " + choice["label"]))
    for ending in sorted(world["endings"], key=lambda x: x["scene"]):
        incoming = [_tid("choice_", e["id"]) for e in world["choices"]
                    if e["to"] == ending["scene"]]
        tasks.append(_task(_tid("ending_", ending["scene"]), "ending_witness",
                           ending["scene"], [scene_tasks[ending["scene"]], *incoming],
                           "Verify reachable ending: " + ending["label"]))
    for asset in sorted(assets["assets"], key=lambda x: x["id"]):
        tasks.append(_task(_tid("asset_", asset["id"]), "asset_rights",
                           asset["id"], [scene_tasks[asset["scene"]]],
                           "Review original asset descriptor: " + asset["description"][:200]))
    for event in sorted(timeline["events"], key=lambda x: x["id"]):
        tasks.append(_task(_tid("event_", event["id"]), "temporal_event",
                           event["id"], [scene_tasks[event["scene"]]] +
                           [_tid("event_", d) for d in event["depends_on"]],
                           "Review temporal event: " + event["description"][:200]))
    tasks.append(_task("playable_compile", "playable_handoff", world["id"],
                       [t["id"] for t in tasks],
                       "Verify browser play, era asset compilation and timeline handoff"))
    return tasks


def topological_tasks(tasks: list[dict[str, Any]]) -> list[str]:
    by_id = {t["id"]: t for t in tasks}
    pending = {tid: set(t["depends_on"]) for tid, t in by_id.items()}
    ready = sorted(tid for tid, deps in pending.items() if not deps)
    ordered: list[str] = []
    while ready:
        tid = ready.pop(0)
        ordered.append(tid)
        for other in sorted(pending):
            if tid in pending[other]:
                pending[other].remove(tid)
                if not pending[other] and other not in ordered and other not in ready:
                    ready.append(other)
        ready.sort()
    if len(ordered) != len(tasks):
        raise CanonError("plan_cycle")
    return ordered


def review_task(plan: Any, world: Any, assets: Any, timeline: Any, *,
                task_id: str, decision: str, note: str) -> dict[str, Any]:
    validate_plan(plan, world, assets, timeline)
    _id(task_id, "task_id")
    if decision not in {"approved", "blocked"}:
        raise CanonError("invalid_review_decision")
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(plan))
    found = [t for t in candidate["tasks"] if t["id"] == task_id]
    if len(found) != 1:
        raise CanonError("unknown_task")
    found[0]["status"] = decision
    found[0]["review_note"] = note
    validate_plan(candidate, world, assets, timeline)
    return candidate


def compile_plan(plan: Any, world: Any, assets: Any, timeline: Any,
                 bundle_receipt: Any) -> dict[str, Any]:
    validate_plan(plan, world, assets, timeline)
    if any(t["status"] != "approved" for t in plan["tasks"]):
        raise CanonError("plan_not_approved")
    if (bundle_receipt["world_digest"] != digest(world) or
        bundle_receipt["asset_briefs_digest"] != digest(assets) or
        bundle_receipt["timeline_digest"] != digest(timeline)):
        raise CanonError("bundle_plan_source_mismatch")
    return {
        "schema": "jeeves.world.production_handoff.v1",
        "world_id": world["id"], "plan_digest": digest(plan),
        "bundle_receipt": bundle_receipt,
        "ordered_tasks": topological_tasks(plan["tasks"]),
        "review_provenance": "operator_approved_not_independent_qualification",
    }


class PlanStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".plan.json"

    def read(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, assets, timeline = _sources(fd, self.worlds, world_id)
            data = strict_json(self.worlds._read(fd, self._name(world_id)))
            return validate_plan(data, world, assets, timeline)
        finally:
            os.close(fd)

    def publish(self, world_id: str, plan: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        lock = world_id + ".lock"
        try:
            try:
                lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(lock_fd)
                world, assets, timeline = _sources(fd, self.worlds, world_id)
                validate_plan(plan, world, assets, timeline)
                try:
                    old = digest(validate_plan(
                        strict_json(self.worlds._read(fd, self._name(world_id))),
                        world, assets, timeline))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_plan")
                self.worlds._write(fd, self._name(world_id), canonical(plan))
                return digest(plan)
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, str]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        lock = world_id + ".lock"
        try:
            try:
                lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW, 0o600, dir_fd=fd)
            except FileExistsError:
                raise CanonError("lease_busy") from None
            try:
                os.close(lock_fd)
                world, assets, timeline = _sources(fd, self.worlds, world_id)
                plan = strict_json(self.worlds._read(fd, self._name(world_id)))
                validate_plan(plan, world, assets, timeline)
                if digest(plan) != expected_digest:
                    raise CanonError("stale_plan")
                if any(t["status"] != "approved" for t in plan["tasks"]):
                    raise CanonError("plan_not_approved")
                # The full bundle must independently reverify against current
                # sources; a forged or partial receipt cannot qualify a plan.
                receipt = PlayableBundleStore(self.worlds.root).verify(world_id)
                handoff = compile_plan(plan, world, assets, timeline, receipt)
                payload = canonical(handoff)
                self.worlds._write(fd, world_id + ".plan.compiled.json", payload)
                return {"world_id": world_id, "plan_digest": digest(plan),
                        "handoff_sha256": sha256(payload).hexdigest(),
                        "compiled_file": world_id + ".plan.compiled.json"}
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)
