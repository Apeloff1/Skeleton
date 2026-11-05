"""Original interactive NPC dialogue with canonical world-choice handoff.

Conversations are finite directed graphs. Every reachable response must lead
to an authored canonical world choice, with no loops or dead ends. Dialogue
session choices are committed under the same world lock as saved gameplay.
"""
from __future__ import annotations

from hashlib import sha256
import base64
import html
import os
from typing import Any

from .bundle import _artifact_read
from .cast import validate_cast
from .session import SessionStore, apply_choice, validate_session
from .timeline import _reachable_flags
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.dialogue_graph.v1"
RECEIPT_SCHEMA = "jeeves.world.dialogue_graph_receipt.v1"
MAX_CONVERSATIONS = 32
MAX_NODES = 128
MAX_RESPONSES = 8
MAX_DEPTH = 128


def validate_dialogues(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    data = _keys(source, {
        "schema", "world_id", "world_digest", "cast_digest",
        "prompt", "conversations", "approved", "review_note",
    })
    if data["schema"] != SCHEMA:
        raise CanonError("dialogue_schema_mismatch")
    if (data["world_id"] != world["id"] or
            data["world_digest"] != digest(world) or
            data["cast_digest"] != digest(cast)):
        raise CanonError("dialogue_source_lease_mismatch")
    _text(data["prompt"], "prompt", 4096)
    if type(data["approved"]) is not bool:
        raise CanonError("dialogue_invalid_approval")
    if data["approved"]:
        _text(data["review_note"], "review_note")
    elif data["review_note"] != "":
        raise CanonError("dialogue_unreviewed_note")
    actors = {a["id"]: a for a in cast["characters"]}
    scenes = {s["id"] for s in world["scenes"]}
    choices = {c["id"]: c for c in world["choices"]}
    reachable = _reachable_flags(world)
    conversations = _list(data["conversations"], "conversations", MAX_CONVERSATIONS)
    if not conversations:
        raise CanonError("dialogue_empty")
    conversation_ids: set[str] = set()
    for conversation in conversations:
        _keys(conversation, {"id", "actor", "scene", "start", "nodes"})
        cid = _id(conversation["id"], "conversation.id")
        if cid in conversation_ids:
            raise CanonError("dialogue_duplicate_conversation", cid)
        conversation_ids.add(cid)
        actor = _id(conversation["actor"], "conversation.actor")
        scene = _id(conversation["scene"], "conversation.scene")
        if scene not in scenes or actor not in actors or scene not in actors[actor]["scenes"]:
            raise CanonError("dialogue_actor_absent", cid)
        nodes = _list(conversation["nodes"], "nodes", MAX_NODES)
        if not nodes:
            raise CanonError("dialogue_empty_nodes")
        by_id: dict[str, Any] = {}
        for node in nodes:
            _keys(node, {"id", "text", "responses"})
            nid = _id(node["id"], "node.id")
            if nid in by_id:
                raise CanonError("dialogue_duplicate_node", nid)
            by_id[nid] = node
            _text(node["text"], "node.text", 4096)
            responses = _list(node["responses"], "responses", MAX_RESPONSES)
            if not responses:
                raise CanonError("dialogue_dead_end", nid)
            response_ids: set[str] = set()
            for response in responses:
                _keys(response, {"id", "label", "next_node", "world_choice"})
                rid = _id(response["id"], "response.id")
                if rid in response_ids:
                    raise CanonError("dialogue_duplicate_response", rid)
                response_ids.add(rid)
                _text(response["label"], "response.label", 1000)
                target, choice = response["next_node"], response["world_choice"]
                if (target is None) == (choice is None):
                    raise CanonError("dialogue_invalid_response_target", rid)
                if target is not None:
                    _id(target, "response.next_node")
                else:
                    _id(choice, "response.world_choice")
                    if choice not in choices or choices[choice]["from"] != scene:
                        raise CanonError("dialogue_invalid_world_choice", rid)
                    if not any(set(choices[choice]["requires"]) <= flags
                               for flags in reachable.get(scene, ())):
                        raise CanonError("dialogue_unearned_world_choice", rid)
            if responses != sorted(responses, key=lambda r: r["id"]):
                raise CanonError("dialogue_response_order", nid)
        if nodes != sorted(nodes, key=lambda n: n["id"]):
            raise CanonError("dialogue_node_order", cid)
        start = _id(conversation["start"], "conversation.start")
        if start not in by_id:
            raise CanonError("dialogue_unknown_start", cid)
        seen: set[str] = set()
        visiting: set[str] = set()
        def visit(node_id: str, depth: int) -> None:
            if depth > MAX_DEPTH or node_id in visiting:
                raise CanonError("dialogue_cycle_or_depth", cid)
            if node_id in seen:
                return
            if node_id not in by_id:
                raise CanonError("dialogue_unknown_node", node_id)
            visiting.add(node_id)
            for response in by_id[node_id]["responses"]:
                if response["next_node"] is not None:
                    visit(response["next_node"], depth + 1)
            visiting.remove(node_id)
            seen.add(node_id)
        visit(start, 0)
        if seen != set(by_id):
            raise CanonError("dialogue_unreachable_nodes", cid)
    if conversations != sorted(conversations, key=lambda c: c["id"]):
        raise CanonError("dialogue_conversation_order")
    if len(canonical(data)) > 524288:
        raise CanonError("dialogue_source_too_large")
    return data


def prove_dialogues(source: Any, world: Any, cast: Any) -> dict[str, Any]:
    data = validate_dialogues(source, world, cast)
    witnesses = {}
    total_nodes = 0
    total_responses = 0
    for conversation in data["conversations"]:
        by_id = {n["id"]: n for n in conversation["nodes"]}
        terminal: dict[str, list[str]] = {}
        stack = [(conversation["start"], ())]
        while stack:
            node_id, path = stack.pop()
            total_nodes += 1
            for response in by_id[node_id]["responses"]:
                total_responses += 1
                route = path + (response["id"],)
                if response["world_choice"] is not None:
                    terminal.setdefault(response["world_choice"], list(route))
                else:
                    stack.append((response["next_node"], route))
                if total_responses > MAX_CONVERSATIONS * MAX_NODES * MAX_RESPONSES:
                    raise CanonError("dialogue_proof_budget_exhausted")
        if not terminal:
            raise CanonError("dialogue_no_world_handoff", conversation["id"])
        witnesses[conversation["id"]] = {
            choice: terminal[choice] for choice in sorted(terminal)}
    return {
        "schema": "jeeves.world.dialogue_graph_proof.v1",
        "world_digest": digest(world), "cast_digest": digest(cast),
        "dialogue_digest": digest(data), "node_visits": total_nodes,
        "response_visits": total_responses,
        "world_choice_witnesses": witnesses,
    }


def replay_dialogue(source: Any, world: Any, cast: Any,
                    conversation_id: str, responses: Any) -> dict[str, Any]:
    validate_dialogues(source, world, cast)
    _id(conversation_id, "conversation_id")
    if type(responses) is not list or len(responses) > MAX_DEPTH:
        raise CanonError("dialogue_invalid_trace")
    matches = [c for c in source["conversations"] if c["id"] == conversation_id]
    if len(matches) != 1:
        raise CanonError("dialogue_unknown_conversation")
    conversation = matches[0]
    nodes = {n["id"]: n for n in conversation["nodes"]}
    current = conversation["start"]
    path = []
    choice = None
    for response_id in responses:
        _id(response_id, "response_id")
        found = [r for r in nodes[current]["responses"] if r["id"] == response_id]
        if len(found) != 1:
            raise CanonError("dialogue_invalid_transition")
        response = found[0]
        path.append({"node": current, "response": response_id})
        if response["world_choice"] is not None:
            choice = response["world_choice"]
            if len(path) != len(responses):
                raise CanonError("dialogue_after_handoff")
            break
        current = response["next_node"]
    return {
        "schema": "jeeves.world.dialogue_graph_replay.v1",
        "world_id": world["id"], "dialogue_digest": digest(source),
        "conversation": conversation_id, "scene": conversation["scene"],
        "actor": conversation["actor"], "current_node": (
            None if choice is not None else current),
        "world_choice": choice, "trace": path,
    }


def propose_dialogue(world: Any, cast: Any, *, prompt: str,
                     conversation_id: str, actor: str, scene: str,
                     text: str, response_id: str, label: str,
                     world_choice: str) -> dict[str, Any]:
    _text(prompt, "prompt", 4096)
    source = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(cast),
        "prompt": prompt,
        "conversations": [{
            "id": conversation_id, "actor": actor, "scene": scene,
            "start": "opening", "nodes": [{
                "id": "opening", "text": text,
                "responses": [{
                    "id": response_id, "label": label,
                    "next_node": None, "world_choice": world_choice,
                }],
            }],
        }],
        "approved": False, "review_note": "",
    }
    prove_dialogues(source, world, cast)
    return source


