"""Source-bound authored quest objectives with replayed player consequences.

Quest completion is never granted by arbitrary input. It is derived from
actual canonical world choice traces and ordered objective prerequisites.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .session import replay_choices
from .timeline import _reachable_flags
from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, _keys, _list, _text,
    canonical, compile_html, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.quest.v1"
HANDOFF_SCHEMA = "jeeves.world.quest_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.quest_receipt.v1"
MAX_OBJECTIVES = 64
MAX_SEARCH_STEPS = 256


def _ids(value: Any, field: str) -> list[str]:
    result = [_id(item, field) for item in _list(value, field, MAX_OBJECTIVES)]
    if result != sorted(set(result)):
        raise CanonError("noncanonical_quest_ids", field)
    return result


def validate_quest(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "ending", "objectives",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("quest_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("quest_world_lease_mismatch")
    if type(obj["ending"]) is not str or obj["ending"] not in {
        e["scene"] for e in world["endings"]
    }:
        raise CanonError("unknown_quest_ending")
    if type(obj["approved"]) is not bool:
        raise CanonError("invalid_quest_approval")
    _text(obj["review_note"], "review_note", 512)
    objectives = _list(obj["objectives"], "objectives", MAX_OBJECTIVES)
    if not objectives:
        raise CanonError("empty_quest")
    reachable = _reachable_flags(world)
    by_id: dict[str, dict[str, Any]] = {}
    for objective in objectives:
        _keys(objective, {"id", "title", "description", "scene",
                          "requires_flags", "depends_on", "required"})
        oid = _id(objective["id"], "objective.id")
        if oid in by_id:
            raise CanonError("duplicate_objective", oid)
        by_id[oid] = objective
        _text(objective["title"], "objective.title", 200)
        _text(objective["description"], "objective.description", 2048)
        scene = _id(objective["scene"], "objective.scene")
        if scene not in reachable:
            raise CanonError("unknown_objective_scene", oid)
        flags = _ids(objective["requires_flags"], "requires_flags")
        _ids(objective["depends_on"], "depends_on")
        if not any(set(flags) <= state for state in reachable[scene]):
            raise CanonError("unreachable_objective_flags", oid)
        if type(objective["required"]) is not bool:
            raise CanonError("invalid_objective_required", oid)
    pending: dict[str, set[str]] = {}
    for oid, objective in by_id.items():
        dependencies = set(objective["depends_on"])
        if oid in dependencies or not dependencies <= by_id.keys():
            raise CanonError("invalid_objective_dependency", oid)
        pending[oid] = dependencies
    done: set[str] = set()
    while pending:
        ready = sorted(oid for oid, deps in pending.items() if deps <= done)
        if not ready:
            raise CanonError("quest_dependency_cycle")
        done.update(ready)
        for oid in ready:
            del pending[oid]
    if len(canonical(obj)) > 524288:
        raise CanonError("quest_too_large")
    return obj


def propose_quest(world: Any, *, ending: str, title: str,
                  description: str) -> dict[str, Any]:
    proof = prove(world)
    _text(title, "title", 200)
    _text(description, "description", 2048)
    obj = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest, "ending": ending,
        "objectives": [{
            "id": "primary", "title": title, "description": description,
            "scene": ending, "requires_flags": [], "depends_on": [],
            "required": True,
        }],
        "approved": False, "review_note": "Awaiting original-author quest review",
    }
    return validate_quest(obj, world)


def edit_quest(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_quest(data, world)
    top = _keys(operation, {"action", "value"})
    operations = (_list(top["value"], "batch", 64)
                  if top["action"] == "batch" else [top])
    if not operations:
        raise CanonError("empty_quest_batch")
    candidate = strict_json(canonical(data))
    for entry in operations:
        item = _keys(entry, {"action", "value"})
        action, value = item["action"], item["value"]
        if action in {"add", "replace"}:
            _keys(value, {"id", "title", "description", "scene",
                          "requires_flags", "depends_on", "required"})
            if action == "add":
                candidate["objectives"].append(value)
            else:
                indices = [i for i, objective in enumerate(candidate["objectives"])
                           if objective["id"] == value["id"]]
                if len(indices) != 1:
                    raise CanonError("unknown_objective")
                candidate["objectives"][indices[0]] = value
        elif action == "remove":
            _keys(value, {"id"})
            before = len(candidate["objectives"])
            candidate["objectives"] = [
                objective for objective in candidate["objectives"]
                if objective["id"] != value["id"]
            ]
            if len(candidate["objectives"]) != before - 1:
                raise CanonError("unknown_objective")
        else:
            raise CanonError("unsupported_quest_edit", str(action))
    candidate["approved"] = False
    candidate["review_note"] = "Quest source changed; renewed review required"
    return validate_quest(candidate, world)


def _earn(objectives: list[dict[str, Any]], scene: str,
          flags: frozenset[str], completed: frozenset[str]) -> frozenset[str]:
    earned = set(completed)
    while True:
        newly = [
            item["id"] for item in objectives
            if item["id"] not in earned and item["scene"] == scene
            and set(item["requires_flags"]) <= flags
            and set(item["depends_on"]) <= earned
        ]
        if not newly:
            return frozenset(earned)
        earned.update(newly)


def evaluate_quest(data: Any, world: Any, choices: Any) -> dict[str, Any]:
    validate_quest(data, world)
    replay = replay_choices(world, choices)
    completed: frozenset[str] = frozenset()
    earned_at: list[dict[str, Any]] = []
    for index, step in enumerate(replay["steps"]):
        updated = _earn(data["objectives"], step["scene"],
                        frozenset(step["flags"]), completed)
        for oid in sorted(updated - completed):
            earned_at.append({"objective": oid, "scene": step["scene"],
                              "step": index})
        completed = updated
    required = {item["id"] for item in data["objectives"] if item["required"]}
    return {
        "world_digest": digest(world), "quest_digest": digest(data),
        "scene": replay["scene"], "ending": replay["ending"],
        "completed": sorted(completed),
        "remaining_required": sorted(required - completed),
        "earned_at": earned_at,
        "quest_won": (replay["scene"] == data["ending"] and
                      not required - completed),
    }


def solve_quest(data: Any, world: Any) -> tuple[str, ...]:
    validate_quest(data, world)
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for options in edges.values():
        options.sort(key=lambda item: item["id"])
    ending_ids = {e["scene"] for e in world["endings"]}
    required = {item["id"] for item in data["objectives"] if item["required"]}
    initial_done = _earn(data["objectives"], world["start"],
                         frozenset(), frozenset())
    initial = (world["start"], frozenset(), initial_done)
    queue = deque([(initial, ())])
    visited = {initial}
    truncated = False
    while queue:
        (scene, flags, completed), trace = queue.popleft()
        if scene == data["ending"] and required <= completed:
            return trace
        if scene in ending_ids:
            continue
        enabled = [edge for edge in edges.get(scene, [])
                   if set(edge["requires"]) <= flags]
        if len(trace) >= MAX_SEARCH_STEPS:
            truncated |= bool(enabled)
            continue
        for edge in enabled:
            next_flags = flags | frozenset(edge["grants"])
            next_done = _earn(data["objectives"], edge["to"],
                              next_flags, completed)
            next_state = (edge["to"], next_flags, next_done)
            if next_state in visited:
                continue
            if len(visited) >= MAX_STATES:
                raise CanonError("quest_search_inconclusive")
            visited.add(next_state)
            queue.append((next_state, trace + (edge["id"],)))
    if truncated:
        raise CanonError("quest_search_inconclusive")
    raise CanonError("quest_unreachable")


def approve_quest(data: Any, world: Any, note: str) -> dict[str, Any]:
    validate_quest(data, world)
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(data))
    candidate["approved"] = True
    candidate["review_note"] = note
    solve_quest(candidate, world)
    return candidate


def compile_quest(data: Any, world: Any) -> dict[str, Any]:
    validate_quest(data, world)
    if not data["approved"]:
        raise CanonError("quest_review_required")
    trace = solve_quest(data, world)
    progress = evaluate_quest(data, world, list(trace))
    if not progress["quest_won"]:
        raise CanonError("quest_witness_invalid")
    return {
        "schema": HANDOFF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "quest_digest": digest(data),
        "approved": True, "review_note": data["review_note"],
        "choice_witness": list(trace), "progress": progress,
        "objectives": data["objectives"],
        "qualification": "operator_review_only_not_release_certified",
    }


class QuestStore:
    """Durable authored quest, with exact-source compiled player and receipt."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".quest.json"

    @staticmethod
    def _artifacts(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".quest.playable.html",
                world_id + ".quest.handoff.json",
                world_id + ".quest.receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _quest(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_quest(
            strict_json(self.worlds._read(fd, self._name(world_id))), world)

    def _lock(self, fd: int, world_id: str) -> int:
        _id(world_id, "world_id")
        try:
            return os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                           os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def read(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            return self._quest(fd, world_id, world)
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                validate_quest(data, world)
                if data["world_id"] != world_id:
                    raise CanonError("identity_mismatch")
                try:
                    old = digest(self._quest(fd, world_id, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_quest")
                self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, data: Any):
        handoff = compile_quest(data, world)
        contents = [compile_html(world).encode("utf-8"), canonical(handoff)]
        names = self._artifacts(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "quest_digest": digest(data),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], contents)
            },
            "qualification": "source_proven_not_device_or_release_certified",
        }
        return receipt, contents

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._quest(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_quest")
                receipt, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                for name, content in zip(names[:2], contents):
                    self.worlds._write(fd, name, content)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._quest(fd, world_id, world)
                expected, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                receipt = strict_json(self.worlds._read(fd, names[2]))
                if receipt != expected:
                    raise CanonError("quest_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if _artifact_read(fd, name) != content:
                        raise CanonError("quest_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
