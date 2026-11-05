"""Original lore canon with branch-aware contradiction and player reveal proof.

Facts are explicitly authored. A fact is only revealed by an actual world
scene and earned flags. Contradictory facts may coexist in the catalog only
when no valid player trace can reveal both. All exploration is bounded.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .session import replay_choices, validate_session
from .timeline import _reachable_flags
from .world_canon import (
    CanonError, MAX_STATES, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.lore.v1"
HANDOFF_SCHEMA = "jeeves.world.lore_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.lore_receipt.v1"
MAX_FACTS = 128
MAX_CONFLICTS = 32


def _ids(value: Any, field: str, limit: int) -> list[str]:
    ids = [_id(item, field) for item in _list(value, field, limit)]
    if ids != sorted(set(ids)):
        raise CanonError("lore_ids_noncanonical", field)
    return ids


def _revealed(facts: list[dict[str, Any]], scene: str,
              flags: frozenset[str]) -> frozenset[str]:
    return frozenset(
        fact["id"] for fact in facts
        if fact["scene"] == scene and set(fact["requires_flags"]) <= flags
    )


def _prove_contradictions(world: Any, facts: list[dict[str, Any]]) -> int:
    conflicts = {
        fact["id"]: set(fact["contradicts"]) for fact in facts
    }
    edges: dict[str, list[dict[str, Any]]] = {}
    for edge in world["choices"]:
        edges.setdefault(edge["from"], []).append(edge)
    for options in edges.values():
        options.sort(key=lambda item: item["id"])
    start = world["start"]
    initial_flags: frozenset[str] = frozenset()
    initial_seen = _revealed(facts, start, initial_flags)
    initial = (start, initial_flags, initial_seen)
    queue = deque([initial])
    visited = {initial}
    while queue:
        scene, flags, seen = queue.popleft()
        for fact_id in seen:
            if conflicts[fact_id] & seen:
                raise CanonError("lore_canon_contradiction", fact_id)
        for edge in edges.get(scene, ()):
            if not set(edge["requires"]) <= flags:
                continue
            next_flags = flags | frozenset(edge["grants"])
            next_seen = seen | _revealed(facts, edge["to"], next_flags)
            state = (edge["to"], next_flags, next_seen)
            if state in visited:
                continue
            if len(visited) >= MAX_STATES:
                raise CanonError("lore_proof_inconclusive")
            visited.add(state)
            queue.append(state)
    return len(visited)


def validate_lore(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "prompt",
        "facts", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("lore_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("lore_world_lease_mismatch")
    _text(obj["prompt"], "prompt", 2048)
    if type(obj["approved"]) is not bool:
        raise CanonError("lore_approval_invalid")
    _text(obj["review_note"], "review_note", 512)
    facts = _list(obj["facts"], "facts", MAX_FACTS)
    if not facts:
        raise CanonError("lore_empty")
    reachable = _reachable_flags(world)
    known_scenes = {scene["id"] for scene in world["scenes"]}
    known_flags = {flag for edge in world["choices"] for flag in edge["grants"]}
    by_id: dict[str, dict[str, Any]] = {}
    for fact in facts:
        _keys(fact, {
            "id", "subject", "scene", "statement",
            "requires_flags", "contradicts",
        })
        fact_id = _id(fact["id"], "fact.id")
        if fact_id in by_id:
            raise CanonError("lore_duplicate_fact", fact_id)
        by_id[fact_id] = fact
        _text(fact["subject"], "fact.subject", 200)
        _text(fact["statement"], "fact.statement", 2048)
        scene = _id(fact["scene"], "fact.scene")
        if scene not in known_scenes:
            raise CanonError("lore_unknown_scene", fact_id)
        required = _ids(fact["requires_flags"], "requires_flags", 64)
        if not set(required) <= known_flags:
            raise CanonError("lore_unknown_flag", fact_id)
        if not any(set(required) <= flags for flags in reachable.get(scene, ())):
            raise CanonError("lore_unreachable_fact", fact_id)
        _ids(fact["contradicts"], "contradicts", MAX_CONFLICTS)
    for fact_id, fact in by_id.items():
        for other in fact["contradicts"]:
            if other == fact_id or other not in by_id:
                raise CanonError("lore_invalid_contradiction", fact_id)
            if fact_id not in by_id[other]["contradicts"]:
                raise CanonError("lore_asymmetric_contradiction", fact_id)
    if len(canonical(obj)) > 524288:
        raise CanonError("lore_source_too_large")
    _prove_contradictions(world, facts)
    return obj


def propose_lore(world: Any, *, prompt: str, subject: str,
                 statement: str) -> dict[str, Any]:
    proof = prove(world)
    data = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest, "prompt": prompt,
        "facts": [{
            "id": "origin", "subject": subject, "scene": world["start"],
            "statement": statement, "requires_flags": [],
            "contradicts": [],
        }],
        "approved": False, "review_note": "Original author review required",
    }
    return validate_lore(data, world)


def edit_lore(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_lore(data, world)
    top = _keys(operation, {"action", "value"})
    operations = (_list(top["value"], "batch", 64)
                  if top["action"] == "batch" else [top])
    if not operations:
        raise CanonError("lore_empty_batch")
    candidate = strict_json(canonical(data))
    for entry in operations:
        op = _keys(entry, {"action", "value"})
        action, value = op["action"], op["value"]
        if action in ("add", "replace"):
            _keys(value, {
                "id", "subject", "scene", "statement",
                "requires_flags", "contradicts",
            })
            if action == "add":
                candidate["facts"].append(value)
            else:
                matches = [i for i, fact in enumerate(candidate["facts"])
                           if fact["id"] == value["id"]]
                if len(matches) != 1:
                    raise CanonError("lore_unknown_fact")
                candidate["facts"][matches[0]] = value
        elif action == "remove":
            _keys(value, {"id"})
            before = len(candidate["facts"])
            candidate["facts"] = [fact for fact in candidate["facts"]
                                  if fact["id"] != value["id"]]
            if len(candidate["facts"]) != before - 1:
                raise CanonError("lore_unknown_fact")
        else:
            raise CanonError("lore_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Lore changed; renewed review required"
    return validate_lore(candidate, world)


def reveal_lore(data: Any, world: Any, session: Any) -> dict[str, Any]:
    validate_lore(data, world)
    validate_session(session, world)
    replay = replay_choices(world, session["choices"])
    seen: set[str] = set()
    reveals: list[dict[str, Any]] = []
    for index, step in enumerate(replay["steps"]):
        newly = sorted(_revealed(data["facts"], step["scene"],
                                 frozenset(step["flags"])) - seen)
        for fact_id in newly:
            fact = next(fact for fact in data["facts"] if fact["id"] == fact_id)
            reveals.append({
                "fact_id": fact_id, "subject": fact["subject"],
                "statement": fact["statement"], "scene": step["scene"],
                "first_seen_step": index,
            })
        seen.update(newly)
    return {
        "world_digest": digest(world), "lore_digest": digest(data),
        "session_digest": digest(session), "revealed": reveals,
        "remaining": sorted({fact["id"] for fact in data["facts"]} - seen),
        "qualification": "replayed_player_reveal_not_release_certified",
    }


def approve_lore(data: Any, world: Any, note: str) -> dict[str, Any]:
    validate_lore(data, world)
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(data))
    candidate["approved"] = True
    candidate["review_note"] = note
    return validate_lore(candidate, world)


def compile_lore(data: Any, world: Any) -> dict[str, Any]:
    validate_lore(data, world)
    if not data["approved"]:
        raise CanonError("lore_review_required")
    return {
        "schema": HANDOFF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "lore_digest": digest(data),
        "prompt": data["prompt"], "facts": data["facts"],
        "states_proven": _prove_contradictions(world, data["facts"]),
        "review_note": data["review_note"],
        "qualification": "author_approved_source_proven_not_release_certified",
    }


def render_lore(manifest: Any) -> bytes:
    if type(manifest) is not dict or manifest.get("schema") != HANDOFF_SCHEMA:
        raise CanonError("lore_invalid_handoff")
    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; ",
        "script-src 'none'; style-src 'none'; base-uri 'none'; form-action 'none'\">",
        "<title>Reviewed original lore</title></head><body><main>",
        "<h1>Original lore canon</h1><p>", esc(manifest["prompt"]), "</p><ol>",
    ]
    for fact in manifest["facts"]:
        parts.extend([
            "<li><strong>", esc(fact["subject"]), "</strong> — ",
            esc(fact["statement"]), " (scene: ", esc(fact["scene"]), ")</li>",
        ])
    parts.extend(["</ol><p>Source SHA-256: ", esc(manifest["world_digest"]),
                  "</p></main></body></html>\n"])
    return "".join(parts).encode("utf-8")


class LoreStore:
    """World-lock CAS custody and independently verified playable/lore artifacts."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".lore.json"

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        stem = _id(world_id, "world_id") + ".lore"
        return (stem + ".playable.html", stem + ".atlas.html",
                stem + ".handoff.json", stem + ".receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _read(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_lore(
            strict_json(self.worlds._read(fd, self._name(world_id))), world,
        )

    def _lock(self, fd: int, world_id: str) -> int:
        _id(world_id, "world_id")
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
            return self._read(fd, world_id, world)
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                validate_lore(data, world)
                if data["world_id"] != world_id:
                    raise CanonError("identity_mismatch")
                try:
                    old = digest(self._read(fd, world_id, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_lore")
                self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, world: Any, data: Any):
        from .lore_player import render_lore_playable
        handoff = compile_lore(data, world)
        contents = [
            render_lore_playable(world, data),
            render_lore(handoff), canonical(handoff),
        ]
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "lore_digest": digest(data),
            "artifacts": {
                name: sha256(payload).hexdigest()
                for name, payload in zip(names[:3], contents)
            },
            "qualification": "source_proven_not_device_or_release_certified",
        }
        return receipt, contents

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_lore")
                receipt, contents = self._outputs(world, data)
                names = self._names(world_id)
                for name, payload in zip(names[:3], contents):
                    self.worlds._write(fd, name, payload)
                self.worlds._write(fd, names[3], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                data = self._read(fd, world_id, world)
                expected, contents = self._outputs(world, data)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[3])) != expected:
                    raise CanonError("lore_receipt_mismatch")
                for name, payload in zip(names[:3], contents):
                    if _artifact_read(fd, name) != payload:
                        raise CanonError("lore_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
