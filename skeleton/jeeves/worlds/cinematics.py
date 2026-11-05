"""Reviewed cinematic storyboards bound to actual scene choices and player replay.

No media URLs, code, arbitrary timers, or generated asset binaries are admitted.
All captions are authored text. The browser player advances only on explicit
button/keyboard activation, preserving accessibility and deterministic replay.
"""
from __future__ import annotations

import base64
from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .session import SessionStore, replay_choices, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical, digest,
    prove, strict_json,
)

SCHEMA = "jeeves.world.cinematics.v1"
PROOF_SCHEMA = "jeeves.world.cinematics_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.cinematics_receipt.v1"
ENGINE_SCHEMA = "jeeves.world.cinematics_engine.v1"
CUES = frozenset({"arrival", "action", "reaction", "departure"})
MAX_SEQUENCES = 64
MAX_BEATS = 8
MAX_TOTAL_BEATS = 128
MAX_TOTAL_DURATION = 60000


def validate_cinematics(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {"schema", "world_id", "world_digest", "prompt",
                         "approved", "review_note", "sequences"})
    if obj["schema"] != SCHEMA:
        raise CanonError("cinematics_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("cinematics_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("cinematics_invalid_approval")
    scenes = {s["id"] for s in world["scenes"]}
    sequences = _list(obj["sequences"], "sequences", MAX_SEQUENCES)
    if not sequences:
        raise CanonError("cinematics_empty")
    seen: set[str] = set()
    total_beats = 0
    for sequence in sequences:
        _keys(sequence, {"scene", "beats"})
        scene = _id(sequence["scene"], "sequence.scene")
        if scene not in scenes:
            raise CanonError("cinematics_unknown_scene", scene)
        if scene in seen:
            raise CanonError("cinematics_duplicate_scene", scene)
        seen.add(scene)
        beats = _list(sequence["beats"], "beats", MAX_BEATS)
        if not beats:
            raise CanonError("cinematics_empty_sequence", scene)
        ids: set[str] = set()
        duration = 0
        for beat in beats:
            _keys(beat, {"id", "cue", "caption", "duration_ms"})
            bid = _id(beat["id"], "beat.id")
            if bid in ids:
                raise CanonError("cinematics_duplicate_beat", bid)
            ids.add(bid)
            if type(beat["cue"]) is not str or beat["cue"] not in CUES:
                raise CanonError("cinematics_invalid_cue", bid)
            _text(beat["caption"], "beat.caption", 2048)
            ms = beat["duration_ms"]
            if type(ms) is not int or not 500 <= ms <= 15000:
                raise CanonError("cinematics_invalid_duration", bid)
            duration += ms
        if duration > MAX_TOTAL_DURATION:
            raise CanonError("cinematics_sequence_duration_budget", scene)
        total_beats += len(beats)
    if total_beats > MAX_TOTAL_BEATS:
        raise CanonError("cinematics_total_beat_budget")
    if [s["scene"] for s in sequences] != sorted(seen):
        raise CanonError("cinematics_noncanonical_scene_order")
    if len(canonical(obj)) > 524288:
        raise CanonError("cinematics_too_large")
    return obj


def prove_cinematics(source: Any, world: Any) -> dict[str, Any]:
    obj = validate_cinematics(source, world)
    target = {s["scene"] for s in obj["sequences"]}
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for values in edges.values():
        values.sort(key=lambda e: e["id"])
    initial = (world["start"], frozenset())
    queue = deque([(initial, ())])
    visited = {initial}
    witnesses: dict[str, list[str]] = {}
    while queue and target - witnesses.keys():
        (scene, flags), path = queue.popleft()
        if scene in target:
            witnesses.setdefault(scene, list(path))
        for edge in edges.get(scene, []):
            if not set(edge["requires"]) <= flags:
                continue
            state = (edge["to"], flags | frozenset(edge["grants"]))
            if state in visited:
                continue
            if len(visited) >= 2048:
                raise CanonError("cinematics_state_budget")
            visited.add(state)
            queue.append((state, path + (edge["id"],)))
    if target - witnesses.keys():
        raise CanonError("cinematics_unreachable_sequence")
    return {
        "schema": PROOF_SCHEMA, "world_digest": digest(world),
        "cinematics_digest": digest(obj), "states_explored": len(visited),
        "entry_witnesses": {k: witnesses[k] for k in sorted(witnesses)},
        "duration_ms": {s["scene"]: sum(b["duration_ms"] for b in s["beats"])
                        for s in obj["sequences"]},
    }


def propose_cinematics(world: Any, *, prompt: str,
                       sequences: Any) -> dict[str, Any]:
    obj = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "prompt": prompt,
        "approved": False,
        "review_note": "Cinematic storyboard requires author review",
        "sequences": sequences,
    }
    prove_cinematics(obj, world)
    return obj


