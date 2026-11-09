"""Original reviewed localized branching NPC conversations.

Locale editions cover every authored dialogue node and response exactly.
No implicit machine translation, silent fallback or unreviewed publication.
"""
from __future__ import annotations

from hashlib import sha256
import base64
import html
import os
import re
from typing import Any

from .bundle import _artifact_read
from .cast import validate_cast
from .dialogue_graph import prove_dialogues, replay_dialogue
from .session import SessionStore, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.dialogue_localization.v1"
RECEIPT_SCHEMA = "jeeves.world.dialogue_localization_receipt.v1"
LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
MAX_LOCALES = 12


def _locale(value: Any) -> str:
    if type(value) is not str or LOCALE_RE.fullmatch(value) is None:
        raise CanonError("dialogue_locale_invalid_tag")
    return value


def validate_dialogue_locales(source: Any, world: Any, cast: Any,
                              dialogue: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    prove_dialogues(dialogue, world, cast)
    data = _keys(source, {
        "schema", "world_id", "world_digest", "cast_digest",
        "dialogue_digest", "prompt", "locales", "approved", "review_note",
    })
    if data["schema"] != SCHEMA:
        raise CanonError("dialogue_locale_schema_mismatch")
    if (data["world_id"] != world["id"] or
            data["world_digest"] != digest(world) or
            data["cast_digest"] != digest(cast) or
            data["dialogue_digest"] != digest(dialogue)):
        raise CanonError("dialogue_locale_source_lease_mismatch")
    _text(data["prompt"], "prompt", 4096)
    if type(data["approved"]) is not bool:
        raise CanonError("dialogue_locale_invalid_approval")
    if data["approved"]:
        _text(data["review_note"], "review_note")
    elif data["review_note"] != "":
        raise CanonError("dialogue_locale_unreviewed_note")
    locales = _list(data["locales"], "locales", MAX_LOCALES)
    if not locales:
        raise CanonError("dialogue_locale_empty")
    original = {c["id"]: c for c in dialogue["conversations"]}
    seen: set[str] = set()
    for edition in locales:
        _keys(edition, {"tag", "conversations"})
        tag = _locale(edition["tag"])
        if tag in seen:
            raise CanonError("dialogue_locale_duplicate_tag", tag)
        seen.add(tag)
        conversations = _list(edition["conversations"], "conversations", 32)
        if {c.get("id") for c in conversations if type(c) is dict} != set(original):
            raise CanonError("dialogue_locale_incomplete_conversations", tag)
        if len(conversations) != len(original):
            raise CanonError("dialogue_locale_duplicate_conversation", tag)
        for conversation in conversations:
            _keys(conversation, {"id", "nodes"})
            cid = _id(conversation["id"], "conversation.id")
            source_nodes = {n["id"]: n for n in original[cid]["nodes"]}
            nodes = _list(conversation["nodes"], "nodes", 128)
            if (len(nodes) != len(source_nodes) or
                    {n.get("id") for n in nodes if type(n) is dict} != set(source_nodes)):
                raise CanonError("dialogue_locale_incomplete_nodes", cid)
            for node in nodes:
                _keys(node, {"id", "text", "responses"})
                nid = _id(node["id"], "node.id")
                _text(node["text"], "node.text", 4096)
                original_responses = {
                    r["id"] for r in source_nodes[nid]["responses"]}
                responses = _list(node["responses"], "responses", 8)
                if (len(responses) != len(original_responses) or
                        {r.get("id") for r in responses if type(r) is dict}
                        != original_responses):
                    raise CanonError("dialogue_locale_incomplete_responses", nid)
                for response in responses:
                    _keys(response, {"id", "label"})
                    _id(response["id"], "response.id")
                    _text(response["label"], "response.label", 1000)
                if responses != sorted(responses, key=lambda r: r["id"]):
                    raise CanonError("dialogue_locale_response_order", nid)
            if nodes != sorted(nodes, key=lambda n: n["id"]):
                raise CanonError("dialogue_locale_node_order", cid)
        if conversations != sorted(conversations, key=lambda c: c["id"]):
            raise CanonError("dialogue_locale_conversation_order", tag)
    if locales != sorted(locales, key=lambda l: l["tag"]):
        raise CanonError("dialogue_locale_order")
    if len(canonical(data)) > 524288:
        raise CanonError("dialogue_locale_source_too_large")
    return data


def prove_dialogue_locales(source: Any, world: Any, cast: Any,
                           dialogue: Any) -> dict[str, Any]:
    data = validate_dialogue_locales(source, world, cast, dialogue)
    return {
        "schema": "jeeves.world.dialogue_localization_proof.v1",
        "world_digest": digest(world), "cast_digest": digest(cast),
        "dialogue_digest": digest(dialogue), "localization_digest": digest(data),
        "locales": [e["tag"] for e in data["locales"]],
        "conversations_per_locale": len(dialogue["conversations"]),
        "nodes_per_locale": sum(len(c["nodes"]) for c in dialogue["conversations"]),
        "responses_per_locale": sum(
            len(n["responses"]) for c in dialogue["conversations"]
            for n in c["nodes"]),
        "qualification": "coverage_proven_language_quality_requires_human_review",
    }


def propose_dialogue_locale(world: Any, cast: Any, dialogue: Any, *,
                            prompt: str, tag: str, conversation_id: str,
                            node_id: str, text: str, response_id: str,
                            label: str) -> dict[str, Any]:
    _text(prompt, "prompt", 4096)
    _locale(tag)
    _text(text, "text", 4096)
    _text(label, "label", 1000)
    conversations = []
    for conversation in dialogue["conversations"]:
        nodes = []
        for node in conversation["nodes"]:
            responses = [{
                "id": r["id"],
                "label": label if (
                    conversation["id"] == conversation_id and
                    node["id"] == node_id and r["id"] == response_id
                ) else r["label"],
            } for r in node["responses"]]
            nodes.append({
                "id": node["id"],
                "text": text if (
                    conversation["id"] == conversation_id and
                    node["id"] == node_id
                ) else node["text"],
                "responses": responses,
            })
        conversations.append({"id": conversation["id"], "nodes": nodes})
    if not any(c["id"] == conversation_id and
               any(n["id"] == node_id and
                   any(r["id"] == response_id for r in n["responses"])
                   for n in c["nodes"]) for c in dialogue["conversations"]):
        raise CanonError("dialogue_locale_unknown_target")
    source = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(cast),
        "dialogue_digest": digest(dialogue), "prompt": prompt,
        "locales": [{"tag": tag, "conversations": conversations}],
        "approved": False, "review_note": "",
    }
    prove_dialogue_locales(source, world, cast, dialogue)
    return source


