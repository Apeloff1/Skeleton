"""Original NPC trust: reviewed, source-leased, replay-proven HTML5 relationships."""
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

SCHEMA = "jeeves.world.relationships.v1"
PROOF_SCHEMA = "jeeves.world.relationships_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.relationships_receipt.v1"


def validate_relationships(data: Any, world: Any, cast: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    obj = _keys(data, {"schema", "world_id", "world_digest", "cast_digest",
                       "prompt", "approved", "review_note", "bonds"})
    if obj["schema"] != SCHEMA:
        raise CanonError("relationships_schema_mismatch")
    if (obj["world_id"] != world["id"] or obj["world_digest"] != digest(world)
            or obj["cast_digest"] != digest(cast)):
        raise CanonError("relationships_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("relationships_invalid_approval")
    actors = {a["id"]: a for a in cast["characters"]}
    choices = {c["id"] for c in world["choices"]}
    bonds = _list(obj["bonds"], "bonds", 8)
    if not bonds:
        raise CanonError("relationships_empty")
    ids = []
    for bond in bonds:
        _keys(bond, {"id", "actor", "name", "rules", "reactions"})
        ids.append(_id(bond["id"], "bond.id"))
        actor = _id(bond["actor"], "bond.actor")
        if actor not in actors:
            raise CanonError("relationships_unknown_actor")
        _text(bond["name"], "bond.name", 160)
        rules = _list(bond["rules"], "rules", 32)
        reactions = _list(bond["reactions"], "reactions", 32)
        if not rules or not reactions:
            raise CanonError("relationships_empty_bond")
        rule_ids = []
        for rule in rules:
            _keys(rule, {"id", "choice", "delta", "reason"})
            rule_ids.append(_id(rule["id"], "rule.id"))
            if _id(rule["choice"], "rule.choice") not in choices:
                raise CanonError("relationships_unknown_choice")
            if (type(rule["delta"]) is not int or rule["delta"] == 0
                    or not -20 <= rule["delta"] <= 20):
                raise CanonError("relationships_invalid_delta")
            _text(rule["reason"], "rule.reason", 512)
        if rule_ids != sorted(set(rule_ids)):
            raise CanonError("relationships_noncanonical_rules")
        reaction_ids = []
        intervals: dict[str, list[tuple[int, int]]] = {}
        for reaction in reactions:
            _keys(reaction, {"id", "scene", "min_score", "max_score", "text"})
            reaction_ids.append(_id(reaction["id"], "reaction.id"))
            scene = _id(reaction["scene"], "reaction.scene")
            if scene not in actors[actor]["scenes"]:
                raise CanonError("relationships_absent_actor")
            lo, hi = reaction["min_score"], reaction["max_score"]
            if (type(lo) is not int or type(hi) is not int
                    or not -100 <= lo <= hi <= 100):
                raise CanonError("relationships_invalid_interval")
            if any(max(lo, a) <= min(hi, b) for a, b in intervals.get(scene, ())):
                raise CanonError("relationships_ambiguous_reaction")
            intervals.setdefault(scene, []).append((lo, hi))
            _text(reaction["text"], "reaction.text", 2048)
        if reaction_ids != sorted(set(reaction_ids)):
            raise CanonError("relationships_noncanonical_reactions")
    if ids != sorted(set(ids)):
        raise CanonError("relationships_noncanonical_bonds")
    if len(canonical(obj)) > 524288:
        raise CanonError("relationships_too_large")
    return obj


def _update(scores: tuple[int, ...], bonds: list[dict[str, Any]],
            choice: str) -> tuple[int, ...]:
    result = []
    for score, bond in zip(scores, bonds):
        for rule in bond["rules"]:
            if rule["choice"] == choice:
                score = max(-100, min(100, score + rule["delta"]))
        result.append(score)
    return tuple(result)


def _reactions(scene: str, scores: tuple[int, ...], bonds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"bond": bond["id"], "actor": bond["actor"], "score": score,
             "reaction": reaction["id"], "text": reaction["text"]}
            for bond, score in zip(bonds, scores)
            for reaction in bond["reactions"]
            if reaction["scene"] == scene
            and reaction["min_score"] <= score <= reaction["max_score"]]


def prove_relationships(data: Any, world: Any, cast: Any) -> dict[str, Any]:
    obj = validate_relationships(data, world, cast)
    bonds = obj["bonds"]
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for group in edges.values():
        group.sort(key=lambda item: item["id"])
    endings = {e["scene"] for e in world["endings"]}
    initial = (world["start"], frozenset(), tuple(0 for _ in bonds))
    queue = deque([(initial, ())])
    visited = {initial}
    witnesses: dict[str, list[str]] = {}
    ending_witnesses: dict[str, list[str]] = {}
    while queue:
        (scene, flags, scores), trace = queue.popleft()
        for reaction in _reactions(scene, scores, bonds):
            witnesses.setdefault(reaction["bond"] + ":" + reaction["reaction"], list(trace))
        if scene in endings:
            ending_witnesses.setdefault(scene, list(trace))
            continue
        enabled = [c for c in edges.get(scene, ()) if set(c["requires"]) <= flags]
        if not enabled:
            raise CanonError("relationships_reachable_dead_end")
        if len(trace) >= 128:
            raise CanonError("relationships_step_budget")
        for choice in enabled:
            state = (choice["to"], flags | frozenset(choice["grants"]),
                     _update(scores, bonds, choice["id"]))
            if state in visited:
                continue
            if len(visited) >= 4096:
                raise CanonError("relationships_state_budget")
            visited.add(state)
            queue.append((state, trace + (choice["id"],)))
    required = {b["id"] + ":" + r["id"] for b in bonds for r in b["reactions"]}
    if required - set(witnesses):
        raise CanonError("relationships_unreachable_reaction")
    if endings - set(ending_witnesses):
        raise CanonError("relationships_unreachable_ending")
    return {"schema": PROOF_SCHEMA, "world_digest": digest(world),
            "cast_digest": digest(cast), "relationships_digest": digest(obj),
            "states_explored": len(visited),
            "reaction_witnesses": {k: witnesses[k] for k in sorted(witnesses)},
            "ending_witnesses": {k: ending_witnesses[k] for k in sorted(ending_witnesses)}}


def propose_relationships(world: Any, cast: Any, *, prompt: str, bond_id: str,
                          actor: str, name: str, choice: str, delta: int,
                          reason: str, reaction_id: str, scene: str,
                          min_score: int, max_score: int, text: str) -> dict[str, Any]:
    obj = {"schema": SCHEMA, "world_id": world["id"],
           "world_digest": digest(world), "cast_digest": digest(cast),
           "prompt": prompt, "approved": False,
           "review_note": "Original author review required",
           "bonds": [{"id": bond_id, "actor": actor, "name": name,
                      "rules": [{"id": "first_change", "choice": choice,
                                 "delta": delta, "reason": reason}],
                      "reactions": [{"id": reaction_id, "scene": scene,
                                     "min_score": min_score, "max_score": max_score,
                                     "text": text}]}]}
    prove_relationships(obj, world, cast)
    return obj


def edit_relationships(data: Any, world: Any, cast: Any, operation: Any) -> dict[str, Any]:
    validate_relationships(data, world, cast)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(data))
    action, value = op["action"], op["value"]
    if action in ("add_bond", "replace_bond"):
        _keys(value, {"id", "actor", "name", "rules", "reactions"})
        if action == "add_bond":
            candidate["bonds"].append(value)
            candidate["bonds"].sort(key=lambda b: b["id"])
        else:
            positions = [i for i, b in enumerate(candidate["bonds"]) if b["id"] == value["id"]]
            if len(positions) != 1:
                raise CanonError("relationships_unknown_edit")
            candidate["bonds"][positions[0]] = value
    elif action == "remove_bond":
        _keys(value, {"id"})
        old = len(candidate["bonds"])
        candidate["bonds"] = [b for b in candidate["bonds"] if b["id"] != value["id"]]
        if len(candidate["bonds"]) != old - 1:
            raise CanonError("relationships_unknown_edit")
    else:
        raise CanonError("relationships_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Edit requires renewed author review"
    prove_relationships(candidate, world, cast)
    return candidate


def evaluate_relationships(data: Any, world: Any, cast: Any, choices: Any) -> dict[str, Any]:
    validate_relationships(data, world, cast)
    replay = replay_choices(world, choices)
    scores = tuple(0 for _ in data["bonds"])
    steps = []
    for step in replay["steps"]:
        if step["choice"] is not None:
            scores = _update(scores, data["bonds"], step["choice"])
        steps.append({"scene": step["scene"], "choice": step["choice"],
                      "scores": {b["id"]: s for b, s in zip(data["bonds"], scores)},
                      "reactions": _reactions(step["scene"], scores, data["bonds"])})
    return {"world_digest": digest(world), "cast_digest": digest(cast),
            "relationships_digest": digest(data), "scene": replay["scene"],
            "ending": replay["ending"], "steps": steps,
            "scores": steps[-1]["scores"], "reactions": steps[-1]["reactions"]}


_PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("relationship-data").textContent);
const world = model.world, cast = model.cast, bonds = model.relationships.bonds;
const actors = new Map(cast.characters.map(a => [a.id, a.name]));
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const root = document.getElementById("play");
let scene = world.start, flags = new Set(), trace = [];
let scores = new Map(bonds.map(b => [b.id, 0]));
function node(tag, text) {
  const el = document.createElement(tag); el.textContent = text; return el;
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  const dialogue = cast.lines.filter(line => line.scene === scene &&
    line.requires_flags.every(flag => flags.has(flag)))
    .sort((a,b) => a.order - b.order || a.id.localeCompare(b.id));
  for (const line of dialogue)
    root.append(node("p", actors.get(line.speaker) + ": " + line.text));
  for (const bond of bonds) {
    const score = scores.get(bond.id);
    root.append(node("p", bond.name + " trust: " + score));
    for (const reaction of bond.reactions) {
      if (reaction.scene === scene && reaction.min_score <= score && score <= reaction.max_score)
        root.append(node("p", bond.name + ": " + reaction.text));
    }
  }
  root.append(node("p", "Choices: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = [];
      scores = new Map(bonds.map(b => [b.id, 0])); render();
    });
    root.append(restart); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(f => flags.has(f))) continue;
    const button = node("button", choice.label);
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      for (const bond of bonds) {
        let score = scores.get(bond.id);
        for (const rule of bond.rules)
          if (rule.choice === choice.id) score = Math.max(-100, Math.min(100, score + rule.delta));
        scores.set(bond.id, score);
      }
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
}
render();
""".strip()


def render_relationships_html(data: Any, world: Any, cast: Any) -> bytes:
    prove_relationships(data, world, cast)
    if not data["approved"] or not cast["approved"]:
        raise CanonError("relationships_review_required")
    payload = canonical({"world": world, "cast": cast, "relationships": data}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "script-src 'sha256-" + policy + "'; connect-src 'none'; "
        'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>' + title + ' relationships</title></head><body>'
        '<main id="play" aria-live="polite"></main>'
        '<script id="relationship-data" type="application/json">' + payload + '</script>'
        '<script>' + _PLAYER_JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("relationships_playable_too_large")
    return page


class RelationshipStore:
    """Descriptor-anchored world/cast custody with exclusive review lease."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.cast = CastStore(root)
        self.worlds = self.cast.worlds

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".relationships.json",
                world_id + ".relationships.playable.html",
                world_id + ".relationships.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        world = self.cast._world(fd, world_id)
        return world, self.cast._cast(fd, world_id, world)

    def _read(self, fd: int, world_id: str, world: Any, cast: Any) -> Any:
        return validate_relationships(
            strict_json(self.worlds._read(fd, self._names(world_id)[0])), world, cast)

    def propose(self, world_id: str, **kwargs: Any) -> Any:
        fd = self.worlds._directory()
        try:
            return propose_relationships(*self._sources(fd, world_id), **kwargs)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            data = self._read(fd, world_id, world, cast)
            return {"relationships": data, "proof": prove_relationships(data, world, cast)}
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        """Read one persisted, independently replay-verified player session."""
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            data = self._read(fd, world_id, world, cast)
            if not data["approved"] or not cast["approved"]:
                raise CanonError("relationships_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))),
                world,
            )
            result = evaluate_relationships(data, world, cast, session["choices"])
            return {"session_digest": digest(session), "slot": slot,
                    "revision": session["revision"], "player": result}
        finally:
            os.close(fd)

    def _locked(self, fd: int, world_id: str) -> None:
        handle = self.cast._lock(fd, world_id)
        os.close(handle)

    def publish(self, world_id: str, data: Any, *,
                expected_digest: str | None = None, create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                candidate = strict_json(canonical(data))
                if type(candidate) is not dict:
                    raise CanonError("expected_object")
                candidate["approved"] = False
                candidate["review_note"] = "Source published; author review required"
                prove_relationships(candidate, world, cast)
                try:
                    old = self._read(fd, world_id, world, cast)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("relationships_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("relationships_stale_edit")
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
                    raise CanonError("relationships_cast_review_required")
                data = self._read(fd, world_id, world, cast)
                if digest(data) != expected_digest:
                    raise CanonError("relationships_stale_edit")
                data["approved"] = True
                data["review_note"] = review_note
                prove_relationships(data, world, cast)
                self.worlds._write(fd, self._names(world_id)[0], canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, data: Any, world: Any, cast: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_relationships(data, world, cast)
        playable = render_relationships_html(data, world, cast)
        receipt = {"schema": RECEIPT_SCHEMA, "world_id": world["id"],
                   "world_digest": digest(world), "cast_digest": digest(cast),
                   "relationships_digest": digest(data), "proof_digest": digest(proof),
                   "html_file": self._names(world["id"])[1],
                   "html_sha256": sha256(playable).hexdigest(),
                   "qualification": "reviewed_original_npc_trust_not_release_certified"}
        return receipt, playable

    def editor(self, world_id: str, expected_digest: str) -> dict[str, str]:
        from .relationships_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                if digest(data) != expected_digest:
                    raise CanonError("relationships_stale_edit")
                page = render_editor(data, world, cast)
                name = world_id + ".relationships.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "relationships_digest": digest(data)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                if digest(data) != expected_digest:
                    raise CanonError("relationships_stale_edit")
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
            self._locked(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                receipt, playable = self._outputs(data, world, cast)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("relationships_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("relationships_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
