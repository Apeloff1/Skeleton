"""Reviewed character transformations across earned world choices and endings.

The arc plane is original authored narrative state, not generated filler. All
reachable ending paths must close every authored arc, or compilation refuses.
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
from .session import SessionStore, validate_session, replay_choices
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.character_arcs.v1"
RECEIPT_SCHEMA = "jeeves.world.character_arcs_receipt.v1"
MAX_ARCS = 32
MAX_BEATS = 128
MAX_STATES = 4096
STAGES = frozenset({"turn", "resolution"})


def validate_arcs(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    data = _keys(source, {
        "schema", "world_id", "world_digest", "cast_digest", "prompt",
        "arcs", "approved", "review_note",
    })
    if data["schema"] != SCHEMA:
        raise CanonError("arcs_schema_mismatch")
    if (data["world_id"] != world["id"] or
            data["world_digest"] != digest(world) or
            data["cast_digest"] != digest(cast)):
        raise CanonError("arcs_source_lease_mismatch")
    _text(data["prompt"], "prompt", 4096)
    if type(data["approved"]) is not bool:
        raise CanonError("arcs_invalid_approval")
    if data["approved"]:
        _text(data["review_note"], "review_note")
    elif data["review_note"] != "":
        raise CanonError("arcs_unreviewed_note")
    actors = {a["id"]: a for a in cast["characters"]}
    choices = {c["id"]: c for c in world["choices"]}
    arcs = _list(data["arcs"], "arcs", MAX_ARCS)
    if not arcs:
        raise CanonError("arcs_empty")
    seen_actors: set[str] = set()
    seen_beats: set[str] = set()
    for arc in arcs:
        _keys(arc, {"actor", "desire", "starting_belief",
                    "resolved_belief", "beats"})
        actor = _id(arc["actor"], "arc.actor")
        if actor not in actors or actor in seen_actors:
            raise CanonError("arcs_invalid_actor", actor)
        seen_actors.add(actor)
        for key in ("desire", "starting_belief", "resolved_belief"):
            _text(arc[key], key, 1000)
        beats = _list(arc["beats"], "beats", MAX_BEATS)
        if not beats or not any(
                type(b) is dict and b.get("stage") == "resolution" for b in beats):
            raise CanonError("arcs_missing_resolution", actor)
        for beat in beats:
            _keys(beat, {"id", "choice", "stage", "text"})
            bid = _id(beat["id"], "beat.id")
            cid = _id(beat["choice"], "beat.choice")
            if bid in seen_beats:
                raise CanonError("arcs_duplicate_beat", bid)
            seen_beats.add(bid)
            if cid not in choices:
                raise CanonError("arcs_unknown_choice", cid)
            if (choices[cid]["from"] not in actors[actor]["scenes"] and
                    choices[cid]["to"] not in actors[actor]["scenes"]):
                raise CanonError("arcs_actor_absent", actor)
            if type(beat["stage"]) is not str or beat["stage"] not in STAGES:
                raise CanonError("arcs_invalid_stage", bid)
            _text(beat["text"], "beat.text", 4096)
        if beats != sorted(beats, key=lambda b: b["id"]):
            raise CanonError("arcs_beat_order", actor)
    if arcs != sorted(arcs, key=lambda a: a["actor"]):
        raise CanonError("arcs_actor_order")
    if len(canonical(data)) > 524288:
        raise CanonError("arcs_source_too_large")
    return data


def prove_arcs(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    data = validate_arcs(source, world, cast)
    beats_by_choice: dict[str, list[tuple[str, Any]]] = {}
    all_beats = set()
    for arc in data["arcs"]:
        for beat in arc["beats"]:
            beats_by_choice.setdefault(beat["choice"], []).append((arc["actor"], beat))
            all_beats.add(beat["id"])
    edges: dict[str, list[Any]] = {}
    for edge in world["choices"]:
        edges.setdefault(edge["from"], []).append(edge)
    for value in edges.values():
        value.sort(key=lambda e: e["id"])
    endings = {e["scene"] for e in world["endings"]}
    actors = {arc["actor"] for arc in data["arcs"]}
    start = (world["start"], frozenset(), frozenset())
    queue = deque([(start, ())])
    seen = {start}
    ending_witnesses: dict[str, list[str]] = {}
    exercised: set[str] = set()
    while queue:
        (scene, flags, resolved), path = queue.popleft()
        if scene in endings:
            if resolved != actors:
                raise CanonError("arcs_unclosed_ending", scene)
            ending_witnesses.setdefault(scene, list(path))
            continue
        enabled = 0
        for edge in edges.get(scene, []):
            if not set(edge["requires"]) <= flags:
                continue
            enabled += 1
            triggered = beats_by_choice.get(edge["id"], [])
            exercised.update(beat["id"] for _, beat in triggered)
            next_resolved = resolved | frozenset(
                actor for actor, beat in triggered if beat["stage"] == "resolution")
            state = (edge["to"], flags | frozenset(edge["grants"]), next_resolved)
            if state not in seen:
                seen.add(state)
                if len(seen) > MAX_STATES:
                    raise CanonError("arcs_state_budget_exhausted")
                queue.append((state, path + (edge["id"],)))
        if not enabled:
            raise CanonError("arcs_reachable_dead_end", scene)
    if set(ending_witnesses) != endings:
        raise CanonError("arcs_unreachable_endings")
    if exercised != all_beats:
        raise CanonError("arcs_unreachable_beats")
    return {
        "schema": "jeeves.world.character_arcs_proof.v1",
        "world_digest": digest(world), "cast_digest": digest(cast),
        "arcs_digest": digest(data), "states_explored": len(seen),
        "ending_witnesses": {
            key: ending_witnesses[key] for key in sorted(ending_witnesses)},
        "exercised_beats": sorted(exercised),
    }


def replay_arcs(source: Any, world: Any, cast: Any, choices: Any) -> dict[str, Any]:
    validate_arcs(source, world, cast)
    replay = replay_choices(world, choices)
    by_choice: dict[str, list[tuple[str, Any]]] = {}
    for arc in source["arcs"]:
        for beat in arc["beats"]:
            by_choice.setdefault(beat["choice"], []).append((arc["actor"], beat))
    beliefs = {arc["actor"]: arc["starting_belief"] for arc in source["arcs"]}
    completed: set[str] = set()
    triggered = []
    for choice in choices:
        for actor, beat in sorted(by_choice.get(choice, []), key=lambda p: p[1]["id"]):
            triggered.append({
                "actor": actor, "beat": beat["id"],
                "stage": beat["stage"], "text": beat["text"],
            })
            if beat["stage"] == "resolution":
                beliefs[actor] = next(
                    arc["resolved_belief"] for arc in source["arcs"]
                    if arc["actor"] == actor)
                completed.add(actor)
    if replay["ending"] is not None and completed != set(beliefs):
        raise CanonError("arcs_unclosed_ending")
    return {
        "schema": "jeeves.world.character_arcs_replay.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "cast_digest": digest(cast), "arcs_digest": digest(source),
        "scene": replay["scene"], "ending": replay["ending"],
        "beliefs": beliefs, "completed": sorted(completed),
        "triggered": triggered, "choices": list(choices),
    }


def propose_arcs(world: Any, cast: Any, *, prompt: str, actor: str,
                 desire: str, starting_belief: str, resolved_belief: str,
                 choice: str, text: str) -> dict[str, Any]:
    _text(prompt, "prompt", 4096)
    source = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(cast),
        "prompt": prompt,
        "arcs": [{
            "actor": actor, "desire": desire,
            "starting_belief": starting_belief,
            "resolved_belief": resolved_belief,
            "beats": [{
                "id": "resolution", "choice": choice,
                "stage": "resolution", "text": text,
            }],
        }],
        "approved": False, "review_note": "",
    }
    prove_arcs(source, world, cast)
    return source


def edit_arcs(source: Any, world: Any, cast: Any, operation: Any) -> dict[str, Any]:
    validate_arcs(source, world, cast)
    candidate = strict_json(canonical(source))
    op = _keys(operation, {"action", "value"})
    action, value = op["action"], op["value"]
    if action in {"add_arc", "replace_arc"}:
        _keys(value, {"actor", "desire", "starting_belief",
                      "resolved_belief", "beats"})
        found = any(a["actor"] == value["actor"] for a in candidate["arcs"])
        if (action == "add_arc" and found) or (action == "replace_arc" and not found):
            raise CanonError("arcs_invalid_edit_target")
        candidate["arcs"] = [a for a in candidate["arcs"]
                             if a["actor"] != value["actor"]] + [value]
    elif action in {"upsert_beat", "remove_beat"}:
        _keys(value, {"actor", "beat"} if action == "upsert_beat"
              else {"actor", "beat_id"})
        matches = [a for a in candidate["arcs"] if a["actor"] == value["actor"]]
        if len(matches) != 1:
            raise CanonError("arcs_unknown_actor")
        target = matches[0]["beats"]
        if action == "upsert_beat":
            _keys(value["beat"], {"id", "choice", "stage", "text"})
            target[:] = [b for b in target
                         if b["id"] != value["beat"]["id"]] + [value["beat"]]
        else:
            before = len(target)
            target[:] = [b for b in target if b["id"] != value["beat_id"]]
            if len(target) != before - 1:
                raise CanonError("arcs_unknown_beat")
        target.sort(key=lambda b: b["id"])
    else:
        raise CanonError("arcs_invalid_edit")
    candidate["arcs"].sort(key=lambda a: a["actor"])
    candidate["approved"] = False
    candidate["review_note"] = ""
    prove_arcs(candidate, world, cast)
    return candidate


def approve_arcs(source: Any, world: Any, cast: Any, note: str) -> dict[str, Any]:
    _text(note, "review_note")
    prove_arcs(source, world, cast)
    if cast["approved"] is not True:
        raise CanonError("arcs_cast_review_required")
    approved = strict_json(canonical(source))
    approved["approved"] = True
    approved["review_note"] = note
    prove_arcs(approved, world, cast)
    return approved


PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("arcs-data").textContent);
const world = data.world, cast = data.cast, arcs = data.arcs;
const root = document.getElementById("play");
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
let scene, flags, trace, beliefs, notes;
function node(tag, value) {
  const item = document.createElement(tag); item.textContent = value; return item;
}
function reset() {
  scene = world.start; flags = new Set(); trace = []; notes = [];
  beliefs = new Map(arcs.arcs.map(a => [a.actor, a.starting_belief]));
  render();
}
function advance(choice) {
  choice.grants.forEach(flag => flags.add(flag));
  trace.push(choice.id); scene = choice.to;
  for (const arc of arcs.arcs)
    for (const beat of arc.beats.filter(b => b.choice === choice.id)) {
      notes.push(beat.text);
      if (beat.stage === "resolution") beliefs.set(arc.actor, arc.resolved_belief);
    }
  render();
}
function render() {
  root.replaceChildren();
  const here = scenes.get(scene);
  root.append(node("h1", here.title), node("p", here.narrative));
  for (const arc of arcs.arcs) {
    const actor = cast.characters.find(a => a.id === arc.actor);
    root.append(node("h2", actor.name + ": " + arc.desire));
    root.append(node("p", "Belief: " + beliefs.get(arc.actor)));
  }
  for (const note of notes) root.append(node("blockquote", note));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
  } else {
    for (const choice of world.choices.filter(c => c.from === scene &&
      c.requires.every(flag => flags.has(flag)))) {
      const button = node("button", choice.label);
      button.type = "button";
      button.addEventListener("click", () => advance(choice));
      root.append(button);
    }
  }
  const restart = node("button", "Restart");
  restart.type = "button"; restart.addEventListener("click", reset);
  root.append(restart);
}
reset();
""".strip()


