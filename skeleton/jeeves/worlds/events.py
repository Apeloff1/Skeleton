"""Reviewed deterministic world events with source-leased HTML5 handoff.

Events are original, one-shot scene effects. They execute in stable ID order,
cannot execute code, and only grant bounded canonical world-state flags.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import base64
import html
import os
from typing import Any

from .bundle import _artifact_read
from .world_canon import (
    CanonError, WorldStore, _flags, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.events.v1"
PROOF_SCHEMA = "jeeves.world.events_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.events_receipt.v1"
MAX_EVENTS = 16
MAX_STATES = 8192


def validate_events(data: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "prompt",
        "approved", "review_note", "events",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("events_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("events_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("events_invalid_approval")
    events = _list(obj["events"], "events", MAX_EVENTS)
    if not events:
        raise CanonError("events_empty")
    scene_ids = {scene["id"] for scene in world["scenes"]}
    ids = []
    for event in events:
        _keys(event, {"id", "scene", "description", "requires", "grants"})
        eid = _id(event["id"], "event.id")
        if _id(event["scene"], "event.scene") not in scene_ids:
            raise CanonError("events_unknown_scene", eid)
        _text(event["description"], "event.description", 2048)
        _flags(event["requires"], "event.requires")
        _flags(event["grants"], "event.grants")
        if not event["grants"]:
            raise CanonError("events_no_effect", eid)
        ids.append(eid)
    if ids != sorted(set(ids)):
        raise CanonError("events_ids_not_canonical")
    if len(canonical(obj)) > 524288:
        raise CanonError("events_source_too_large")
    return obj


def _enter(scene: str, flags: frozenset[str], fired: frozenset[str],
           events: list[dict[str, Any]]) -> tuple[frozenset[str], frozenset[str], tuple[str, ...]]:
    triggered = []
    # A bounded fixed point: an event can enable a later or earlier event.
    for _ in range(len(events)):
        changed = False
        for event in events:
            if event["scene"] != scene or event["id"] in fired:
                continue
            if set(event["requires"]) <= flags:
                fired = fired | {event["id"]}
                flags = flags | frozenset(event["grants"])
                triggered.append("event:" + event["id"])
                changed = True
        if not changed:
            break
    return flags, fired, tuple(triggered)


def prove_events(data: Any, world: Any) -> dict[str, Any]:
    obj = validate_events(data, world)
    events = obj["events"]
    endings = {ending["scene"] for ending in world["endings"]}
    edges = {}
    for edge in world["choices"]:
        edges.setdefault(edge["from"], []).append(edge)
    for group in edges.values():
        group.sort(key=lambda e: e["id"])
    flags, fired, fired_trace = _enter(world["start"], frozenset(), frozenset(), events)
    initial = (world["start"], flags, fired)
    queue = deque([(initial, fired_trace)])
    seen = {initial}
    event_witnesses = {e[6:]: list(fired_trace[:i + 1])
                       for i, e in enumerate(fired_trace)}
    ending_witnesses = {}
    while queue:
        (scene, flags, fired), path = queue.popleft()
        if scene in endings:
            ending_witnesses.setdefault(scene, list(path))
            continue
        enabled = [e for e in edges.get(scene, ()) if set(e["requires"]) <= flags]
        if not enabled:
            raise CanonError("events_reachable_dead_end", scene)
        for edge in enabled:
            new_flags = flags | frozenset(edge["grants"])
            new_flags, new_fired, actions = _enter(edge["to"], new_flags, fired, events)
            new_path = path + (edge["id"],) + actions
            for index, action in enumerate(actions):
                event_witnesses.setdefault(action[6:], list(path + (edge["id"],) + actions[:index + 1]))
            state = (edge["to"], new_flags, new_fired)
            if state not in seen:
                seen.add(state)
                if len(seen) > MAX_STATES:
                    raise CanonError("events_state_budget")
                queue.append((state, new_path))
    if endings - set(ending_witnesses):
        raise CanonError("events_unreachable_endings")
    if {e["id"] for e in events} - set(event_witnesses):
        raise CanonError("events_unreachable_events")
    return {
        "schema": PROOF_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "events_digest": digest(obj),
        "states_explored": len(seen),
        "event_witnesses": {k: event_witnesses[k] for k in sorted(event_witnesses)},
        "ending_witnesses": {k: ending_witnesses[k] for k in sorted(ending_witnesses)},
        "qualification": "bounded_deterministic_scene_effects",
    }


def propose_events(world: Any, *, prompt: str, event_id: str, scene: str,
                   description: str, requires: list[str],
                   grants: list[str]) -> dict[str, Any]:
    obj = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "prompt": prompt,
        "approved": False, "review_note": "Original-author review required",
        "events": [{
            "id": event_id, "scene": scene, "description": description,
            "requires": requires, "grants": grants,
        }],
    }
    prove_events(obj, world)
    return obj


def edit_events(data: Any, world: Any, operation: Any) -> dict[str, Any]:
    obj = validate_events(data, world)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(obj))
    value = op["value"]
    if op["action"] == "add":
        _keys(value, {"id", "scene", "description", "requires", "grants"})
        candidate["events"].append(value)
        candidate["events"].sort(key=lambda e: e["id"])
    elif op["action"] == "replace":
        _keys(value, {"id", "scene", "description", "requires", "grants"})
        matches = [i for i, e in enumerate(candidate["events"]) if e["id"] == value["id"]]
        if len(matches) != 1:
            raise CanonError("events_unknown_edit")
        candidate["events"][matches[0]] = value
    elif op["action"] == "remove":
        _keys(value, {"id"})
        original = len(candidate["events"])
        candidate["events"] = [e for e in candidate["events"] if e["id"] != value["id"]]
        if len(candidate["events"]) == original:
            raise CanonError("events_unknown_edit")
    else:
        raise CanonError("events_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Review required after event edit"
    prove_events(candidate, world)
    return candidate


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("event-data").textContent);
const world = data.world, events = data.events.events;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const root = document.getElementById("play");
let scene = world.start, flags = new Set(), fired = new Set(), trace = [];
function node(tag, value) {
  const el = document.createElement(tag); el.textContent = value; return el;
}
function enter() {
  for (let iteration = 0; iteration < events.length; iteration++) {
    let changed = false;
    for (const event of events) {
      if (event.scene !== scene || fired.has(event.id)) continue;
      if (!event.requires.every(f => flags.has(f))) continue;
      fired.add(event.id);
      for (const flag of event.grants) flags.add(flag);
      trace.push("event:" + event.id);
      changed = true;
    }
    if (!changed) break;
  }
}
function render() {
  enter();
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  for (const event of events.filter(e => fired.has(e.id) && e.scene === scene)) {
    root.append(node("p", "World event: " + event.description));
  }
  root.append(node("p", "Trace: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); fired = new Set(); trace = []; render();
    });
    root.append(restart); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(f => flags.has(f))) continue;
    const button = node("button", choice.label);
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
}
render();
""".strip()


