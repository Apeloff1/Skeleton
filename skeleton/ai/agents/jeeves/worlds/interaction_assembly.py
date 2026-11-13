"""Unified original NPC dialogue + economy + character arc gameplay handoff.

All five sources are read under one world-wide lease, proven together, and
compiled into a single deterministic offline player and typed engine recipe.
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
from .character_arcs import prove_arcs, replay_arcs
from .dialogue_graph import prove_dialogues
from .economy import _advance, _graph, prove_economy, replay_economy
from .session import SessionStore, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.interaction_assembly.v1"
RECEIPT_SCHEMA = "jeeves.world.interaction_assembly_receipt.v1"
SOURCE_NAMES = ("world", "cast", "economy", "arcs", "dialogue")
MAX_STATES = 4096


def prove_interaction(world: Any, cast: Any, economy: Any,
                      arcs: Any, dialogue: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    if not all(source["approved"] is True for source in
               (cast, economy, arcs, dialogue)):
        raise CanonError("interaction_review_required")
    proofs = {
        "economy": prove_economy(economy, world),
        "arcs": prove_arcs(arcs, world, cast),
        "dialogue": prove_dialogues(dialogue, world, cast),
    }
    # A world-valid dialogue choice may still be unaffordable. Prove at least
    # one actual economy-state witness for every authored conversation handoff.
    data, resource_ids, capacities, effects, edges = _graph(economy, world)
    initial = tuple(r["initial"] for r in data["resources"])
    start = (world["start"], frozenset(), initial)
    queue = deque([(start, ())])
    seen = {start}
    handoffs = {
        (conversation["id"], choice)
        for conversation in dialogue["conversations"]
        for node in conversation["nodes"]
        for response in node["responses"]
        if (choice := response["world_choice"]) is not None
    }
    conversations = {c["id"]: c for c in dialogue["conversations"]}
    witnesses: dict[str, list[str]] = {}
    while queue:
        (scene, flags, balances), path = queue.popleft()
        for conversation in dialogue["conversations"]:
            if conversation["scene"] != scene:
                continue
            terminal_choices = {
                response["world_choice"]
                for node in conversation["nodes"]
                for response in node["responses"]
                if response["world_choice"] is not None
            }
            if not any(
                edge["id"] in terminal_choices and
                set(edge["requires"]) <= flags and
                _advance(edge, balances, resource_ids, capacities,
                         effects) is not None
                for edge in edges.get(scene, [])
            ):
                raise CanonError("interaction_dialogue_unaffordable_state",
                                 conversation["id"])
        for cid, choice_id in sorted(handoffs):
            conversation = conversations[cid]
            if conversation["scene"] != scene:
                continue
            for edge in edges.get(scene, []):
                if (edge["id"] == choice_id and
                        set(edge["requires"]) <= flags and
                        _advance(edge, balances, resource_ids, capacities,
                                 effects) is not None):
                    witnesses.setdefault(cid + ":" + choice_id, list(path))
        for edge in edges.get(scene, []):
            if not set(edge["requires"]) <= flags:
                continue
            balances_next = _advance(
                edge, balances, resource_ids, capacities, effects)
            if balances_next is None:
                continue
            state = (edge["to"], flags | frozenset(edge["grants"]), balances_next)
            if state not in seen:
                seen.add(state)
                if len(seen) > MAX_STATES:
                    raise CanonError("interaction_state_budget_exhausted")
                queue.append((state, path + (edge["id"],)))
    if len(witnesses) != len(handoffs):
        raise CanonError("interaction_unaffordable_dialogue_handoff")
    return {
        "schema": "jeeves.world.interaction_assembly_proof.v1",
        "source_digests": dict(zip(SOURCE_NAMES, map(digest, (
            world, cast, economy, arcs, dialogue)))),
        "plane_proofs": proofs,
        "states_explored": len(seen),
        "dialogue_handoff_witnesses": {
            key: witnesses[key] for key in sorted(witnesses)},
    }


def replay_interaction(world: Any, cast: Any, economy: Any,
                       arcs: Any, dialogue: Any, session: Any) -> dict[str, Any]:
    proof = prove_interaction(world, cast, economy, arcs, dialogue)
    validate_session(session, world)
    economy_view = replay_economy(economy, world, session["choices"])
    arcs_view = replay_arcs(arcs, world, cast, session["choices"])
    if economy_view["scene"] != arcs_view["scene"]:
        raise CanonError("interaction_replay_disagreement")
    conversations = sorted([
        c["id"] for c in dialogue["conversations"]
        if c["scene"] == session["scene"]
    ])
    return {
        "schema": "jeeves.world.interaction_assembly_replay.v1",
        "world_id": world["id"], "session_digest": digest(session),
        "source_digests": proof["source_digests"],
        "scene": session["scene"], "ending": session["ending"],
        "economy": economy_view, "arcs": arcs_view,
        "available_conversations": conversations,
        "qualification": "reviewed_source_replay_not_device_certified",
    }


PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("interaction-data").textContent);
const world = model.world, cast = model.cast, economy = model.economy;
const arcs = model.arcs, dialogue = model.dialogue;
const root = document.getElementById("play");
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const effects = new Map(economy.effects.map(e => [e.choice, e]));
let scene, flags, balances, beliefs, notes, trace, active, nodeId;
function node(tag, value) {
  const item = document.createElement(tag); item.textContent = value; return item;
}
function button(label, action) {
  const item = node("button", label); item.type = "button";
  item.addEventListener("click", action); root.append(item);
}
function reset() {
  scene = world.start; flags = new Set(); notes = []; trace = [];
  balances = new Map(economy.resources.map(r => [r.id, r.initial]));
  beliefs = new Map(arcs.arcs.map(a => [a.actor, a.starting_belief]));
  active = null; nodeId = null; render();
}
function available(choice) {
  if (!choice.requires.every(f => flags.has(f))) return false;
  const effect = effects.get(choice.id) || {costs: {}, gains: {}};
  return economy.resources.every(r => {
    const next = balances.get(r.id) - (effect.costs[r.id] || 0) +
      (effect.gains[r.id] || 0);
    return next >= 0 && next <= r.capacity;
  });
}
function advance(choice) {
  if (!available(choice)) return;
  const effect = effects.get(choice.id) || {costs: {}, gains: {}};
  for (const r of economy.resources)
    balances.set(r.id, balances.get(r.id) - (effect.costs[r.id] || 0) +
      (effect.gains[r.id] || 0));
  for (const arc of arcs.arcs)
    for (const beat of arc.beats.filter(b => b.choice === choice.id)) {
      notes.push(beat.text);
      if (beat.stage === "resolution") beliefs.set(arc.actor, arc.resolved_belief);
    }
  choice.grants.forEach(f => flags.add(f));
  trace.push(choice.id); scene = choice.to; active = null; nodeId = null;
  render();
}
function render() {
  root.replaceChildren();
  const here = scenes.get(scene);
  root.append(node("h1", here.title), node("p", here.narrative));
  for (const resource of economy.resources)
    root.append(node("p", resource.name + ": " + balances.get(resource.id) +
      "/" + resource.capacity));
  for (const arc of arcs.arcs) {
    const actor = cast.characters.find(a => a.id === arc.actor);
    root.append(node("p", actor.name + " believes: " + beliefs.get(arc.actor)));
  }
  for (const note of notes) root.append(node("blockquote", note));
  if (active) {
    const current = active.nodes.find(n => n.id === nodeId);
    root.append(node("h2", current.text));
    for (const response of current.responses) {
      if (response.world_choice !== null) {
        const choice = world.choices.find(c => c.id === response.world_choice);
        if (available(choice)) button(response.label, () => advance(choice));
      } else {
        button(response.label, () => {nodeId = response.next_node; render();});
      }
    }
    button("Leave conversation", () => {active = null; render();});
    return;
  }
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
  } else {
    for (const conversation of dialogue.conversations.filter(c => c.scene === scene)) {
      const actor = cast.characters.find(a => a.id === conversation.actor);
      button("Talk to " + actor.name, () => {
        active = conversation; nodeId = conversation.start; render();
      });
    }
    for (const choice of world.choices.filter(c => c.from === scene && available(c)))
      button(choice.label, () => advance(choice));
  }
  button("Restart", reset);
}
reset();
""".strip()


