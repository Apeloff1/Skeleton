"""Exhaustive bounded world-state invariants with canonical witness replay.

An authored safety/continuity invariant is checked against EVERY reachable
scene+earned-flag state. Inconclusive or unexercised rules never pass silently.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import os
from typing import Any

from .bundle import _artifact_read
from .session import replay_choices
from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, _keys, _list, _text,
    _flags, canonical, compile_html, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.invariant_suite.v1"
REPORT_SCHEMA = "jeeves.world.invariant_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.invariant_receipt.v1"
MAX_RULES = 64
MAX_TRANSITIONS = 65536
MAX_HTML = 1572864
KINDS = {
    "forbid_all_flags", "require_all_at_scene",
    "forbid_any_at_scene", "require_any_at_ending",
}


def validate_suite(spec: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(spec, {
        "schema", "world_id", "world_digest", "rules", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("invariant_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("invariant_world_lease_mismatch")
    if type(obj["approved"]) is not bool:
        raise CanonError("invariant_invalid_approval")
    _text(obj["review_note"], "review_note", 512)
    rules = _list(obj["rules"], "rules", MAX_RULES)
    if not rules:
        raise CanonError("invariant_empty_rules")
    scenes = {item["id"] for item in world["scenes"]}
    endings = {item["scene"] for item in world["endings"]}
    known_flags = {flag for choice in world["choices"] for flag in choice["grants"]}
    seen: set[str] = set()
    for rule in rules:
        _keys(rule, {"id", "kind", "scene", "flags"})
        rid = _id(rule["id"], "rule.id")
        if rid in seen:
            raise CanonError("invariant_duplicate_rule", rid)
        seen.add(rid)
        kind = rule["kind"]
        if type(kind) is not str or kind not in KINDS:
            raise CanonError("invariant_unknown_kind", rid)
        flags = _flags(rule["flags"], "rule.flags")
        if not flags or len(flags) > 8 or not set(flags) <= known_flags:
            raise CanonError("invariant_invalid_flags", rid)
        if kind == "forbid_all_flags":
            if rule["scene"] is not None or len(flags) < 2:
                raise CanonError("invariant_invalid_global_rule", rid)
        else:
            scene = _id(rule["scene"], "rule.scene")
            if scene not in scenes:
                raise CanonError("invariant_unknown_scene", rid)
            if kind == "require_any_at_ending" and scene not in endings:
                raise CanonError("invariant_not_ending", rid)
    if len(canonical(obj)) > 524288:
        raise CanonError("invariant_suite_too_large")
    return obj


def prove_invariants(spec: Any, world: Any) -> dict[str, Any]:
    """Bounded BFS over actual player transitions; one shortest witness per rule."""
    validate_suite(spec, world)
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        by_scene.setdefault(choice["from"], []).append(choice)
    for edges in by_scene.values():
        edges.sort(key=lambda edge: edge["id"])
    endings = {item["scene"] for item in world["endings"]}
    initial = (world["start"], frozenset())
    queue = deque([initial])
    traces = {initial: ()}
    transitions = 0
    while queue:
        scene, flags = queue.popleft()
        if scene in endings:
            continue
        for edge in by_scene.get(scene, ()):
            if not set(edge["requires"]) <= flags:
                continue
            target = (edge["to"], flags | frozenset(edge["grants"]))
            transitions += 1
            if transitions > MAX_TRANSITIONS:
                raise CanonError("invariant_transition_budget")
            if target not in traces:
                if len(traces) >= MAX_STATES:
                    raise CanonError("invariant_state_budget")
                traces[target] = traces[(scene, flags)] + (edge["id"],)
                queue.append(target)
    results = []
    ordered_states = sorted(
        traces, key=lambda state: (len(traces[state]), traces[state], state[0], sorted(state[1])),
    )
    for rule in sorted(spec["rules"], key=lambda value: value["id"]):
        kind = rule["kind"]
        required = set(rule["flags"])
        exercised = 0
        violations = 0
        witness = None
        observed = None
        for scene, flags in ordered_states:
            if kind == "forbid_all_flags":
                applicable = True
                bad = required <= flags
            else:
                applicable = scene == rule["scene"]
                if kind == "require_all_at_scene":
                    bad = not required <= flags
                elif kind == "forbid_any_at_scene":
                    bad = bool(required & flags)
                else:
                    bad = not bool(required & flags)
            if not applicable:
                continue
            exercised += 1
            if bad:
                violations += 1
                if witness is None:
                    trace = traces[(scene, flags)]
                    playback = replay_choices(world, list(trace))
                    if playback["scene"] != scene or playback["flags"] != sorted(flags):
                        raise CanonError("invariant_witness_mismatch", rule["id"])
                    witness = list(trace)
                    observed = {"scene": scene, "flags": sorted(flags)}
        status = (
            "unexercised" if exercised == 0 else
            "violation" if violations else "passed"
        )
        results.append({
            "id": rule["id"], "kind": kind, "status": status,
            "exercised_states": exercised, "violating_states": violations,
            "violation_witness": witness, "violation_state": observed,
        })
    report = {
        "schema": REPORT_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "suite_digest": digest(spec),
        "states_explored": len(traces), "transitions_explored": transitions,
        "rules": results, "complete": all(r["status"] == "passed" for r in results),
        "qualification": "bounded_exhaustive_state_proof_not_release_certified",
    }
    if len(canonical(report)) > 524288:
        raise CanonError("invariant_report_too_large")
    return report


class InvariantStore:
    """Reviewed private invariant rules and verified playable handoff."""

    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".invariants.json",
            world_id + ".invariants.report.json",
            world_id + ".invariants.playable.html",
            world_id + ".invariants.receipt.json",
        )

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                os.O_NOFOLLOW, 0o600, dir_fd=fd,
            )
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("invariant_identity_mismatch")
        return world

    def _spec(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        spec = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_suite(spec, world)

    def propose(self, world_id: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
        world = self.worlds.read(world_id)
        return validate_suite({
            "schema": SCHEMA, "world_id": world_id,
            "world_digest": digest(world), "rules": rules,
            "approved": False, "review_note": "Awaiting operator invariant review",
        }, world)

    def save(self, world_id: str, spec: Any, *,
             expected_world_digest: str) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                if digest(world) != expected_world_digest:
                    raise CanonError("invariant_stale_source")
                validate_suite(spec, world)
                if spec["approved"]:
                    raise CanonError("invariant_implicit_approval_forbidden")
                name = self._names(world_id)[0]
                try:
                    self.worlds._read(fd, name)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                else:
                    raise CanonError("invariant_already_exists")
                self.worlds._write(fd, name, canonical(spec))
                return digest(spec)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            spec = self._spec(fd, world_id, world)
            return {"suite": spec, "report": prove_invariants(spec, world)}
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_suite_digest: str,
                review_note: str) -> str:
        _id(world_id, "world_id")
        _text(review_note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                spec = self._spec(fd, world_id, world)
                if digest(spec) != expected_suite_digest:
                    raise CanonError("invariant_stale_suite")
                if spec["approved"]:
                    raise CanonError("invariant_already_approved")
                if not prove_invariants(spec, world)["complete"]:
                    raise CanonError("invariant_proof_failed")
                updated = strict_json(canonical(spec))
                updated["approved"] = True
                updated["review_note"] = review_note
                validate_suite(updated, world)
                self.worlds._write(fd, self._names(world_id)[0], canonical(updated))
                return digest(updated)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    @staticmethod
    def _outputs(world: Any, spec: Any) -> tuple[dict[str, Any], tuple[bytes, bytes]]:
        report = prove_invariants(spec, world)
        if not spec["approved"]:
            raise CanonError("invariant_review_required")
        if not report["complete"]:
            raise CanonError("invariant_proof_failed")
        data = canonical(report)
        playable = compile_html(world).encode("utf-8")
        if len(playable) > MAX_HTML:
            raise CanonError("invariant_playable_too_large")
        names = InvariantStore._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "suite_digest": digest(spec),
            "report_digest": digest(report),
            "artifacts": {
                names[1]: sha256(data).hexdigest(),
                names[2]: sha256(playable).hexdigest(),
            },
            "qualification": "reviewed_source_proof_not_device_certified",
        }
        return receipt, (data, playable)

    def compile(self, world_id: str, *, expected_suite_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                spec = self._spec(fd, world_id, world)
                if digest(spec) != expected_suite_digest:
                    raise CanonError("invariant_stale_suite")
                receipt, outputs = self._outputs(world, spec)
                names = self._names(world_id)
                for name, data in zip(names[1:3], outputs):
                    self.worlds._write(fd, name, data)
                self.worlds._write(fd, names[3], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                names = self._names(world_id)
                stored = strict_json(self.worlds._read(fd, names[3]))
                world = self._world(fd, world_id)
                spec = self._spec(fd, world_id, world)
                receipt, outputs = self._outputs(world, spec)
                if stored != receipt:
                    raise CanonError("invariant_receipt_mismatch")
                for name, data in zip(names[1:3], outputs):
                    if _artifact_read(fd, name) != data:
                        raise CanonError("invariant_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
