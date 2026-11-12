"""Temporal continuity and causal event compilation for authored playable worlds."""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import os
from typing import Any

from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, _keys, _list, _text, canonical,
    compile_manifest, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.timeline.v1"
MAX_EVENTS = 256
KINDS = frozenset({"setup", "observation", "decision", "consequence", "resolution"})


def _reachable_flags(world: dict[str, Any]) -> dict[str, set[frozenset[str]]]:
    edges: dict[str, list[dict[str, Any]]] = {}
    for edge in world["choices"]:
        edges.setdefault(edge["from"], []).append(edge)
    queue = deque([(world["start"], frozenset())])
    seen = {(world["start"], frozenset())}
    states: dict[str, set[frozenset[str]]] = {}
    while queue:
        scene, flags = queue.popleft()
        states.setdefault(scene, set()).add(flags)
        for edge in edges.get(scene, []):
            if not set(edge["requires"]) <= flags:
                continue
            next_state = (edge["to"], flags | frozenset(edge["grants"]))
            if next_state not in seen:
                seen.add(next_state)
                if len(seen) > MAX_STATES:
                    raise CanonError("timeline_state_budget")
                queue.append(next_state)
    return states


def validate_timeline(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {"schema", "world_id", "world_digest", "events"})
    if obj["schema"] != SCHEMA:
        raise CanonError("timeline_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("timeline_world_lease_mismatch")
    events = _list(obj["events"], "events", MAX_EVENTS)
    if not events:
        raise CanonError("timeline_empty")
    scene_ids = {scene["id"] for scene in world["scenes"]}
    ending_ids = {ending["scene"] for ending in world["endings"]}
    reachable_flags = _reachable_flags(world)
    by_id: dict[str, dict[str, Any]] = {}
    actor_slots: set[tuple[str, int]] = set()
    min_tick: dict[str, int] = {}
    for event in events:
        _keys(event, {"id", "scene", "actor", "tick", "kind", "description",
                      "depends_on", "requires_flags"})
        eid = _id(event["id"], "event.id")
        if eid in by_id:
            raise CanonError("duplicate_event", eid)
        by_id[eid] = event
        scene = _id(event["scene"], "event.scene")
        if scene not in scene_ids:
            raise CanonError("unknown_event_scene", eid)
        actor = _id(event["actor"], "event.actor")
        tick = event["tick"]
        if type(tick) is not int or not 0 <= tick <= 1000000:
            raise CanonError("invalid_event_tick", eid)
        if event["kind"] not in KINDS:
            raise CanonError("invalid_event_kind", eid)
        _text(event["description"], "event.description", 2048)
        depends = [_id(x, "depends_on") for x in _list(
            event["depends_on"], "depends_on", 32)]
        requires = [_id(x, "requires_flags") for x in _list(
            event["requires_flags"], "requires_flags", 32)]
        if depends != sorted(set(depends)) or requires != sorted(set(requires)):
            raise CanonError("noncanonical_event_dependencies", eid)
        if not any(set(requires) <= flags for flags in reachable_flags.get(scene, ())):
            raise CanonError("unreachable_event_precondition", eid)
        if (actor, tick) in actor_slots:
            raise CanonError("actor_double_booked", eid)
        actor_slots.add((actor, tick))
        min_tick[scene] = min(tick, min_tick.get(scene, tick))
    if set(min_tick) != scene_ids:
        raise CanonError("unannotated_scene",
                         ",".join(sorted(scene_ids - set(min_tick))))
    for event in events:
        for predecessor in event["depends_on"]:
            if predecessor not in by_id:
                raise CanonError("unknown_event_predecessor", predecessor)
            if by_id[predecessor]["tick"] >= event["tick"]:
                raise CanonError("causal_time_paradox", event["id"])
    # A cycle cannot satisfy strict increasing predecessor ticks, so no
    # separate unbounded recursive topological traversal is needed.
    for edge in world["choices"]:
        if min_tick[edge["to"]] < min_tick[edge["from"]]:
            raise CanonError("backward_scene_clock", edge["id"])
    for ending in ending_ids:
        if not any(e["scene"] == ending and e["kind"] == "resolution"
                   for e in events):
            raise CanonError("ending_without_resolution_event", ending)
    if len(canonical(obj)) > 524288:
        raise CanonError("source_too_large")
    return obj


def propose_timeline(world: Any, *, actor: str, opening_note: str,
                     resolution_note: str) -> dict[str, Any]:
    proof = prove(world)
    _id(actor, "actor")
    _text(opening_note, "opening_note", 2048)
    _text(resolution_note, "resolution_note", 2048)
    # A reviewed timeline must annotate *every* authored scene, not just its
    # opening and endings. Derive one stable causal order from actual edges.
    # Cyclic graphs cannot be placed on a single actor's strictly occupied
    # clock without explicit authored review, and must fail closed.
    scene_ids = {scene["id"] for scene in world["scenes"]}
    edges: dict[str, set[str]] = {scene: set() for scene in scene_ids}
    incoming = {scene: 0 for scene in scene_ids}
    for edge in world["choices"]:
        before, after = edge["from"], edge["to"]
        if after not in edges[before]:
            edges[before].add(after)
            incoming[after] += 1
    ready = sorted(scene for scene, count in incoming.items() if count == 0)
    ordered: list[str] = []
    while ready:
        scene = ready.pop(0)
        ordered.append(scene)
        for successor in sorted(edges[scene]):
            incoming[successor] -= 1
            if incoming[successor] == 0:
                ready.append(successor)
                ready.sort()
    if len(ordered) != len(scene_ids) or ordered[0] != world["start"]:
        raise CanonError("timeline_cycle_requires_explicit_review")
    endings = sorted(ending["scene"] for ending in world["endings"])
    ending_order = {scene: index for index, scene in enumerate(endings, 1)}
    scene_notes = {scene["id"]: scene["title"] for scene in world["scenes"]}
    events = []
    for tick, scene in enumerate(ordered):
        if scene == world["start"]:
            event_id, kind, description = "setup", "setup", opening_note
        elif scene in ending_order:
            event_id = f"resolution_{ending_order[scene]}"
            kind, description = "resolution", resolution_note
        else:
            event_id = f"observation_{tick}"
            kind, description = "observation", "Enter: " + scene_notes[scene]
        events.append({
            "id": event_id, "scene": scene, "actor": actor,
            "tick": tick, "kind": kind, "description": description,
            "depends_on": [] if tick == 0 else ["setup"],
            "requires_flags": [],
        })
    data = {"schema": SCHEMA, "world_id": world["id"],
            "world_digest": proof.source_digest, "events": events}
    validate_timeline(data, world)
    return data


def edit_timeline(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_timeline(data, world)
    op = _keys(operation, {"action", "value"})
    ops = _list(op["value"], "batch", 64) if op["action"] == "batch" else [op]
    if not ops:
        raise CanonError("empty_timeline_batch")
    candidate = strict_json(canonical(data))
    for entry in ops:
        item = _keys(entry, {"action", "value"})
        action, value = item["action"], item["value"]
        if action == "add":
            _keys(value, {"id", "scene", "actor", "tick", "kind", "description",
                          "depends_on", "requires_flags"})
            candidate["events"].append(value)
        elif action == "replace":
            _keys(value, {"id", "scene", "actor", "tick", "kind", "description",
                          "depends_on", "requires_flags"})
            matches = [i for i, e in enumerate(candidate["events"])
                       if e["id"] == value["id"]]
            if len(matches) != 1:
                raise CanonError("unknown_event")
            candidate["events"][matches[0]] = value
        elif action == "remove":
            _keys(value, {"id"})
            before = len(candidate["events"])
            candidate["events"] = [e for e in candidate["events"]
                                   if e["id"] != value["id"]]
            if len(candidate["events"]) != before - 1:
                raise CanonError("unknown_event")
        else:
            raise CanonError("unsupported_timeline_edit", str(action))
    return validate_timeline(candidate, world)


def compile_timeline(data: Any, world: Any) -> dict[str, Any]:
    validate_timeline(data, world)
    # The playable world remains the authority for actual branch traversal.
    # Event cues are deterministic annotations, not fabricated engine actions.
    playable = compile_manifest(world)
    events = sorted(data["events"], key=lambda e: (e["tick"], e["id"]))
    return {
        "schema": "jeeves.world.temporal_handoff.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "timeline_digest": digest(data),
        "playable_proof": playable["proof"],
        "events": events,
        "timing": "logical_ticks_not_wall_clock",
    }


class TimelineStore:
    """World-lease-serialized durable timeline source and verified compilation."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".timeline.json"

    def read(self, world_id: str) -> dict[str, Any]:
        world = self.worlds.read(world_id)
        fd = self.worlds._directory()
        try:
            data = strict_json(self.worlds._read(fd, self._name(world_id)))
            return validate_timeline(data, world)
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        _id(world_id, "world_id")
        if create and expected_digest is not None:
            raise CanonError("invalid_lease")
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
                world = strict_json(self.worlds._read(fd, world_id + ".json"))
                validate_timeline(data, world)
                try:
                    previous = strict_json(self.worlds._read(fd, self._name(world_id)))
                    old = digest(validate_timeline(previous, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_timeline")
                self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
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
                world = strict_json(self.worlds._read(fd, world_id + ".json"))
                data = strict_json(self.worlds._read(fd, self._name(world_id)))
                validate_timeline(data, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_timeline")
                handoff = compile_timeline(data, world)
                payload = canonical(handoff)
                self.worlds._write(fd, world_id + ".timeline.compiled.json", payload)
                return {"world_id": world_id, "world_digest": digest(world),
                        "timeline_digest": digest(data),
                        "manifest_sha256": sha256(payload).hexdigest(),
                        "compiled_file": world_id + ".timeline.compiled.json"}
            finally:
                os.unlink(lock, dir_fd=fd)
        finally:
            os.close(fd)
