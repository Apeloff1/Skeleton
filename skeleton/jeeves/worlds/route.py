"""Source-leased, replay-proven route authoring for original Jeeves worlds.

Route approval is an explicit operator decision. Search witnesses are not model
claims: each choice is replayed against the canonical world transition rules.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, _keys, _list, _text,
    canonical, compile_html, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.route_review.v1"
HANDOFF_SCHEMA = "jeeves.world.route_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.route_receipt.v1"
MAX_STEPS = 512
MAX_EXCLUSIONS = 512


def _ids(values: Any, name: str, limit: int) -> list[str]:
    result = [_id(value, name) for value in _list(values, name, limit)]
    if result != sorted(set(result)):
        raise CanonError("noncanonical_route_ids", name)
    return result


def validate_spec(spec: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(spec, {
        "schema", "world_id", "world_digest", "ending", "requires_flags",
        "forbids_flags", "forbids_choices", "max_steps", "approved",
        "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("route_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("route_world_lease_mismatch")
    ending = _id(obj["ending"], "ending")
    if ending not in {item["scene"] for item in world["endings"]}:
        raise CanonError("unknown_route_ending")
    required = _ids(obj["requires_flags"], "requires_flags", 64)
    forbidden = _ids(obj["forbids_flags"], "forbids_flags", 64)
    excluded = _ids(obj["forbids_choices"], "forbids_choices", MAX_EXCLUSIONS)
    if set(required) & set(forbidden):
        raise CanonError("conflicting_route_flags")
    known_choices = {item["id"] for item in world["choices"]}
    if not set(excluded) <= known_choices:
        raise CanonError("unknown_excluded_choice")
    known_flags = {flag for item in world["choices"] for flag in item["grants"]}
    if not set(required) <= known_flags:
        raise CanonError("unknown_required_flag")
    if type(obj["max_steps"]) is not int or not 0 <= obj["max_steps"] <= MAX_STEPS:
        raise CanonError("invalid_route_budget")
    if type(obj["approved"]) is not bool:
        raise CanonError("invalid_route_approval")
    _text(obj["review_note"], "review_note", 512)
    if len(canonical(obj)) > 524288:
        raise CanonError("route_too_large")
    return obj


def propose_spec(world: Any, *, ending: str, requires_flags: list[str] | None = None,
                 forbids_flags: list[str] | None = None,
                 forbids_choices: list[str] | None = None,
                 max_steps: int = 128) -> dict[str, Any]:
    proof = prove(world)
    spec = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest, "ending": ending,
        "requires_flags": sorted(requires_flags or []),
        "forbids_flags": sorted(forbids_flags or []),
        "forbids_choices": sorted(forbids_choices or []),
        "max_steps": max_steps, "approved": False,
        "review_note": "Awaiting explicit operator route review",
    }
    return validate_spec(spec, world)


def _edges(world: Any) -> dict[str, list[dict[str, Any]]]:
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for options in edges.values():
        options.sort(key=lambda value: value["id"])
    return edges


def solve(spec: Any, world: Any) -> tuple[str, ...]:
    """Bounded BFS; inconclusive is never misreported as unreachable."""
    validate_spec(spec, world)
    edges = _edges(world)
    excluded = set(spec["forbids_choices"])
    forbidden = set(spec["forbids_flags"])
    required = set(spec["requires_flags"])
    ending_ids = {item["scene"] for item in world["endings"]}
    initial = (world["start"], frozenset())
    queue = deque([(initial, ())])
    seen = {initial}
    truncated = False
    while queue:
        (scene, flags), trace = queue.popleft()
        if scene == spec["ending"] and required <= flags:
            return trace
        if scene in ending_ids:
            continue
        enabled = [
            choice for choice in edges.get(scene, ())
            if choice["id"] not in excluded
            and set(choice["requires"]) <= flags
            and not set(choice["grants"]) & forbidden
        ]
        if len(trace) >= spec["max_steps"]:
            truncated |= bool(enabled)
            continue
        for choice in enabled:
            next_state = (
                choice["to"], flags | frozenset(choice["grants"]),
            )
            if next_state in seen:
                continue
            if len(seen) >= MAX_STATES:
                raise CanonError("route_search_inconclusive")
            seen.add(next_state)
            queue.append((next_state, trace + (choice["id"],)))
    if truncated:
        raise CanonError("route_search_inconclusive")
    raise CanonError("route_unreachable")


def replay(spec: Any, world: Any, trace: Any) -> dict[str, Any]:
    """Independent transition replay; never trusts a searcher's witness."""
    validate_spec(spec, world)
    choices = {item["id"]: item for item in world["choices"]}
    steps = _list(trace, "trace", MAX_STEPS)
    if len(steps) > spec["max_steps"]:
        raise CanonError("route_trace_budget")
    scene = world["start"]
    flags: set[str] = set()
    forbidden = set(spec["forbids_flags"])
    excluded = set(spec["forbids_choices"])
    ending_ids = {item["scene"] for item in world["endings"]}
    scenes = {item["id"]: item for item in world["scenes"]}
    witness = [{"scene": scene, "title": scenes[scene]["title"],
                "flags": [], "choice": None}]
    for choice_id in steps:
        _id(choice_id, "trace.choice")
        choice = choices.get(choice_id)
        if choice is None or choice["from"] != scene:
            raise CanonError("route_invalid_transition", choice_id)
        if scene in ending_ids:
            raise CanonError("route_after_ending", choice_id)
        if (choice_id in excluded or
            not set(choice["requires"]) <= flags or
            set(choice["grants"]) & forbidden):
            raise CanonError("route_forbidden_transition", choice_id)
        flags.update(choice["grants"])
        scene = choice["to"]
        witness.append({
            "scene": scene, "title": scenes[scene]["title"],
            "flags": sorted(flags), "choice": choice_id,
        })
    if scene != spec["ending"] or not set(spec["requires_flags"]) <= flags:
        raise CanonError("route_witness_incomplete")
    return {
        "schema": HANDOFF_SCHEMA,
        "world_id": world["id"],
        "world_digest": digest(world),
        "route_digest": digest(spec),
        "ending": scene,
        "choice_trace": list(steps),
        "steps": witness,
        "ending_label": next(item["label"] for item in world["endings"]
                             if item["scene"] == scene),
        "operator_approved": spec["approved"],
        "review_note": spec["review_note"],
    }


