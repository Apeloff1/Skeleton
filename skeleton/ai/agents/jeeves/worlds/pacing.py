"""Source-bound original narrative pacing: phase order, climax witnesses and play."""
from __future__ import annotations

import base64
from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .session import SessionStore, replay_choices, validate_session
from .world_canon import CanonError, WorldStore, _id, _keys, _list, _text, canonical, digest, prove, strict_json

SCHEMA = "jeeves.world.pacing.v1"
PROOF_SCHEMA = "jeeves.world.pacing_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.pacing_receipt.v1"
PHASES = {"setup": 0, "rising": 1, "climax": 2, "resolution": 3}


def validate_pacing(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {"schema", "world_id", "world_digest", "prompt",
                         "approved", "review_note", "beats"})
    if obj["schema"] != SCHEMA:
        raise CanonError("pacing_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("pacing_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("pacing_invalid_approval")
    scenes = {item["id"] for item in world["scenes"]}
    beats = _list(obj["beats"], "beats", 128)
    ids = []
    for beat in beats:
        _keys(beat, {"scene", "phase", "intensity", "note"})
        sid = _id(beat["scene"], "beat.scene")
        if sid not in scenes:
            raise CanonError("pacing_unknown_scene")
        ids.append(sid)
        if type(beat["phase"]) is not str or beat["phase"] not in PHASES:
            raise CanonError("pacing_invalid_phase")
        level = beat["intensity"]
        if type(level) is not int or not 0 <= level <= 10:
            raise CanonError("pacing_invalid_intensity")
        if (beat["phase"] == "setup" and level > 4
                or beat["phase"] == "climax" and level < 7
                or beat["phase"] == "resolution" and level > 6):
            raise CanonError("pacing_phase_intensity_mismatch")
        _text(beat["note"], "beat.note", 2048)
    if ids != sorted(scenes):
        raise CanonError("pacing_scene_coverage")
    if len(canonical(obj)) > 524288:
        raise CanonError("pacing_too_large")
    return obj


def prove_pacing(source: Any, world: Any) -> dict[str, Any]:
    obj = validate_pacing(source, world)
    beats = {item["scene"]: item for item in obj["beats"]}
    if beats[world["start"]]["phase"] != "setup":
        raise CanonError("pacing_start_not_setup")
    endings = {item["scene"] for item in world["endings"]}
    if any(beats[scene]["phase"] != "resolution" for scene in endings):
        raise CanonError("pacing_ending_not_resolution")
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for group in edges.values():
        group.sort(key=lambda item: item["id"])
    initial = (world["start"], frozenset(), False)
    queue = deque([(initial, ())])
    visited = {initial}
    climax_witnesses: dict[str, list[str]] = {}
    ending_witnesses: dict[str, list[str]] = {}
    while queue:
        (scene, flags, saw_climax), trace = queue.popleft()
        phase = beats[scene]["phase"]
        saw_climax = saw_climax or phase == "climax"
        if phase == "climax":
            climax_witnesses.setdefault(scene, list(trace))
        if scene in endings:
            if not saw_climax:
                raise CanonError("pacing_ending_without_climax")
            ending_witnesses.setdefault(scene, list(trace))
            continue
        enabled = [choice for choice in edges.get(scene, ())
                   if set(choice["requires"]) <= flags]
        if not enabled:
            raise CanonError("pacing_reachable_dead_end")
        if len(trace) >= 128:
            raise CanonError("pacing_step_budget")
        for choice in enabled:
            target = choice["to"]
            if PHASES[beats[target]["phase"]] < PHASES[phase]:
                raise CanonError("pacing_phase_regression")
            state = (target, flags | frozenset(choice["grants"]), saw_climax)
            if state in visited:
                continue
            if len(visited) >= 4096:
                raise CanonError("pacing_state_budget")
            visited.add(state)
            queue.append((state, trace + (choice["id"],)))
    if endings - set(ending_witnesses):
        raise CanonError("pacing_unreachable_ending")
    return {"schema": PROOF_SCHEMA, "world_digest": digest(world),
            "pacing_digest": digest(obj), "states_explored": len(visited),
            "climax_witnesses": {k: climax_witnesses[k] for k in sorted(climax_witnesses)},
            "ending_witnesses": {k: ending_witnesses[k] for k in sorted(ending_witnesses)}}


def propose_pacing(world: Any, *, prompt: str, beats: Any) -> dict[str, Any]:
    obj = {"schema": SCHEMA, "world_id": world["id"],
           "world_digest": digest(world), "prompt": prompt,
           "approved": False, "review_note": "Narrative pacing requires author review",
           "beats": beats}
    prove_pacing(obj, world)
    return obj


def edit_pacing(source: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_pacing(source, world)
    op = _keys(operation, {"action", "value"})
    if op["action"] != "replace_beat":
        raise CanonError("pacing_unsupported_edit")
    value = _keys(op["value"], {"scene", "phase", "intensity", "note"})
    candidate = strict_json(canonical(source))
    matches = [i for i, item in enumerate(candidate["beats"])
               if item["scene"] == value["scene"]]
    if len(matches) != 1:
        raise CanonError("pacing_unknown_edit")
    candidate["beats"][matches[0]] = value
    candidate["approved"] = False
    candidate["review_note"] = "Edited pacing requires renewed author review"
    prove_pacing(candidate, world)
    return candidate


def replay_pacing(source: Any, world: Any, choices: Any) -> dict[str, Any]:
    validate_pacing(source, world)
    replay = replay_choices(world, choices)
    beats = {item["scene"]: item for item in source["beats"]}
    steps = [{"scene": step["scene"], "choice": step["choice"],
              "beat": beats[step["scene"]]} for step in replay["steps"]]
    return {"world_digest": digest(world), "pacing_digest": digest(source),
            "scene": replay["scene"], "ending": replay["ending"],
            "steps": steps}


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("pacing-data").textContent);
const world = data.world, beats = new Map(data.pacing.beats.map(b => [b.scene, b]));
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const root = document.getElementById("play");
let scene = world.start, flags = new Set(), trace = [];
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
function render() {
  root.replaceChildren();
  const current = scenes.get(scene), beat = beats.get(scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  root.append(node("p", "Narrative phase: " + beat.phase + "; intensity: " + beat.intensity));
  root.append(node("p", beat.note));
  root.append(node("p", "Choices: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = []; render();
    });
    root.append(restart); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(flag => flags.has(flag))) continue;
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


def render_pacing_html(source: Any, world: Any) -> bytes:
    prove_pacing(source, world)
    if not source["approved"]:
        raise CanonError("pacing_review_required")
    payload = canonical({"world": world, "pacing": source}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + title + ' narrative pacing</title></head><body>'
            '<main id="play" aria-live="polite"></main>'
            '<script id="pacing-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("pacing_playable_too_large")
    return page


class PacingStore:
    """World-locked original pacing custody with explicit review and byte receipts."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".pacing.json",
                world_id + ".pacing.playable.html",
                world_id + ".pacing.receipt.json")

    def _world(self, fd: int, world_id: str) -> Any:
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _read(self, fd: int, world_id: str, world: Any) -> Any:
        return validate_pacing(
            strict_json(self.worlds._read(fd, self._names(world_id)[0])), world)

    def _locked(self, fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def propose(self, world_id: str, *, prompt: str, beats: Any) -> Any:
        fd = self.worlds._directory()
        try:
            return propose_pacing(self._world(fd, world_id), prompt=prompt, beats=beats)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            source = self._read(fd, world_id, world)
            return {"pacing": source, "proof": prove_pacing(source, world)}
        finally:
            os.close(fd)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                candidate = strict_json(canonical(source))
                if type(candidate) is not dict:
                    raise CanonError("expected_object")
                candidate["approved"] = False
                candidate["review_note"] = "Published pacing requires author review"
                prove_pacing(candidate, world)
                try:
                    old = self._read(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("pacing_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("pacing_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(candidate))
                return digest(candidate)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, *, expected_digest: str, review_note: str) -> str:
        _text(review_note, "review_note", 512)
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("pacing_stale_edit")
                source["approved"] = True
                source["review_note"] = review_note
                prove_pacing(source, world)
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
            source = self._read(fd, world_id, world)
            if not source["approved"]:
                raise CanonError("pacing_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
            return {"slot": slot, "session_digest": digest(session),
                    "revision": session["revision"],
                    "player": replay_pacing(source, world, session["choices"])}
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_pacing(source, world)
        playable = render_pacing_html(source, world)
        receipt = {"schema": RECEIPT_SCHEMA, "world_id": world["id"],
                   "world_digest": digest(world),
                   "pacing_digest": digest(source), "proof_digest": digest(proof),
                   "html_file": self._names(world["id"])[1],
                   "html_sha256": sha256(playable).hexdigest(),
                   "qualification": "reviewed_original_pacing_not_release_certified"}
        return receipt, playable

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("pacing_stale_edit")
                receipt, playable = self._outputs(source, world)
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
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                receipt, playable = self._outputs(source, world)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("pacing_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("pacing_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .pacing_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("pacing_stale_edit")
                page = render_editor(source, world)
                name = world_id + ".pacing.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "pacing_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