def edit_dialogue_locale(source: Any, world: Any, cast: Any,
                         dialogue: Any, operation: Any) -> dict[str, Any]:
    validate_dialogue_locales(source, world, cast, dialogue)
    candidate = strict_json(canonical(source))
    op = _keys(operation, {"action", "value"})
    action, value = op["action"], op["value"]
    if action == "upsert_locale":
        _keys(value, {"tag", "conversations"})
        candidate["locales"] = [
            e for e in candidate["locales"] if e["tag"] != value["tag"]] + [value]
    elif action == "replace_node":
        _keys(value, {"tag", "conversation", "node"})
        _keys(value["node"], {"id", "text", "responses"})
        editions = [e for e in candidate["locales"] if e["tag"] == value["tag"]]
        if len(editions) != 1:
            raise CanonError("dialogue_locale_unknown_tag")
        conversations = [c for c in editions[0]["conversations"]
                         if c["id"] == value["conversation"]]
        if len(conversations) != 1:
            raise CanonError("dialogue_locale_unknown_conversation")
        nodes = conversations[0]["nodes"]
        if not any(n["id"] == value["node"]["id"] for n in nodes):
            raise CanonError("dialogue_locale_unknown_node")
        nodes[:] = [n for n in nodes if n["id"] != value["node"]["id"]] + [
            value["node"]]
        nodes.sort(key=lambda n: n["id"])
    else:
        raise CanonError("dialogue_locale_invalid_edit")
    candidate["locales"].sort(key=lambda e: e["tag"])
    candidate["approved"] = False
    candidate["review_note"] = ""
    prove_dialogue_locales(candidate, world, cast, dialogue)
    return candidate


def approve_dialogue_locale(source: Any, world: Any, cast: Any,
                            dialogue: Any, note: str) -> dict[str, Any]:
    _text(note, "review_note")
    prove_dialogue_locales(source, world, cast, dialogue)
    if cast["approved"] is not True or dialogue["approved"] is not True:
        raise CanonError("dialogue_locale_review_required")
    candidate = strict_json(canonical(source))
    candidate["approved"] = True
    candidate["review_note"] = note
    prove_dialogue_locales(candidate, world, cast, dialogue)
    return candidate


