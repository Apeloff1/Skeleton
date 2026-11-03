"""Reviewed original NPC itineraries with bounded temporal presence proof.

An NPC can only speak where the authored cast permits, at a reachable tick
and with earned flags. Every appointment is independently witnessed before
compiling the same source into a network-disabled HTML5 playable.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import base64
import html
import os
from typing import Any

from .bundle import _artifact_read
from .cast import validate_cast
from .world_canon import (
    CanonError, WorldStore, _flags, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.npc_schedule.v1"
PROOF_SCHEMA = "jeeves.world.npc_schedule_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.npc_schedule_receipt.v1"
MAX_APPOINTMENTS = 128
MAX_TICK = 64
MAX_STATES = 8192


def validate_schedule(data: Any, world: Any, cast: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "cast_digest", "prompt",
        "appointments", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("npc_schedule_schema_mismatch")
    if obj["world_id"] != world["id"] or (
        obj["world_digest"] != digest(world)
    ) or obj["cast_digest"] != digest(cast):
        raise CanonError("npc_schedule_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("npc_schedule_invalid_approval")
    actors = {actor["id"]: actor for actor in cast["characters"]}
    scenes = {scene["id"] for scene in world["scenes"]}
    appointments = _list(obj["appointments"], "appointments", MAX_APPOINTMENTS)
    if not appointments:
        raise CanonError("npc_schedule_empty")
    seen: set[str] = set()
    occupied: dict[str, list[tuple[int, int]]] = {}
    for item in appointments:
        _keys(item, {
            "id", "actor", "scene", "first_tick", "last_tick",
            "label", "requires_flags",
        })
        aid = _id(item["id"], "appointment.id")
        actor = _id(item["actor"], "appointment.actor")
        scene = _id(item["scene"], "appointment.scene")
        if aid in seen:
            raise CanonError("npc_schedule_duplicate_appointment", aid)
        seen.add(aid)
        if actor not in actors:
            raise CanonError("npc_schedule_unknown_actor", aid)
        if scene not in scenes or scene not in actors[actor]["scenes"]:
            raise CanonError("npc_schedule_actor_absent", aid)
        first, last = item["first_tick"], item["last_tick"]
        if type(first) is not int or type(last) is not int or (
            not 0 <= first <= last <= MAX_TICK
        ):
            raise CanonError("npc_schedule_invalid_window", aid)
        for start, end in occupied.setdefault(actor, []):
            if first <= end and start <= last:
                raise CanonError("npc_schedule_double_booking", aid)
        occupied[actor].append((first, last))
        _text(item["label"], "appointment.label", 400)
        _flags(item["requires_flags"], "appointment.requires_flags")
    if [a["id"] for a in appointments] != sorted(seen):
        raise CanonError("npc_schedule_not_sorted")
    if len(canonical(obj)) > 524288:
        raise CanonError("npc_schedule_source_too_large")
    return obj


def prove_schedule(data: Any, world: Any, cast: Any) -> dict[str, Any]:
    validate_schedule(data, world, cast)
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for items in edges.values():
        items.sort(key=lambda item: item["id"])
    endings = {ending["scene"] for ending in world["endings"]}
    initial = (world["start"], frozenset(), 0)
    queue = deque([(initial, ())])
    seen = {initial}
    witnesses: dict[str, dict[str, Any]] = {}
    while queue:
        (scene, flags, tick), path = queue.popleft()
        for appointment in data["appointments"]:
            if appointment["id"] in witnesses:
                continue
            if appointment["scene"] == scene and (
                appointment["first_tick"] <= tick <= appointment["last_tick"]
            ) and set(appointment["requires_flags"]) <= flags:
                witnesses[appointment["id"]] = {
                    "scene": scene, "tick": tick, "choices": list(path),
                    "flags": sorted(flags),
                }
        if scene in endings or tick >= MAX_TICK:
            continue
        for choice in edges.get(scene, ()):
            if not set(choice["requires"]) <= flags:
                continue
            target = (
                choice["to"], flags | frozenset(choice["grants"]), tick + 1,
            )
            if target not in seen:
                seen.add(target)
                if len(seen) > MAX_STATES:
                    raise CanonError("npc_schedule_state_budget")
                queue.append((target, path + (choice["id"],)))
    missing = {item["id"] for item in data["appointments"]} - set(witnesses)
    if missing:
        raise CanonError("npc_schedule_unreachable_appointment",
                         ",".join(sorted(missing)))
    return {
        "schema": PROOF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(cast),
        "schedule_digest": digest(data), "states_explored": len(seen),
        "witnesses": {k: witnesses[k] for k in sorted(witnesses)},
        "qualification": "bounded_reachable_temporal_npc_presence",
    }


def propose_schedule(
    world: Any, cast: Any, *, prompt: str, actor: str,
    scene: str, first_tick: int, last_tick: int, label: str,
) -> dict[str, Any]:
    _text(prompt, "prompt", 4096)
    _id(actor, "actor")
    _id(scene, "scene")
    _text(label, "label", 400)
    proposal = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(cast),
        "prompt": prompt,
        "appointments": [{
            "id": "first_appointment", "actor": actor, "scene": scene,
            "first_tick": first_tick, "last_tick": last_tick,
            "label": label, "requires_flags": [],
        }],
        "approved": False, "review_note": "Original author review required.",
    }
    prove_schedule(proposal, world, cast)
    return proposal


def edit_schedule(data: Any, world: Any, cast: Any,
                  operation: Any) -> dict[str, Any]:
    validate_schedule(data, world, cast)
    op = _keys(operation, {"action", "value"})
    actions = (_list(op["value"], "batch", 64)
               if op["action"] == "batch" else [op])
    if not actions:
        raise CanonError("npc_schedule_empty_edit")
    updated = strict_json(canonical(data))
    for action in actions:
        item = _keys(action, {"action", "value"})
        kind, value = item["action"], item["value"]
        if kind in ("add", "replace"):
            _keys(value, {
                "id", "actor", "scene", "first_tick", "last_tick",
                "label", "requires_flags",
            })
            if kind == "add":
                updated["appointments"].append(value)
            else:
                matches = [i for i, old in enumerate(updated["appointments"])
                           if old["id"] == value["id"]]
                if len(matches) != 1:
                    raise CanonError("npc_schedule_unknown_appointment")
                updated["appointments"][matches[0]] = value
        elif kind == "remove":
            _keys(value, {"id"})
            before = len(updated["appointments"])
            updated["appointments"] = [
                old for old in updated["appointments"]
                if old["id"] != value["id"]
            ]
            if len(updated["appointments"]) != before - 1:
                raise CanonError("npc_schedule_unknown_appointment")
        else:
            raise CanonError("npc_schedule_unknown_edit")
    updated["appointments"].sort(key=lambda item: item["id"])
    updated["approved"] = False
    updated["review_note"] = "Edited schedule requires renewed review."
    prove_schedule(updated, world, cast)
    return updated


def approve_schedule(data: Any, world: Any, cast: Any,
                     note: str) -> dict[str, Any]:
    prove_schedule(data, world, cast)
    _text(note, "review_note", 512)
    if cast["approved"] is not True:
        raise CanonError("npc_schedule_cast_review_required")
    updated = strict_json(canonical(data))
    updated["approved"] = True
    updated["review_note"] = note
    prove_schedule(updated, world, cast)
    return updated


PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("schedule-data").textContent);
const world = model.world;
const cast = model.cast;
const schedule = model.schedule;
let scene = world.start;
let flags = new Set();
let tick = 0;
const root = document.getElementById("play");
function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}
function button(label, action) {
  const node = element("button", label);
  node.type = "button";
  node.addEventListener("click", action);
  root.append(node);
}
function reset() {
  scene = world.start;
  flags = new Set();
  tick = 0;
  render();
}
function render() {
  root.replaceChildren();
  const here = world.scenes.find(item => item.id === scene);
  root.append(element("h1", world.region + " — " + here.title));
  root.append(element("p", here.narrative));
  root.append(element("p", "Scene tick: " + tick));
  const present = schedule.appointments.filter(item =>
    item.scene === scene && item.first_tick <= tick &&
    tick <= item.last_tick &&
    item.requires_flags.every(flag => flags.has(flag))
  );
  for (const appointment of present) {
    const actor = cast.characters.find(item => item.id === appointment.actor);
    root.append(element("h2", actor.name + " — " + appointment.label));
    for (const line of cast.lines.filter(item =>
      item.scene === scene && item.speaker === actor.id &&
      item.requires_flags.every(flag => flags.has(flag)))) {
      root.append(element("p", line.text));
    }
  }
  const ending = world.endings.find(item => item.scene === scene);
  if (ending) {
    root.append(element("h2", "Ending: " + ending.label));
    button("Restart", reset);
    return;
  }
  if (tick >= 64) {
    root.append(element("p", "Bounded schedule session complete."));
    button("Restart", reset);
    return;
  }
  for (const choice of world.choices.filter(item =>
    item.from === scene &&
    item.requires.every(flag => flags.has(flag)))) {
    button(choice.label, () => {
      choice.grants.forEach(flag => flags.add(flag));
      scene = choice.to;
      tick += 1;
      render();
    });
  }
  button("Restart", reset);
}
render();
""".strip()


