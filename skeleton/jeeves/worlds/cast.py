"""Original NPC cast, authored dialogue and source-bound playable world continuity.

The player runtime uses the same world transitions and earned flags as canon
proof. Dialogue is displayed only when its actor is present and its
preconditions are earned on that exact scene state.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .timeline import _reachable_flags
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.cast.v1"
HANDOFF_SCHEMA = "jeeves.world.cast_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.cast_receipt.v1"
MAX_CHARACTERS = 128
MAX_LINES = 512
ROLES = frozenset({"protagonist", "companion", "npc", "antagonist"})


def _ordered_ids(value: Any, field: str, limit: int) -> list[str]:
    items = [_id(item, field) for item in _list(value, field, limit)]
    if items != sorted(set(items)):
        raise CanonError("cast_ids_not_canonical", field)
    return items


def validate_cast(data: Any, world: Any) -> dict[str, Any]:
    proof = prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "characters",
        "lines", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("cast_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != proof.source_digest:
        raise CanonError("cast_world_lease_mismatch")
    if type(obj["approved"]) is not bool:
        raise CanonError("invalid_cast_approval")
    _text(obj["review_note"], "review_note", 512)
    scenes = {item["id"] for item in world["scenes"]}
    characters = _list(obj["characters"], "characters", MAX_CHARACTERS)
    lines = _list(obj["lines"], "lines", MAX_LINES)
    if not characters or not lines:
        raise CanonError("empty_cast")
    actors: dict[str, dict[str, Any]] = {}
    for actor in characters:
        _keys(actor, {"id", "name", "role", "scenes", "traits"})
        actor_id = _id(actor["id"], "actor.id")
        if actor_id in actors:
            raise CanonError("duplicate_actor", actor_id)
        actors[actor_id] = actor
        _text(actor["name"], "actor.name", 200)
        if type(actor["role"]) is not str or actor["role"] not in ROLES:
            raise CanonError("invalid_actor_role", actor_id)
        presence = _ordered_ids(actor["scenes"], "actor.scenes", 128)
        if not presence or not set(presence) <= scenes:
            raise CanonError("invalid_actor_presence", actor_id)
        _ordered_ids(actor["traits"], "actor.traits", 64)
    reachable = _reachable_flags(world)
    line_ids: set[str] = set()
    order_slots: set[tuple[str, int]] = set()
    for line in lines:
        _keys(line, {"id", "scene", "speaker", "order", "text", "requires_flags"})
        line_id = _id(line["id"], "line.id")
        if line_id in line_ids:
            raise CanonError("duplicate_dialogue_line", line_id)
        line_ids.add(line_id)
        scene = _id(line["scene"], "line.scene")
        speaker = _id(line["speaker"], "line.speaker")
        if scene not in scenes:
            raise CanonError("unknown_dialogue_scene", line_id)
        if speaker not in actors or scene not in actors[speaker]["scenes"]:
            raise CanonError("absent_dialogue_speaker", line_id)
        if type(line["order"]) is not int or not 0 <= line["order"] <= 10000:
            raise CanonError("invalid_dialogue_order", line_id)
        slot = (scene, line["order"])
        if slot in order_slots:
            raise CanonError("dialogue_order_collision", line_id)
        order_slots.add(slot)
        _text(line["text"], "line.text", 4096)
        flags = _ordered_ids(line["requires_flags"], "line.requires_flags", 64)
        if not any(set(flags) <= state for state in reachable.get(scene, ())):
            raise CanonError("unreachable_dialogue_precondition", line_id)
    if len(canonical(obj)) > 524288:
        raise CanonError("cast_too_large")
    return obj


def propose_cast(world: Any, *, npc_id: str, npc_name: str,
                 npc_line: str) -> dict[str, Any]:
    proof = prove(world)
    _id(npc_id, "npc_id")
    _text(npc_name, "npc_name", 200)
    _text(npc_line, "npc_line", 4096)
    obj = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": proof.source_digest,
        "characters": [{
            "id": npc_id, "name": npc_name, "role": "npc",
            "scenes": [world["start"]], "traits": [],
        }],
        "lines": [{
            "id": "opening_line", "scene": world["start"],
            "speaker": npc_id, "order": 0, "text": npc_line,
            "requires_flags": [],
        }],
        "approved": False, "review_note": "Awaiting original-author review",
    }
    return validate_cast(obj, world)


def edit_cast(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_cast(data, world)
    top = _keys(operation, {"action", "value"})
    operations = (_list(top["value"], "batch", 64)
                  if top["action"] == "batch" else [top])
    if not operations:
        raise CanonError("empty_cast_edit_batch")
    candidate = strict_json(canonical(data))
    for operation_item in operations:
        item = _keys(operation_item, {"action", "value"})
        action, value = item["action"], item["value"]
        if action in {"add_actor", "replace_actor"}:
            _keys(value, {"id", "name", "role", "scenes", "traits"})
            target = candidate["characters"]
            if action == "add_actor":
                target.append(value)
            else:
                indices = [i for i, actor in enumerate(target)
                           if actor["id"] == value["id"]]
                if len(indices) != 1:
                    raise CanonError("unknown_actor")
                target[indices[0]] = value
        elif action in {"add_line", "replace_line"}:
            _keys(value, {"id", "scene", "speaker", "order", "text",
                          "requires_flags"})
            target = candidate["lines"]
            if action == "add_line":
                target.append(value)
            else:
                indices = [i for i, line in enumerate(target)
                           if line["id"] == value["id"]]
                if len(indices) != 1:
                    raise CanonError("unknown_dialogue_line")
                target[indices[0]] = value
        elif action in {"remove_actor", "remove_line"}:
            _keys(value, {"id"})
            target = candidate["characters" if action == "remove_actor" else "lines"]
            before = len(target)
            target[:] = [entry for entry in target if entry["id"] != value["id"]]
            if len(target) != before - 1:
                raise CanonError("unknown_cast_edit_target")
        else:
            raise CanonError("unsupported_cast_edit", str(action))
    candidate["approved"] = False
    candidate["review_note"] = "Changed source requires renewed author review"
    return validate_cast(candidate, world)


def approve_cast(data: Any, world: Any, note: str) -> dict[str, Any]:
    validate_cast(data, world)
    _text(note, "review_note", 512)
    candidate = strict_json(canonical(data))
    candidate["approved"] = True
    candidate["review_note"] = note
    return validate_cast(candidate, world)


def compile_cast(data: Any, world: Any) -> dict[str, Any]:
    validate_cast(data, world)
    if not data["approved"]:
        raise CanonError("cast_review_required")
    return {
        "schema": HANDOFF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(data),
        "world": world, "cast": data, "world_proof": prove(world).as_dict(),
        "continuity": "speaker_presence_and_earned_flags_proven",
        "review": "original_author_approved_not_release_qualified",
    }


_PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("cast-data").textContent);
const world = model.world;
const cast = model.cast;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const actors = new Map(cast.characters.map(a => [a.id, a]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
let scene = world.start;
let flags = new Set();
let trace = [];
const root = document.getElementById("play");
function node(tag, value) {
  const element = document.createElement(tag);
  element.textContent = value;
  return element;
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title));
  root.append(node("p", current.narrative));
  const lines = cast.lines.filter(line => line.scene === scene &&
    line.requires_flags.every(flag => flags.has(flag)))
    .sort((a,b) => a.order - b.order || a.id.localeCompare(b.id));
  for (const line of lines) {
    const speaker = actors.get(line.speaker);
    root.append(node("p", speaker.name + ": " + line.text));
  }
  root.append(node("p", "Choices: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = []; render();
    });
    root.append(restart);
    return;
  }
  for (const choice of world.choices.filter(c => c.from === scene &&
      c.requires.every(flag => flags.has(flag)))) {
    const button = node("button", choice.label);
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      trace.push(choice.id);
      scene = choice.to;
      render();
    });
    root.append(button);
  }
}
render();
""".strip()