def compile_arcs(source: Any, world: Any, cast: Any) -> tuple[dict[str, Any], bytes]:
    if source["approved"] is not True or cast["approved"] is not True:
        raise CanonError("arcs_review_required")
    proof = prove_arcs(source, world, cast)
    recipe = {
        "schema": "jeeves.world.character_arcs_engine_recipe.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "cast_digest": digest(cast), "arcs_digest": digest(source),
        "arcs": source["arcs"], "proof": proof,
        "qualification": "reviewed_original_source_not_device_certified",
    }
    embedded = canonical({"world": world, "cast": cast, "arcs": source}).decode(
        "utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(PLAYER_JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Original character arcs: " + html.escape(world["id"]) +
        '</title></head><body><main id="play" aria-live="polite"></main>'
        '<script id="arcs-data" type="application/json">' + embedded +
        "</script><script>" + PLAYER_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("arcs_playable_too_large")
    return recipe, page


class ArcStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".arcs.json", world_id + ".arcs.playable.html",
                world_id + ".arcs.engine.json", world_id + ".arcs.receipt.json")

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("arcs_world_identity_mismatch")
        cast = strict_json(self.worlds._read(fd, world_id + ".cast.json"))
        validate_cast(cast, world)
        return world, cast

    def _source(self, fd: int, world_id: str, world: Any, cast: Any) -> Any:
        data = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_arcs(data, world, cast)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                return propose_arcs(*self._sources(fd, world_id), **kwargs)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                return {"arcs": source, "proof": prove_arcs(source, world, cast)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                prove_arcs(source, world, cast)
                if source["approved"]:
                    raise CanonError("arcs_approval_requires_review")
                try:
                    previous = self._source(fd, world_id, world, cast)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    previous = None
                if create:
                    if previous is not None or expected_digest is not None:
                        raise CanonError("arcs_already_exists")
                elif previous is None or digest(previous) != expected_digest:
                    raise CanonError("arcs_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(source))
                return digest(source)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def edit(self, world_id: str, expected_digest: str, operation: Any) -> str:
        inspected = self.inspect(world_id)
        if digest(inspected["arcs"]) != expected_digest:
            raise CanonError("arcs_stale_edit")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("arcs_stale_edit")
                updated = edit_arcs(source, world, cast, operation)
                self.worlds._write(fd, self._names(world_id)[0], canonical(updated))
                return digest(updated)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, expected_digest: str, note: str) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("arcs_stale_edit")
                approved = approve_arcs(source, world, cast, note)
                self.worlds._write(fd, self._names(world_id)[0], canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any, cast: Any):
        recipe, playable = compile_arcs(source, world, cast)
        manifest = canonical(recipe)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cast_digest": digest(cast),
            "arcs_digest": digest(source), "proof_digest": digest(recipe["proof"]),
            "artifacts": {
                self._names(world["id"])[1]: sha256(playable).hexdigest(),
                self._names(world["id"])[2]: sha256(manifest).hexdigest(),
            },
            "qualification": "reviewed_original_source_not_release_certified",
        }
        return receipt, playable, manifest

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("arcs_stale_edit")
                receipt, playable, manifest = self._outputs(source, world, cast)
                names = self._names(world_id)
                self.worlds._write(fd, names[1], playable)
                self.worlds._write(fd, names[2], manifest)
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
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                receipt, playable, manifest = self._outputs(source, world, cast)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[3])) != receipt:
                    raise CanonError("arcs_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("arcs_playable_mismatch")
                if _artifact_read(fd, names[2]) != manifest:
                    raise CanonError("arcs_recipe_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if source["approved"] is not True or cast["approved"] is not True:
                    raise CanonError("arcs_review_required")
                session = validate_session(strict_json(self.worlds._read(
                    fd, SessionStore._name(world_id, slot))), world)
                return {"slot": slot, "session_digest": digest(session),
                        "replay": replay_arcs(source, world, cast, session["choices"])}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .character_arcs_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("arcs_stale_edit")
                content = render_editor(source, world, cast)
                name = world_id + ".arcs.editor.html"
                self.worlds._write(fd, name, content)
                return {"html_file": name, "html_sha256": sha256(content).hexdigest(),
                        "arcs_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