def edit_cinematics(source: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_cinematics(source, world)
    op = _keys(operation, {"action", "value"})
    operations = (_list(op["value"], "batch", 32) if op["action"] == "batch"
                  else [op])
    if not operations:
        raise CanonError("cinematics_empty_edit")
    candidate = strict_json(canonical(source))
    for item in operations:
        edit = _keys(item, {"action", "value"})
        action = edit["action"]
        value = edit["value"]
        if action in {"add_sequence", "replace_sequence"}:
            _keys(value, {"scene", "beats"})
            _id(value["scene"], "sequence.scene")
            matches = [i for i, s in enumerate(candidate["sequences"])
                       if s["scene"] == value["scene"]]
            if action == "add_sequence":
                if matches:
                    raise CanonError("cinematics_duplicate_scene")
                candidate["sequences"].append(value)
            else:
                if len(matches) != 1:
                    raise CanonError("cinematics_unknown_edit_target")
                candidate["sequences"][matches[0]] = value
        elif action == "remove_sequence":
            _keys(value, {"scene"})
            _id(value["scene"], "sequence.scene")
            before = len(candidate["sequences"])
            candidate["sequences"] = [s for s in candidate["sequences"]
                                      if s["scene"] != value["scene"]]
            if len(candidate["sequences"]) != before - 1:
                raise CanonError("cinematics_unknown_edit_target")
        else:
            raise CanonError("cinematics_unsupported_edit")
    candidate["sequences"].sort(key=lambda s: s["scene"])
    candidate["approved"] = False
    candidate["review_note"] = "Edited storyboard requires renewed author review"
    prove_cinematics(candidate, world)
    return candidate


def replay_cinematics(source: Any, world: Any, choices: Any) -> dict[str, Any]:
    validate_cinematics(source, world)
    replay = replay_choices(world, choices)
    sequences = {s["scene"]: s["beats"] for s in source["sequences"]}
    visits = [{"scene": step["scene"], "choice": step["choice"],
               "beats": sequences[step["scene"]]}
              for step in replay["steps"] if step["scene"] in sequences]
    return {
        "schema": "jeeves.world.cinematics_replay.v1",
        "world_digest": digest(world), "cinematics_digest": digest(source),
        "scene": replay["scene"], "ending": replay["ending"],
        "visits": visits,
    }


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("cinematics-data").textContent);
const world = data.world, sequences = new Map(data.cinematics.sequences.map(s => [s.scene, s.beats]));
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const root = document.getElementById("play");
let scene, flags, trace, beatIndex;
function node(tag, text) { const n = document.createElement(tag); n.textContent = text; return n; }
function button(text, fn) {
  const n = node("button", text); n.type = "button"; n.addEventListener("click", fn);
  root.append(n); return n;
}
function reset() { scene = world.start; flags = new Set(); trace = []; beatIndex = 0; render(); }
function advance(choice) {
  for (const flag of choice.grants) flags.add(flag);
  trace.push(choice.id); scene = choice.to; beatIndex = 0; render();
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  const beats = sequences.get(scene) || [];
  if (beatIndex < beats.length) {
    const beat = beats[beatIndex];
    root.append(node("h2", "Storyboard: " + beat.cue),
                node("p", beat.caption),
                node("p", "Beat " + (beatIndex + 1) + " of " + beats.length));
    const next = button(beatIndex + 1 === beats.length ? "Finish scene" : "Continue", () => {
      beatIndex += 1; render();
    });
    next.focus(); return;
  }
  root.append(node("p", "Choices taken: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    button("Restart", reset); return;
  }
  const options = world.choices.filter(c => c.from === scene &&
    c.requires.every(flag => flags.has(flag)));
  for (const choice of options) button(choice.label, () => advance(choice));
}
reset();
""".strip()


def render_cinematics_html(source: Any, world: Any) -> bytes:
    prove_cinematics(source, world)
    if not source["approved"]:
        raise CanonError("cinematics_review_required")
    payload = canonical({"world": world, "cinematics": source}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' storyboard</title></head>'
            '<body><main id="play" aria-live="polite"></main>'
            '<script id="cinematics-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("cinematics_playable_too_large")
    return page


def engine_handoff(source: Any, world: Any) -> dict[str, Any]:
    proof = prove_cinematics(source, world)
    if not source["approved"]:
        raise CanonError("cinematics_review_required")
    return {
        "schema": ENGINE_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cinematics_digest": digest(source),
        "sequences": source["sequences"],
        "entry_witnesses": proof["entry_witnesses"],
        "timing_policy": "authored_hint_only_explicit_user_advance",
        "assets": [], "external_media": False,
        "qualification": "reviewed_original_storyboard_not_device_certified",
    }


class CinematicsStore:
    """One world-wide O_EXCL lease protects review, publication and compilation."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".cinematics.json",
                world_id + ".cinematics.playable.html",
                world_id + ".cinematics.engine.json",
                world_id + ".cinematics.receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _source(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_cinematics(
            strict_json(self.worlds._read(fd, self._names(world_id)[0])), world)

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def propose(self, world_id: str, *, prompt: str,
                sequences: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            return propose_cinematics(self._world(fd, world_id),
                                      prompt=prompt, sequences=sequences)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            source = self._source(fd, world_id, world)
            return {"cinematics": source, "proof": prove_cinematics(source, world)}
        finally:
            os.close(fd)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                candidate = strict_json(canonical(source))
                candidate["approved"] = False
                candidate["review_note"] = "Published storyboard requires author review"
                prove_cinematics(candidate, world)
                try:
                    existing = self._source(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    existing = None
                if create:
                    if existing is not None or expected_digest is not None:
                        raise CanonError("cinematics_already_exists")
                elif existing is None or digest(existing) != expected_digest:
                    raise CanonError("cinematics_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(candidate))
                return digest(candidate)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, expected_digest: str, note: str) -> str:
        _text(note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("cinematics_stale_edit")
                source["approved"] = True
                source["review_note"] = note
                prove_cinematics(source, world)
                self.worlds._write(fd, self._names(world_id)[0], canonical(source))
                return digest(source)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            source = self._source(fd, world_id, world)
            if not source["approved"]:
                raise CanonError("cinematics_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
            return {
                "slot": slot, "session_digest": digest(session),
                "revision": session["revision"],
                "player": replay_cinematics(source, world, session["choices"]),
            }
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any) -> tuple[dict[str, Any], bytes, bytes]:
        proof = prove_cinematics(source, world)
        playable = render_cinematics_html(source, world)
        engine = canonical(engine_handoff(source, world))
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cinematics_digest": digest(source),
            "proof_digest": digest(proof),
            "artifacts": {names[1]: sha256(playable).hexdigest(),
                          names[2]: sha256(engine).hexdigest()},
            "qualification": "reviewed_source_not_release_certified",
        }
        return receipt, playable, engine

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("cinematics_stale_edit")
                receipt, playable, engine = self._outputs(source, world)
                names = self._names(world_id)
                self.worlds._write(fd, names[1], playable)
                self.worlds._write(fd, names[2], engine)
                self.worlds._write(fd, names[3], canonical(receipt))
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
                source = self._source(fd, world_id, world)
                receipt, playable, engine = self._outputs(source, world)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[3])) != receipt:
                    raise CanonError("cinematics_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable or _artifact_read(fd, names[2]) != engine:
                    raise CanonError("cinematics_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .cinematics_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("cinematics_stale_edit")
                page = render_editor(source, world)
                name = world_id + ".cinematics.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "cinematics_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