def compile_interaction(world: Any, cast: Any, economy: Any,
                        arcs: Any, dialogue: Any) -> tuple[dict[str, Any], bytes]:
    proof = prove_interaction(world, cast, economy, arcs, dialogue)
    manifest = {
        "schema": SCHEMA, "world_id": world["id"],
        "source_digests": proof["source_digests"],
        "proof_digest": digest(proof),
        "scene_nodes": world["scenes"], "choice_edges": world["choices"],
        "ending_nodes": world["endings"], "characters": cast["characters"],
        "resources": economy["resources"], "economy_effects": economy["effects"],
        "character_arcs": arcs["arcs"], "dialogues": dialogue["conversations"],
        "qualification": "reviewed_original_engine_recipe_not_built_or_device_certified",
    }
    embedded = canonical({
        "world": world, "cast": cast, "economy": economy,
        "arcs": arcs, "dialogue": dialogue,
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(PLAYER_JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Original interaction studio: " + html.escape(world["id"]) +
        '</title></head><body><main id="play" aria-live="polite"></main>'
        '<script id="interaction-data" type="application/json">' + embedded +
        "</script><script>" + PLAYER_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864 or len(canonical(manifest)) > 1572864:
        raise CanonError("interaction_artifact_too_large")
    return manifest, page


class InteractionStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".interaction.playable.html",
                world_id + ".interaction.engine.json",
                world_id + ".interaction.receipt.json")

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _sources(self, fd: int, world_id: str) -> tuple[Any, ...]:
        _id(world_id, "world_id")
        sources = tuple(strict_json(self.worlds._read(fd, world_id + suffix))
                        for suffix in (".json", ".cast.json", ".economy.json",
                                       ".arcs.json", ".dialogue.json"))
        if sources[0]["id"] != world_id:
            raise CanonError("interaction_world_identity_mismatch")
        prove_interaction(*sources)
        return sources

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                proof = prove_interaction(*self._sources(fd, world_id))
                return {"schema": SCHEMA, "world_id": world_id, "proof": proof}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, sources: tuple[Any, ...]):
        manifest, playable = compile_interaction(*sources)
        recipe = canonical(manifest)
        names = self._names(sources[0]["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": sources[0]["id"],
            "source_digests": manifest["source_digests"],
            "proof_digest": manifest["proof_digest"],
            "artifacts": {
                names[0]: sha256(playable).hexdigest(),
                names[1]: sha256(recipe).hexdigest(),
            },
            "qualification": "reviewed_source_only_not_release_certified",
        }
        return receipt, playable, recipe

    def compile(self, world_id: str, expected_digests: Any) -> dict[str, Any]:
        if type(expected_digests) is not dict or set(expected_digests) != set(SOURCE_NAMES):
            raise CanonError("interaction_invalid_lease")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                receipt, playable, recipe = self._outputs(sources)
                if receipt["source_digests"] != expected_digests:
                    raise CanonError("interaction_stale_source")
                names = self._names(world_id)
                self.worlds._write(fd, names[0], playable)
                self.worlds._write(fd, names[1], recipe)
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
                sources = self._sources(fd, world_id)
                receipt, playable, recipe = self._outputs(sources)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("interaction_receipt_mismatch")
                if _artifact_read(fd, names[0]) != playable:
                    raise CanonError("interaction_playable_mismatch")
                if _artifact_read(fd, names[1]) != recipe:
                    raise CanonError("interaction_recipe_mismatch")
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
                sources = self._sources(fd, world_id)
                session = validate_session(strict_json(self.worlds._read(
                    fd, SessionStore._name(world_id, slot))), sources[0])
                return {"slot": slot, "player": replay_interaction(*sources, session)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