def compile_events_html(data: Any, world: Any) -> bytes:
    prove_events(data, world)
    if not data["approved"]:
        raise CanonError("events_review_required")
    payload = canonical({"world": world, "events": data}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + policy + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' world events</title></head><body>'
        '<main id="play" aria-live="polite"></main>'
        '<script id="event-data" type="application/json">' + payload + '</script>'
        '<script>' + _PLAYER_JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 1048576:
        raise CanonError("events_playable_too_large")
    return page


class EventStore:
    def __init__(self, root: str) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".events.json", world_id + ".events.playable.html",
                world_id + ".events.receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _read(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        obj = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_events(obj, world)

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        return propose_events(self.worlds.read(world_id), **kwargs)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            obj = self._read(fd, world_id, world)
            return {"events": obj, "proof": prove_events(obj, world)}
        finally:
            os.close(fd)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                candidate = strict_json(canonical(data))
                if type(candidate) is not dict:
                    raise CanonError("expected_object")
                candidate["approved"] = False
                candidate["review_note"] = "Review required after source publication"
                prove_events(candidate, world)
                name = self._names(world_id)[0]
                try:
                    existing = self._read(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    existing = None
                if create:
                    if existing is not None or expected_digest is not None:
                        raise CanonError("events_already_exists")
                elif existing is None or digest(existing) != expected_digest:
                    raise CanonError("events_stale_edit")
                self.worlds._write(fd, name, canonical(candidate))
                return digest(candidate)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_digest: str, review_note: str) -> str:
        _text(review_note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                obj = self._read(fd, world_id, world)
                if digest(obj) != expected_digest:
                    raise CanonError("events_stale_edit")
                obj["approved"] = True
                obj["review_note"] = review_note
                prove_events(obj, world)
                self.worlds._write(fd, self._names(world_id)[0], canonical(obj))
                return digest(obj)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, obj: Any, world: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_events(obj, world)
        playable = compile_events_html(obj, world)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "events_digest": digest(obj),
            "proof_digest": digest(proof), "html_sha256": sha256(playable).hexdigest(),
            "html_file": self._names(world["id"])[1],
            "qualification": "reviewed_deterministic_scene_events",
        }
        return receipt, playable


    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .events_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                obj = self._read(fd, world_id, world)
                if digest(obj) != expected_digest:
                    raise CanonError("events_stale_edit")
                content = render_editor(obj, world)
                name = world_id + ".events.editor.html"
                self.worlds._write(fd, name, content)
                return {
                    "html_file": name, "html_sha256": sha256(content).hexdigest(),
                    "events_digest": digest(obj),
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
                world = self._world(fd, world_id)
                obj = self._read(fd, world_id, world)
                if digest(obj) != expected_digest:
                    raise CanonError("events_stale_edit")
                receipt, playable = self._outputs(obj, world)
                _, html_name, receipt_name = self._names(world_id)
                self.worlds._write(fd, html_name, playable)
                self.worlds._write(fd, receipt_name, canonical(receipt))
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
                world = self._world(fd, world_id)
                obj = self._read(fd, world_id, world)
                receipt, playable = self._outputs(obj, world)
                _, html_name, receipt_name = self._names(world_id)
                if strict_json(self.worlds._read(fd, receipt_name)) != receipt:
                    raise CanonError("events_receipt_mismatch")
                if _artifact_read(fd, html_name) != playable:
                    raise CanonError("events_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