def render_cast_html(data: Any, world: Any) -> bytes:
    manifest = compile_cast(data, world)
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    policy_hash = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode()
    title = html.escape(world["id"], quote=True)
    markup = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        f"script-src 'sha256-{policy_hash}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'\">"
        f"<title>{title} — authored cast</title></head><body>"
        "<main id='play' aria-live='polite'></main>"
        f"<script id='cast-data' type='application/json'>{embedded}</script>"
        f"<script>{_PLAYER_JS}</script></body></html>\n"
    )
    return markup.encode("utf-8")


class CastStore:
    """POSIX no-follow source custody and verified, exact-source playable output."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _source_name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".cast.json"

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".cast.playable.html",
                world_id + ".cast.manifest.json",
                world_id + ".cast.receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _cast(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_cast(
            strict_json(self.worlds._read(fd, self._source_name(world_id))), world)

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
            return self._cast(fd, world_id, world)
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None,
                create: bool = False) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world = self._world(fd, world_id)
                validate_cast(data, world)
                if data["world_id"] != world_id:
                    raise CanonError("identity_mismatch")
                try:
                    old = digest(self._cast(fd, world_id, world))
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("already_exists")
                elif old is None or old != expected_digest:
                    raise CanonError("stale_cast")
                self.worlds._write(fd, self._source_name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _artifacts(self, world: Any, data: Any) -> tuple[dict[str, Any], list[bytes]]:
        manifest = compile_cast(data, world)
        contents = [render_cast_html(data, world), canonical(manifest)]
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cast_digest": digest(data),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], contents)
            },
            "qualification": "operator_review_not_device_or_release_certified",
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
                data = self._cast(fd, world_id, world)
                if digest(data) != expected_digest:
                    raise CanonError("stale_cast")
                receipt, contents = self._artifacts(world, data)
                names = self._names(world_id)
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
                data = self._cast(fd, world_id, world)
                expected, contents = self._artifacts(world, data)
                names = self._names(world_id)
                receipt = strict_json(self.worlds._read(fd, names[2]))
                if receipt != expected:
                    raise CanonError("cast_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if _artifact_read(fd, name) != content:
                        raise CanonError("cast_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