def localized_dialogue(source: Any, world: Any, cast: Any, dialogue: Any,
                       conversation: str, responses: Any, tag: str) -> dict[str, Any]:
    validate_dialogue_locales(source, world, cast, dialogue)
    _locale(tag)
    edition = next((e for e in source["locales"] if e["tag"] == tag), None)
    if edition is None:
        raise CanonError("dialogue_locale_unknown_tag")
    replay = replay_dialogue(dialogue, world, cast, conversation, responses)
    convo = next(c for c in edition["conversations"] if c["id"] == conversation)
    nodes = {n["id"]: n for n in convo["nodes"]}
    current = replay["current_node"]
    return {
        "schema": "jeeves.world.localized_dialogue_replay.v1",
        "world_id": world["id"], "locale": tag,
        "dialogue_digest": digest(dialogue),
        "localization_digest": digest(source), "replay": replay,
        "localized_node": nodes[current] if current is not None else None,
        "localized_trace": [{
            "node": item["node"], "response": item["response"],
            "label": next(r["label"] for r in nodes[item["node"]]["responses"]
                          if r["id"] == item["response"]),
        } for item in replay["trace"]],
    }


PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("locale-data").textContent);
const world = data.world, dialogue = data.dialogue, local = data.localization;
const root = document.getElementById("play");
let edition = local.locales[0], active = null, nodeId = null;
let scene, flags;
function node(tag, value) {
  const item = document.createElement(tag); item.textContent = value; return item;
}
function button(label, fn) {
  const item = node("button", label); item.type = "button";
  item.addEventListener("click", fn); root.append(item);
}
function reset() {
  scene = world.start; flags = new Set(); active = null; nodeId = null; render();
}
function render() {
  root.replaceChildren();
  const selector = document.createElement("select");
  for (const item of local.locales) {
    const option = document.createElement("option");
    option.value = item.tag; option.textContent = item.tag;
    option.selected = item.tag === edition.tag; selector.append(option);
  }
  selector.addEventListener("change", () => {
    edition = local.locales.find(e => e.tag === selector.value); render();
  });
  root.append(node("label", "Dialogue language: "), selector);
  const here = world.scenes.find(s => s.id === scene);
  root.append(node("h1", here.title), node("p", here.narrative));
  if (active) {
    const translated = edition.conversations.find(c => c.id === active.id);
    const current = translated.nodes.find(n => n.id === nodeId);
    root.append(node("h2", current.text));
    const original = active.nodes.find(n => n.id === nodeId);
    for (const response of original.responses) {
      const label = current.responses.find(r => r.id === response.id).label;
      if (response.world_choice !== null) {
        const choice = world.choices.find(c => c.id === response.world_choice);
        if (choice.requires.every(f => flags.has(f)))
          button(label, () => {
            choice.grants.forEach(f => flags.add(f));
            scene = choice.to; active = null; nodeId = null; render();
          });
      } else {
        button(label, () => {nodeId = response.next_node; render();});
      }
    }
    button("Leave conversation", () => {active = null; render();});
    return;
  }
  const ending = world.endings.find(e => e.scene === scene);
  if (ending) root.append(node("h2", "Ending: " + ending.label));
  else {
    for (const conversation of dialogue.conversations.filter(c => c.scene === scene))
      button("Talk: " + conversation.id, () => {
        active = conversation; nodeId = conversation.start; render();
      });
    for (const choice of world.choices.filter(c => c.from === scene &&
      c.requires.every(f => flags.has(f))))
      button(choice.label, () => {
        choice.grants.forEach(f => flags.add(f));
        scene = choice.to; render();
      });
  }
  button("Restart", reset);
}
reset();
""".strip()


def compile_dialogue_locales(source: Any, world: Any, cast: Any,
                             dialogue: Any) -> tuple[dict[str, Any], bytes]:
    if not all(s["approved"] is True for s in (cast, dialogue, source)):
        raise CanonError("dialogue_locale_review_required")
    proof = prove_dialogue_locales(source, world, cast, dialogue)
    recipe = {
        "schema": "jeeves.world.dialogue_localization_engine_recipe.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "cast_digest": digest(cast), "dialogue_digest": digest(dialogue),
        "localization_digest": digest(source), "locales": source["locales"],
        "proof": proof,
        "qualification": "reviewed_language_source_not_device_certified",
    }
    embedded = canonical({
        "world": world, "dialogue": dialogue, "localization": source,
    }).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(PLAYER_JS.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        "<title>Original dialogue locales: " + html.escape(world["id"]) +
        '</title></head><body><main id="play" aria-live="polite"></main>'
        '<script id="locale-data" type="application/json">' + embedded +
        "</script><script>" + PLAYER_JS + "</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("dialogue_locale_playable_too_large")
    return recipe, page


class DialogueLocaleStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".dialogue.locales.json",
                world_id + ".dialogue.locales.playable.html",
                world_id + ".dialogue.locales.engine.json",
                world_id + ".dialogue.locales.receipt.json")

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _sources(self, fd: int, world_id: str):
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("dialogue_locale_world_identity_mismatch")
        cast = strict_json(self.worlds._read(fd, world_id + ".cast.json"))
        validate_cast(cast, world)
        dialogue = strict_json(self.worlds._read(fd, world_id + ".dialogue.json"))
        prove_dialogues(dialogue, world, cast)
        return world, cast, dialogue

    def _source(self, fd: int, world_id: str, sources: Any):
        data = strict_json(self.worlds._read(fd, self._names(world_id)[0]))
        return validate_dialogue_locales(data, *sources)

    def propose(self, world_id: str, **kwargs: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                return propose_dialogue_locale(
                    *self._sources(fd, world_id), **kwargs)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                data = self._source(fd, world_id, sources)
                return {"localization": data,
                        "proof": prove_dialogue_locales(data, *sources)}
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
                sources = self._sources(fd, world_id)
                prove_dialogue_locales(source, *sources)
                if source["approved"]:
                    raise CanonError("dialogue_locale_approval_requires_review")
                try:
                    previous = self._source(fd, world_id, sources)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    previous = None
                if create:
                    if previous is not None or expected_digest is not None:
                        raise CanonError("dialogue_locale_already_exists")
                elif previous is None or digest(previous) != expected_digest:
                    raise CanonError("dialogue_locale_stale_edit")
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
                sources = self._sources(fd, world_id)
                data = self._source(fd, world_id, sources)
                if digest(data) != expected_digest:
                    raise CanonError("dialogue_locale_stale_edit")
                updated = edit_dialogue_locale(data, *sources, operation)
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
                sources = self._sources(fd, world_id)
                data = self._source(fd, world_id, sources)
                if digest(data) != expected_digest:
                    raise CanonError("dialogue_locale_stale_edit")
                approved = approve_dialogue_locale(data, *sources, note)
                self.worlds._write(fd, self._names(world_id)[0], canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, data: Any, sources: Any):
        recipe, playable = compile_dialogue_locales(data, *sources)
        manifest = canonical(recipe)
        names = self._names(sources[0]["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": sources[0]["id"],
            "world_digest": digest(sources[0]),
            "cast_digest": digest(sources[1]),
            "dialogue_digest": digest(sources[2]),
            "localization_digest": digest(data),
            "proof_digest": digest(recipe["proof"]),
            "artifacts": {
                names[1]: sha256(playable).hexdigest(),
                names[2]: sha256(manifest).hexdigest(),
            },
            "qualification": "reviewed_language_source_not_release_certified",
        }
        return receipt, playable, manifest

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                data = self._source(fd, world_id, sources)
                if digest(data) != expected_digest:
                    raise CanonError("dialogue_locale_stale_edit")
                receipt, playable, manifest = self._outputs(data, sources)
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
                sources = self._sources(fd, world_id)
                data = self._source(fd, world_id, sources)
                receipt, playable, manifest = self._outputs(data, sources)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[3])) != receipt:
                    raise CanonError("dialogue_locale_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("dialogue_locale_playable_mismatch")
                if _artifact_read(fd, names[2]) != manifest:
                    raise CanonError("dialogue_locale_recipe_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str, conversation: str,
               responses: Any, tag: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                data = self._source(fd, world_id, sources)
                if not all(s["approved"] is True for s in
                           (sources[1], sources[2], data)):
                    raise CanonError("dialogue_locale_review_required")
                session = validate_session(strict_json(self.worlds._read(
                    fd, SessionStore._name(world_id, slot))), sources[0])
                replay = localized_dialogue(
                    data, *sources, conversation, responses, tag)
                if session["scene"] != replay["replay"]["scene"]:
                    raise CanonError("dialogue_locale_wrong_scene")
                return {"slot": slot, "session_digest": digest(session),
                        "player": replay}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .dialogue_localization_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                data = self._source(fd, world_id, sources)
                if digest(data) != expected_digest:
                    raise CanonError("dialogue_locale_stale_edit")
                content = render_editor(data, *sources)
                name = world_id + ".dialogue.locales.editor.html"
                self.worlds._write(fd, name, content)
                return {"html_file": name, "html_sha256": sha256(content).hexdigest(),
                        "localization_digest": digest(data)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