def edit_dialogue(source: Any, world: Any, cast: Any, operation: Any) -> dict[str, Any]:
    validate_dialogues(source, world, cast)
    candidate = strict_json(canonical(source))
    top = _keys(operation, {"action", "value"})
    ops = _list(top["value"], "batch", 64) if top["action"] == "batch" else [top]
    if not ops:
        raise CanonError("dialogue_empty_edit")
    for op in ops:
        item = _keys(op, {"action", "value"})
        action, value = item["action"], item["value"]
        if action == "upsert_conversation":
            _keys(value, {"id", "actor", "scene", "start", "nodes"})
            candidate["conversations"] = [
                c for c in candidate["conversations"] if c["id"] != value["id"]
            ] + [value]
        elif action == "upsert_node":
            _keys(value, {"conversation", "node"})
            _keys(value["node"], {"id", "text", "responses"})
            matches = [c for c in candidate["conversations"]
                       if c["id"] == value["conversation"]]
            if len(matches) != 1:
                raise CanonError("dialogue_unknown_conversation")
            nodes = matches[0]["nodes"]
            nodes[:] = [n for n in nodes if n["id"] != value["node"]["id"]] + [
                value["node"]]
            nodes.sort(key=lambda n: n["id"])
        elif action == "remove_conversation":
            _keys(value, {"id"})
            before = len(candidate["conversations"])
            candidate["conversations"] = [
                c for c in candidate["conversations"] if c["id"] != value["id"]]
            if len(candidate["conversations"]) != before - 1:
                raise CanonError("dialogue_unknown_conversation")
        else:
            raise CanonError("dialogue_invalid_edit")
    candidate["conversations"].sort(key=lambda c: c["id"])
    candidate["approved"] = False
    candidate["review_note"] = ""
    prove_dialogues(candidate, world, cast)
    return candidate


