"""Original clue discovery from legal player decisions, with reviewed canon proof.

An evidence item is not obtained by a model assertion or client-provided flag.
A source-bound player trace must contain its unlocking choice; dependencies
must be earned, and an explicit author approval gates compilation.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import os
from typing import Any

from .session import replay_choices, validate_session
from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.evidence.v1"
HANDOFF_SCHEMA = "jeeves.world.evidence_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.evidence_receipt.v1"
MAX_CLUES = 64
MAX_STEPS = 256


def validate_evidence(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "prompt", "clues",
        "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("evidence_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("evidence_world_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    if type(obj["approved"]) is not bool:
        raise CanonError("invalid_evidence_approval")
    if type(obj["review_note"]) is not str or len(obj["review_note"]) > 512:
        raise CanonError("invalid_evidence_review_note")
    if obj["approved"]:
        _text(obj["review_note"], "review_note", 512)
    clues = _list(obj["clues"], "clues", MAX_CLUES)
    if not clues:
        raise CanonError("empty_evidence")
    choice_ids = {c["id"] for c in world["choices"]}
    by_id: dict[str, dict[str, Any]] = {}
    for clue in clues:
        _keys(clue, {"id", "title", "detail", "unlock_choice",
                     "depends_on", "required"})
        cid = _id(clue["id"], "clue.id")
        if cid in by_id:
            raise CanonError("duplicate_evidence", cid)
        by_id[cid] = clue
        _text(clue["title"], "clue.title", 200)
        _text(clue["detail"], "clue.detail", 2048)
        if _id(clue["unlock_choice"], "clue.unlock_choice") not in choice_ids:
            raise CanonError("unknown_evidence_choice", cid)
        deps = [_id(v, "clue.depends_on") for v in
                _list(clue["depends_on"], "clue.depends_on", MAX_CLUES)]
        if deps != sorted(set(deps)):
            raise CanonError("noncanonical_evidence_dependencies", cid)
        if type(clue["required"]) is not bool:
            raise CanonError("invalid_evidence_required", cid)
    if list(by_id) != sorted(by_id):
        raise CanonError("noncanonical_evidence_ids")
    pending = {cid: set(clue["depends_on"]) for cid, clue in by_id.items()}
    for cid, deps in pending.items():
        if cid in deps or not deps <= by_id.keys():
            raise CanonError("invalid_evidence_dependency", cid)
    resolved: set[str] = set()
    while pending:
        ready = [cid for cid in sorted(pending) if pending[cid] <= resolved]
        if not ready:
            raise CanonError("evidence_dependency_cycle")
        resolved.update(ready)
        for cid in ready:
            del pending[cid]
    if len(canonical(obj)) > 524288:
        raise CanonError("evidence_too_large")
    return obj


def propose_evidence(world: Any, *, prompt: str, clue_id: str, title: str,
                     detail: str, unlock_choice: str) -> dict[str, Any]:
    data = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": prove(world).source_digest, "prompt": prompt,
        "clues": [{"id": clue_id, "title": title, "detail": detail,
                   "unlock_choice": unlock_choice, "depends_on": [],
                   "required": True}],
        "approved": False, "review_note": "",
    }
    return validate_evidence(data, world)


def edit_evidence(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_evidence(data, world)
    top = _keys(operation, {"action", "value"})
    actions = (_list(top["value"], "batch", 64)
               if top["action"] == "batch" else [top])
    if not actions:
        raise CanonError("empty_evidence_edit")
    candidate = strict_json(canonical(data))
    for entry in actions:
        item = _keys(entry, {"action", "value"})
        action, value = item["action"], item["value"]
        if action in {"add", "replace"}:
            _keys(value, {"id", "title", "detail", "unlock_choice",
                          "depends_on", "required"})
            if action == "add":
                candidate["clues"].append(value)
            else:
                found = [i for i, old in enumerate(candidate["clues"])
                         if old["id"] == value["id"]]
                if len(found) != 1:
                    raise CanonError("unknown_evidence")
                candidate["clues"][found[0]] = value
        elif action == "remove":
            _keys(value, {"id"})
            before = len(candidate["clues"])
            candidate["clues"] = [clue for clue in candidate["clues"]
                                  if clue["id"] != value["id"]]
            if len(candidate["clues"]) != before - 1:
                raise CanonError("unknown_evidence")
        else:
            raise CanonError("unsupported_evidence_edit")
    candidate["clues"].sort(key=lambda x: x["id"])
    candidate["approved"] = False
    candidate["review_note"] = ""
    return validate_evidence(candidate, world)


def approve_evidence(data: Any, world: Any, note: str) -> dict[str, Any]:
    validate_evidence(data, world)
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(data))
    candidate["approved"] = True
    candidate["review_note"] = note
    return validate_evidence(candidate, world)


def _earn(clues: list[dict[str, Any]], observed: frozenset[str],
          collected: frozenset[str]) -> frozenset[str]:
    earned = set(collected)
    while True:
        newly = {
            clue["id"] for clue in clues
            if clue["id"] not in earned
            and clue["unlock_choice"] in observed
            and set(clue["depends_on"]) <= earned
        }
        if not newly:
            return frozenset(earned)
        earned.update(newly)


def replay_evidence(data: Any, world: Any, choices: Any) -> dict[str, Any]:
    validate_evidence(data, world)
    replay = replay_choices(world, choices)
    observed: set[str] = set()
    collected: frozenset[str] = frozenset()
    earned_at: list[dict[str, Any]] = []
    for index, step in enumerate(replay["steps"][1:], 1):
        observed.add(step["choice"])
        updated = _earn(data["clues"], frozenset(observed), collected)
        for cid in sorted(updated - collected):
            earned_at.append({"id": cid, "step": index,
                              "choice_id": step["choice"]})
        collected = updated
    required = {c["id"] for c in data["clues"] if c["required"]}
    return {
        "world_digest": digest(world), "evidence_digest": digest(data),
        "scene": replay["scene"], "ending": replay["ending"],
        "collected": sorted(collected),
        "remaining_required": sorted(required - collected),
        "visible_clues": [
            {"id": c["id"], "title": c["title"], "detail": c["detail"]}
            for c in data["clues"] if c["id"] in collected
        ],
        "earned_at": earned_at,
        "complete": replay["ending"] is not None and required <= collected,
    }


def solve_evidence(data: Any, world: Any) -> tuple[str, ...]:
    validate_evidence(data, world)
    choices = {}
    for edge in world["choices"]:
        choices.setdefault(edge["from"], []).append(edge)
    for outgoing in choices.values():
        outgoing.sort(key=lambda c: c["id"])
    endings = {e["scene"] for e in world["endings"]}
    relevant = {c["unlock_choice"] for c in data["clues"]}
    required = {c["id"] for c in data["clues"] if c["required"]}
    initial = (world["start"], frozenset(), frozenset(), frozenset())
    queue = deque([(initial, ())])
    visited = {initial}
    truncated = False
    while queue:
        (scene, flags, observed, collected), trace = queue.popleft()
        if scene in endings:
            if required <= collected:
                return trace
            continue
        outgoing = [c for c in choices.get(scene, [])
                    if set(c["requires"]) <= flags]
        if len(trace) >= MAX_STEPS:
            truncated |= bool(outgoing)
            continue
        for choice in outgoing:
            next_observed = observed | ({choice["id"]} if choice["id"] in relevant
                                        else set())
            next_collected = _earn(data["clues"], frozenset(next_observed),
                                   collected)
            state = (choice["to"], flags | frozenset(choice["grants"]),
                     frozenset(next_observed), next_collected)
            if state in visited:
                continue
            if len(visited) >= MAX_STATES:
                raise CanonError("evidence_search_inconclusive")
            visited.add(state)
            queue.append((state, trace + (choice["id"],)))
    if truncated:
        raise CanonError("evidence_search_inconclusive")
    raise CanonError("evidence_unreachable")


def compile_evidence(data: Any, world: Any) -> dict[str, Any]:
    validate_evidence(data, world)
    if not data["approved"]:
        raise CanonError("evidence_review_required")
    witness = solve_evidence(data, world)
    outcome = replay_evidence(data, world, list(witness))
    if not outcome["complete"]:
        raise CanonError("evidence_witness_invalid")
    return {
        "schema": HANDOFF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "evidence_digest": digest(data),
        "choice_witness": list(witness), "outcome": outcome,
        "clues": data["clues"], "review_note": data["review_note"],
        "qualification": "source_replayed_not_device_or_release_certified",
    }


class EvidenceStore:
    """Private CAS custody, authored compilation and exact-byte verification."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".evidence.json"

    @staticmethod
    def _artifacts(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".evidence.playable.html",
                world_id + ".evidence.handoff.json",
                world_id + ".evidence.receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _data(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_evidence(
            strict_json(self.worlds._read(fd, self._name(world_id))), world)

    @staticmethod
    def _lock(fd: int, world_id: str) -> int:
        try:
            return os.open(world_id + ".lock",
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def read(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            return self._data(fd, world_id, world)
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
                validate_evidence(data, world)
                try:
                    old = digest(self._data(fd, world_id, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or expected_digest != old:
                    raise CanonError("stale_evidence")
                self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, data: Any):
        handoff = compile_evidence(data, world)
        names = self._artifacts(world["id"])
        from .overlay import compile_overlay_html
        contents = [compile_overlay_html(
            world, evidence=data).encode("utf-8"),
            canonical(handoff)]
        if any(len(content) > 524288 for content in contents):
            raise CanonError("evidence_output_too_large")
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "evidence_digest": digest(data),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], contents)
            },
            "qualification": "source_replay_not_release_certified",
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
                data = self._data(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_evidence")
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
                data = self._data(fd, world_id, world)
                expected, contents = self._outputs(world, data)
                names = self._artifacts(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != expected:
                    raise CanonError("evidence_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if self.worlds._read(fd, name) != content:
                        raise CanonError("evidence_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        from .session import SessionStore
        world = self.worlds.read(world_id)
        data = self.read(world_id)
        if not data["approved"]:
            raise CanonError("evidence_review_required")
        session = SessionStore(self.worlds.root).read(world_id, slot)
        validate_session(session, world)
        return replay_evidence(data, world, session["choices"])
