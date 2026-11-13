"""Reviewed NPC testimony, branch-exclusive contradictions and source-leased replay."""
from __future__ import annotations

import base64
from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .cast import CastStore, validate_cast
from .session import SessionStore, replay_choices, validate_session
from .world_canon import CanonError, _id, _keys, _list, _text, canonical, digest, prove, strict_json

SCHEMA = "jeeves.world.testimony.v1"
PROOF_SCHEMA = "jeeves.world.testimony_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.testimony_receipt.v1"


def validate_testimony(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    obj = _keys(source, {"schema", "world_id", "world_digest", "cast_digest",
                         "prompt", "approved", "review_note", "statements"})
    if obj["schema"] != SCHEMA:
        raise CanonError("testimony_schema_mismatch")
    if (obj["world_id"] != world["id"] or obj["world_digest"] != digest(world)
            or obj["cast_digest"] != digest(cast)):
        raise CanonError("testimony_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("testimony_invalid_approval")
    actors = {actor["id"]: actor for actor in cast["characters"]}
    choices = {choice["id"]: choice for choice in world["choices"]}
    statements = _list(obj["statements"], "statements", 24)
    if not statements:
        raise CanonError("testimony_empty")
    ids = []
    for item in statements:
        _keys(item, {"id", "actor", "scene", "choice", "claim", "stance",
                     "text", "provenance"})
        ids.append(_id(item["id"], "statement.id"))
        actor = _id(item["actor"], "statement.actor")
        scene = _id(item["scene"], "statement.scene")
        choice_id = _id(item["choice"], "statement.choice")
        _id(item["claim"], "statement.claim")
        if actor not in actors or scene not in actors[actor]["scenes"]:
            raise CanonError("testimony_actor_absent")
        if choice_id not in choices or choices[choice_id]["to"] != scene:
            raise CanonError("testimony_trigger_not_arrival")
        if item["stance"] not in ("supports", "denies") or type(item["stance"]) is not str:
            raise CanonError("testimony_invalid_stance")
        if item["provenance"] not in ("firsthand", "hearsay", "record"):
            raise CanonError("testimony_invalid_provenance")
        _text(item["text"], "statement.text", 2048)
    if ids != sorted(set(ids)):
        raise CanonError("testimony_noncanonical_statements")
    if len(canonical(obj)) > 524288:
        raise CanonError("testimony_too_large")
    return obj


def _reveals(statements: list[dict[str, Any]], choice: str) -> int:
    return sum(1 << index for index, statement in enumerate(statements)
               if statement["choice"] == choice)


def _conflict(statements: list[dict[str, Any]], mask: int) -> bool:
    positions: dict[str, str] = {}
    for index, statement in enumerate(statements):
        if mask & (1 << index):
            claim, stance = statement["claim"], statement["stance"]
            if claim in positions and positions[claim] != stance:
                return True
            positions[claim] = stance
    return False


def prove_testimony(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    obj = validate_testimony(source, world, cast)
    statements = obj["statements"]
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for group in edges.values():
        group.sort(key=lambda choice: choice["id"])
    endings = {ending["scene"] for ending in world["endings"]}
    initial = (world["start"], frozenset(), 0)
    queue = deque([(initial, ())])
    visited = {initial}
    witnessed: dict[str, list[str]] = {}
    ending_witnesses: dict[str, list[str]] = {}
    while queue:
        (scene, flags, mask), trace = queue.popleft()
        for index, statement in enumerate(statements):
            if mask & (1 << index):
                witnessed.setdefault(statement["id"], list(trace))
        if scene in endings:
            ending_witnesses.setdefault(scene, list(trace))
            continue
        enabled = [choice for choice in edges.get(scene, ())
                   if set(choice["requires"]) <= flags]
        if not enabled:
            raise CanonError("testimony_reachable_dead_end")
        if len(trace) >= 128:
            raise CanonError("testimony_step_budget")
        for choice in enabled:
            next_mask = mask | _reveals(statements, choice["id"])
            if _conflict(statements, next_mask):
                raise CanonError("testimony_coexisting_contradiction")
            state = (choice["to"], flags | frozenset(choice["grants"]), next_mask)
            if state in visited:
                continue
            if len(visited) >= 4096:
                raise CanonError("testimony_state_budget")
            visited.add(state)
            queue.append((state, trace + (choice["id"],)))
    if set(item["id"] for item in statements) - set(witnessed):
        raise CanonError("testimony_unreachable_statement")
    if endings - set(ending_witnesses):
        raise CanonError("testimony_unreachable_ending")
    return {"schema": PROOF_SCHEMA, "world_digest": digest(world),
            "cast_digest": digest(cast), "testimony_digest": digest(obj),
            "states_explored": len(visited),
            "statement_witnesses": {k: witnessed[k] for k in sorted(witnessed)},
            "ending_witnesses": {k: ending_witnesses[k] for k in sorted(ending_witnesses)}}


def propose_testimony(world: Any, cast: Any, *, prompt: str, statement_id: str,
                     actor: str, scene: str, choice: str, claim: str,
                     stance: str, text: str, provenance: str) -> dict[str, Any]:
    obj = {"schema": SCHEMA, "world_id": world["id"],
           "world_digest": digest(world), "cast_digest": digest(cast),
           "prompt": prompt, "approved": False,
           "review_note": "Original testimony requires author review",
           "statements": [{"id": statement_id, "actor": actor, "scene": scene,
                           "choice": choice, "claim": claim, "stance": stance,
                           "text": text, "provenance": provenance}]}
    prove_testimony(obj, world, cast)
    return obj


def edit_testimony(source: Any, world: Any, cast: Any, operation: Any) -> dict[str, Any]:
    validate_testimony(source, world, cast)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(source))
    action, value = op["action"], op["value"]
    if action in ("add_statement", "replace_statement"):
        _keys(value, {"id", "actor", "scene", "choice", "claim", "stance",
                      "text", "provenance"})
        if action == "add_statement":
            candidate["statements"].append(value)
        else:
            matches = [i for i, item in enumerate(candidate["statements"])
                       if item["id"] == value["id"]]
            if len(matches) != 1:
                raise CanonError("testimony_unknown_edit")
            candidate["statements"][matches[0]] = value
        candidate["statements"].sort(key=lambda item: item["id"])
    elif action == "remove_statement":
        _keys(value, {"id"})
        old = len(candidate["statements"])
        candidate["statements"] = [item for item in candidate["statements"]
                                   if item["id"] != value["id"]]
        if len(candidate["statements"]) != old - 1:
            raise CanonError("testimony_unknown_edit")
    else:
        raise CanonError("testimony_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Changed testimony requires renewed author review"
    prove_testimony(candidate, world, cast)
    return candidate


def replay_testimony(source: Any, world: Any, cast: Any, choices: Any) -> dict[str, Any]:
    validate_testimony(source, world, cast)
    replay = replay_choices(world, choices)
    revealed: set[str] = set()
    steps = []
    for step in replay["steps"]:
        if step["choice"] is not None:
            revealed.update(item["id"] for item in source["statements"]
                            if item["choice"] == step["choice"])
        current = [item for item in source["statements"]
                   if item["id"] in revealed and item["scene"] == step["scene"]]
        steps.append({"scene": step["scene"], "choice": step["choice"],
                      "statements": current})
    return {"world_digest": digest(world), "cast_digest": digest(cast),
            "testimony_digest": digest(source), "scene": replay["scene"],
            "ending": replay["ending"], "steps": steps,
            "revealed_ids": sorted(revealed)}


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("testimony-data").textContent);
const world = data.world, statements = data.testimony.statements;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const actors = new Map(data.cast.characters.map(a => [a.id, a.name]));
const root = document.getElementById("play");
let scene = world.start, flags = new Set(), trace = [], revealed = new Set();
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  for (const item of statements)
    if (item.scene === scene && revealed.has(item.id))
      root.append(node("blockquote", actors.get(item.actor) + " [" + item.provenance + "]: " + item.text));
  root.append(node("p", "Witnessed choices: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = []; revealed = new Set(); render();
    });
    root.append(restart); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(flag => flags.has(flag))) continue;
    const button = node("button", choice.label);
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      for (const item of statements) if (item.choice === choice.id) revealed.add(item.id);
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
}
render();
""".strip()


def render_testimony_html(source: Any, world: Any, cast: Any) -> bytes:
    prove_testimony(source, world, cast)
    if not source["approved"] or not cast["approved"]:
        raise CanonError("testimony_review_required")
    payload = canonical({"world": world, "cast": cast, "testimony": source}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + title + ' testimony</title></head><body>'
            '<main id="play" aria-live="polite"></main>'
            '<script id="testimony-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("testimony_playable_too_large")
    return page


class TestimonyStore:
    """Descriptor-anchored, explicitly reviewed NPC testimony custody."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.cast = CastStore(root)
        self.worlds = self.cast.worlds

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".testimony.json",
                world_id + ".testimony.playable.html",
                world_id + ".testimony.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        world = self.cast._world(fd, world_id)
        return world, self.cast._cast(fd, world_id, world)

    def _read(self, fd: int, world_id: str, world: Any, cast: Any) -> Any:
        return validate_testimony(
            strict_json(self.worlds._read(fd, self._names(world_id)[0])), world, cast)

    def _locked(self, fd: int, world_id: str) -> None:
        handle = self.cast._lock(fd, world_id)
        os.close(handle)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            return propose_testimony(*self._sources(fd, world_id), **kwargs)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            source = self._read(fd, world_id, world, cast)
            return {"testimony": source, "proof": prove_testimony(source, world, cast)}
        finally:
            os.close(fd)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                candidate = strict_json(canonical(source))
                if type(candidate) is not dict:
                    raise CanonError("expected_object")
                candidate["approved"] = False
                candidate["review_note"] = "Published testimony requires author review"
                prove_testimony(candidate, world, cast)
                try:
                    old = self._read(fd, world_id, world, cast)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("testimony_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("testimony_stale_edit")
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
                world, cast = self._sources(fd, world_id)
                if not cast["approved"]:
                    raise CanonError("testimony_cast_review_required")
                source = self._read(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("testimony_stale_edit")
                source["approved"] = True
                source["review_note"] = review_note
                prove_testimony(source, world, cast)
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
            world, cast = self._sources(fd, world_id)
            source = self._read(fd, world_id, world, cast)
            if not source["approved"] or not cast["approved"]:
                raise CanonError("testimony_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
            return {"slot": slot, "session_digest": digest(session),
                    "revision": session["revision"],
                    "player": replay_testimony(source, world, cast, session["choices"])}
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any, cast: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_testimony(source, world, cast)
        playable = render_testimony_html(source, world, cast)
        receipt = {"schema": RECEIPT_SCHEMA, "world_id": world["id"],
                   "world_digest": digest(world), "cast_digest": digest(cast),
                   "testimony_digest": digest(source), "proof_digest": digest(proof),
                   "html_file": self._names(world["id"])[1],
                   "html_sha256": sha256(playable).hexdigest(),
                   "qualification": "reviewed_original_testimony_not_release_certified"}
        return receipt, playable

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._read(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("testimony_stale_edit")
                receipt, playable = self._outputs(source, world, cast)
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
                world, cast = self._sources(fd, world_id)
                source = self._read(fd, world_id, world, cast)
                receipt, playable = self._outputs(source, world, cast)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("testimony_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("testimony_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .testimony_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._read(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("testimony_stale_edit")
                page = render_editor(source, world, cast)
                name = world_id + ".testimony.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "testimony_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