def approve_dialogue(source: Any, world: Any, cast: Any, note: str) -> dict[str, Any]:
    _text(note, "review_note")
    prove_dialogues(source, world, cast)
    if cast["approved"] is not True:
        raise CanonError("dialogue_cast_review_required")
    candidate = strict_json(canonical(source))
    candidate["approved"] = True
    candidate["review_note"] = note
    prove_dialogues(candidate, world, cast)
    return candidate


PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("dialogue-data").textContent);
const world = data.world, cast = data.cast, dialogue = data.dialogue;
const root = document.getElementById("play");
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
let scene, flags, trace, active, nodeId;
function node(tag, value) {
  const item = document.createElement(tag); item.textContent = value; return item;
}
function button(label, fn) {
  const item = node("button", label);
  item.type = "button"; item.addEventListener("click", fn); root.append(item);
}
function reset() {
  scene = world.start; flags = new Set(); trace = []; active = null;
  nodeId = null; render();
}
function advance(choice) {
  choice.grants.forEach(flag => flags.add(flag));
  trace.push(choice.id); scene = choice.to; active = null; nodeId = null;
  render();
}
function render() {
  root.replaceChildren();
  const here = scenes.get(scene);
  root.append(node("h1", here.title), node("p", here.narrative));
  if (active) {
    const current = active.nodes.find(n => n.id === nodeId);
    const actor = cast.characters.find(a => a.id === active.actor);
    root.append(node("h2", actor.name), node("p", current.text));
    for (const response of current.responses) {
      if (response.world_choice !== null) {
        const choice = world.choices.find(c => c.id === response.world_choice);
        if (choice.requires.every(f => flags.has(f)))
          button(response.label, () => advance(choice));
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
    for (const choice of world.choices.filter(c => c.from === scene &&
      c.requires.every(f => flags.has(f))))
      button(choice.label, () => advance(choice));
  }
  button("Restart", reset);
}
reset();
""".strip()


def compile_dialogue(source: Any, world: Any, cast: Any) -> tuple[dict[str, Any], bytes]:
    if source["approved"] is not True or cast["approved"] is not True:
        raise CanonError("dialogue_review_required")
    proof = prove_dialogues(source, world, cast)
    recipe = {
        "schema": "jeeves.world.dialogue_graph_engine_recipe.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "cast_digest": digest(cast), "dialogue_digest": digest(source),
        "conversations": source["conversations"], "proof": proof,
        "qualification": "reviewed_original_source_not_device_certified",
    }
    embedded = canonical({"world": world, "cast": cast, "dialogue": source}).decode(
        "utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(PLAYER_JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Original dialogue: " + html.escape(world["id"]) +
        '</title></head><body><main id="play" aria-live="polite"></main>'
        '<script id="dialogue-data" type="application/json">' + embedded +
        "</script><script>" + PLAYER_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("dialogue_playable_too_large")
    return recipe, page


class DialogueStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".dialogue.json", world_id + ".dialogue.playable.html",
                world_id + ".dialogue.engine.json", world_id + ".dialogue.receipt.json")

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
            raise CanonError("dialogue_world_identity_mismatch")
        cast = strict_json(self.worlds._read(fd, world_id + ".cast.json"))
        validate_cast(cast, world)
        return world, cast

    def _source(self, fd: int, world_id: str, world: Any, cast: Any) -> Any:
        source = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_dialogues(source, world, cast)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                return propose_dialogue(*self._sources(fd, world_id), **kwargs)
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
                return {"dialogue": source, "proof": prove_dialogues(source, world, cast)}
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
                prove_dialogues(source, world, cast)
                if source["approved"]:
                    raise CanonError("dialogue_approval_requires_review")
                try:
                    previous = self._source(fd, world_id, world, cast)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    previous = None
                if create:
                    if previous is not None or expected_digest is not None:
                        raise CanonError("dialogue_already_exists")
                elif previous is None or digest(previous) != expected_digest:
                    raise CanonError("dialogue_stale_edit")
                self.worlds._write(fd, self._names(world_id)[0], canonical(source))
                return digest(source)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def edit(self, world_id: str, expected_digest: str, operation: Any) -> str:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("dialogue_stale_edit")
                updated = edit_dialogue(source, world, cast, operation)
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
                    raise CanonError("dialogue_stale_edit")
                approved = approve_dialogue(source, world, cast, note)
                self.worlds._write(fd, self._names(world_id)[0], canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any, cast: Any):
        recipe, playable = compile_dialogue(source, world, cast)
        manifest = canonical(recipe)
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cast_digest": digest(cast),
            "dialogue_digest": digest(source), "proof_digest": digest(recipe["proof"]),
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
                    raise CanonError("dialogue_stale_edit")
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
                    raise CanonError("dialogue_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("dialogue_playable_mismatch")
                if _artifact_read(fd, names[2]) != manifest:
                    raise CanonError("dialogue_recipe_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str, conversation: str,
               responses: Any) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if source["approved"] is not True or cast["approved"] is not True:
                    raise CanonError("dialogue_review_required")
                session = validate_session(strict_json(self.worlds._read(
                    fd, SessionStore._name(world_id, slot))), world)
                replay = replay_dialogue(source, world, cast, conversation, responses)
                if session["scene"] != replay["scene"]:
                    raise CanonError("dialogue_wrong_scene")
                return {"slot": slot, "session_digest": digest(session),
                        "dialogue": replay}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def choose(self, world_id: str, slot: str, conversation: str, responses: Any,
               *, expected_session_digest: str, expected_dialogue_digest: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if digest(source) != expected_dialogue_digest:
                    raise CanonError("dialogue_stale_source")
                if source["approved"] is not True or cast["approved"] is not True:
                    raise CanonError("dialogue_review_required")
                session_name = SessionStore._name(world_id, slot)
                session = validate_session(strict_json(self.worlds._read(
                    fd, session_name)), world)
                if digest(session) != expected_session_digest:
                    raise CanonError("dialogue_stale_session")
                replay = replay_dialogue(source, world, cast, conversation, responses)
                if session["scene"] != replay["scene"] or replay["world_choice"] is None:
                    raise CanonError("dialogue_handoff_not_ready")
                updated = apply_choice(session, world, replay["world_choice"])
                self.worlds._write(fd, session_name, canonical(updated))
                return {"slot": slot, "session_digest": digest(updated),
                        "dialogue": replay, "scene": updated["scene"],
                        "ending": updated["ending"]}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .dialogue_graph_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                source = self._source(fd, world_id, world, cast)
                if digest(source) != expected_digest:
                    raise CanonError("dialogue_stale_edit")
                content = render_editor(source, world, cast)
                name = world_id + ".dialogue.editor.html"
                self.worlds._write(fd, name, content)
                return {"html_file": name, "html_sha256": sha256(content).hexdigest(),
                        "dialogue_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