def render_schedule_html(data: Any, world: Any, cast: Any) -> bytes:
    if data["approved"] is not True:
        raise CanonError("npc_schedule_review_required")
    if cast["approved"] is not True:
        raise CanonError("npc_schedule_cast_review_required")
    proof = prove_schedule(data, world, cast)
    payload = canonical({
        "world": world, "cast": cast, "schedule": data, "proof": proof,
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(PLAYER_JS.encode()).digest()).decode()
    output = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Original NPC schedule: " + html.escape(world["id"]) +
        "</title></head><body><main id=\"play\" aria-live=\"polite\"></main>"
        '<script id="schedule-data" type="application/json">' + payload +
        "</script><script>" + PLAYER_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(output) > 1572864:
        raise CanonError("npc_schedule_playable_too_large")
    return output


class ScheduleStore:
    """Optimistic source custody under the canonical world exclusive lease."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".npc_schedule.json",
                world_id + ".npc_schedule.playable.html",
                world_id + ".npc_schedule.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("npc_schedule_world_identity_mismatch")
        cast = strict_json(self.worlds._read(fd, world_id + ".cast.json"))
        validate_cast(cast, world)
        return world, cast

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(
                world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd,
            )
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _read(self, fd: int, world_id: str, world: Any, cast: Any) -> Any:
        data = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_schedule(data, world, cast)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            data = self._read(fd, world_id, world, cast)
            return {"schedule": data, "proof": prove_schedule(data, world, cast)}
        finally:
            os.close(fd)

    def propose(self, world_id: str, **kwargs: Any) -> Any:
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            return propose_schedule(world, cast, **kwargs)
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None,
                create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                prove_schedule(data, world, cast)
                if data["approved"]:
                    raise CanonError("npc_schedule_approval_requires_review")
                try:
                    old = self._read(fd, world_id, world, cast)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("npc_schedule_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("npc_schedule_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_digest: str,
                review_note: str) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                if digest(data) != expected_digest:
                    raise CanonError("npc_schedule_stale_edit")
                approved = approve_schedule(data, world, cast, review_note)
                self.worlds._write(
                    fd, self._names(world_id)[0], canonical(approved),
                )
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, data: Any, world: Any,
                 cast: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_schedule(data, world, cast)
        html_bytes = render_schedule_html(data, world, cast)
        name = self._names(world["id"])[1]
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cast_digest": digest(cast),
            "schedule_digest": digest(data), "proof": proof,
            "artifacts": {name: sha256(html_bytes).hexdigest()},
            "qualification": "original_offline_npc_schedule_not_device_certified",
        }
        strict_json(canonical(receipt))
        return receipt, html_bytes

    def editor(self, world_id: str, expected_digest: str) -> dict[str, str]:
        """Publish a CSP-bound offline authoring UI under the source lease."""
        from .npc_schedule_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                if digest(data) != expected_digest:
                    raise CanonError("npc_schedule_stale_edit")
                content = render_editor(data, world, cast)
                name = world_id + ".npc_schedule.editor.html"
                self.worlds._write(fd, name, content)
                return {
                    "html_file": name, "html_sha256": sha256(content).hexdigest(),
                    "schedule_digest": digest(data),
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                if digest(data) != expected_digest:
                    raise CanonError("npc_schedule_stale_edit")
                receipt, playable = self._outputs(data, world, cast)
                names = self._names(world_id)
                self.worlds._write(fd, names[1], playable)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                receipt, playable = self._outputs(data, world, cast)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("npc_schedule_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("npc_schedule_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