def approve_spec(spec: Any, world: Any, note: str) -> dict[str, Any]:
    validate_spec(spec, world)
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(spec))
    candidate["approved"] = True
    candidate["review_note"] = note
    replay(candidate, world, solve(candidate, world))
    return candidate


def compile_route(spec: Any, world: Any) -> dict[str, Any]:
    validate_spec(spec, world)
    if not spec["approved"]:
        raise CanonError("route_review_required")
    trace = solve(spec, world)
    return replay(spec, world, list(trace))


def render_guide(handoff: Any) -> bytes:
    """Static CSP guide complements the real compiled offline playable HTML."""
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise CanonError("invalid_route_handoff")
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "style-src 'none'; script-src 'none'; base-uri 'none'; form-action 'none'\">",
        "<title>Reviewed route witness</title></head><body>",
        "<main><h1>Reviewed route witness</h1>",
        "<p>Replay these authored choices in the compiled offline playable world.</p>",
        "<ol>",
    ]
    for step in handoff["steps"]:
        label = html.escape(step["title"], quote=True)
        choice = html.escape(step["choice"] or "start", quote=True)
        parts.append("<li>" + label + " — " + choice + "</li>")
    parts.extend([
        "</ol><p>Ending: ", html.escape(handoff["ending_label"], quote=True),
        "</p><p>World SHA-256: ",
        html.escape(handoff["world_digest"], quote=True),
        "</p><p>Route SHA-256: ",
        html.escape(handoff["route_digest"], quote=True),
        "</p></main></body></html>\n",
    ])
    return "".join(parts).encode("utf-8")


class RouteStore:
    """Descriptor-anchored, serialized route custody with optimistic source leases."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".route.json"

    def _source(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        prove(world)
        return world

    def _read_spec(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        data = strict_json(self.worlds._read(fd, self._name(world_id)))
        return validate_spec(data, world)

    def read(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._source(fd, world_id)
            return self._read_spec(fd, world_id, world)
        finally:
            os.close(fd)

    def _locked(self, fd: int, world_id: str) -> int:
        _id(world_id, "world_id")
        try:
            return os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                           os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def publish(self, world_id: str, spec: Any, *,
                expected_digest: str | None = None,
                create: bool = False) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._locked(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._source(fd, world_id)
                validate_spec(spec, world)
                if spec["world_id"] != world_id:
                    raise CanonError("identity_mismatch")
                try:
                    old = digest(self._read_spec(fd, world_id, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_route")
                self.worlds._write(fd, self._name(world_id), canonical(spec))
                return digest(spec)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    @staticmethod
    def _artifact_names(world_id: str) -> tuple[str, str, str, str]:
        return (
            world_id + ".route.playable.html",
            world_id + ".route.guide.html",
            world_id + ".route.witness.json",
            world_id + ".route.receipt.json",
        )

    def _outputs(self, world: Any, spec: Any) -> tuple[dict[str, Any], list[bytes]]:
        witness = compile_route(spec, world)
        artifacts = [
            compile_html(world).encode("utf-8"),
            render_guide(witness),
            canonical(witness),
        ]
        names = self._artifact_names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "route_digest": digest(spec),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:3], artifacts)
            },
            "qualification": "operator_review_only_not_device_or_release_certified",
        }
        return receipt, artifacts

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._locked(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._source(fd, world_id)
                spec = self._read_spec(fd, world_id, world)
                if digest(spec) != expected_digest:
                    raise CanonError("stale_route")
                receipt, artifacts = self._outputs(world, spec)
                names = self._artifact_names(world_id)
                for name, payload in zip(names[:3], artifacts):
                    self.worlds._write(fd, name, payload)
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
            lock_fd = self._locked(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._source(fd, world_id)
                spec = self._read_spec(fd, world_id, world)
                expected, artifacts = self._outputs(world, spec)
                names = self._artifact_names(world_id)
                receipt = strict_json(self.worlds._read(fd, names[3]))
                if receipt != expected:
                    raise CanonError("route_receipt_mismatch")
                for name, payload in zip(names[:3], artifacts):
                    actual = _artifact_read(fd, name)
                    if actual != payload:
                        raise CanonError("route_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
