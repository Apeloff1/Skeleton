"""Reviewed NPC knowledge provenance, dialogue spoiler proof and playable handoff.

Facts are authored, never inferred by an LLM. An explicit narrator disclosure is
an author-controlled reveal, not an authenticated external information source.
The proof covers declared fact-bearing lines; unannotated prose is not analyzed.
"""
from __future__ import annotations

import base64
from collections import deque
from hashlib import sha256
import html
import os
from typing import Any

from .cast import validate_cast
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text, canonical,
    digest, prove, strict_json,
)

SCHEMA = "jeeves.world.knowledge.v1"
HANDOFF_SCHEMA = "jeeves.world.knowledge_handoff.v1"
RECEIPT_SCHEMA = "jeeves.world.knowledge_receipt.v1"
MAX_FACTS = 64
MAX_DISCLOSURES = 256
MAX_CLAIMS = 256
MAX_STATES = 2048
MAX_TRACE = 512
MAX_BYTES = 524288


def _ids(value: Any, field: str, limit: int) -> list[str]:
    result = [_id(item, field) for item in _list(value, field, limit)]
    if result != sorted(set(result)):
        raise CanonError("knowledge_ids_not_canonical", field)
    return result


def validate_knowledge(data: Any, world: Any, cast: Any) -> dict[str, Any]:
    world_proof = prove(world)
    validate_cast(cast, world)
    obj = _keys(data, {
        "schema", "world_id", "world_digest", "cast_digest", "facts",
        "disclosures", "claims", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA:
        raise CanonError("knowledge_schema_mismatch")
    if (obj["world_id"] != world["id"] or
            obj["world_digest"] != world_proof.source_digest or
            obj["cast_digest"] != digest(cast)):
        raise CanonError("knowledge_source_lease_mismatch")
    if type(obj["approved"]) is not bool:
        raise CanonError("knowledge_approval_invalid")
    _text(obj["review_note"], "review_note", 512)
    actors = {actor["id"]: actor for actor in cast["characters"]}
    allowed = set(actors) | {"player"}
    facts = _list(obj["facts"], "facts", MAX_FACTS)
    if not facts:
        raise CanonError("knowledge_empty_facts")
    fact_ids: set[str] = set()
    for fact in facts:
        _keys(fact, {"id", "title", "detail", "initial_knowers"})
        fid = _id(fact["id"], "fact.id")
        if fid in fact_ids:
            raise CanonError("knowledge_duplicate_fact", fid)
        fact_ids.add(fid)
        _text(fact["title"], "fact.title", 200)
        _text(fact["detail"], "fact.detail", 4096)
        if not set(_ids(fact["initial_knowers"], "initial_knowers", 129)) <= allowed:
            raise CanonError("knowledge_unknown_initial_knower", fid)
    choices = {choice["id"]: choice for choice in world["choices"]}
    disclosures = _list(obj["disclosures"], "disclosures", MAX_DISCLOSURES)
    seen_disclosures: set[str] = set()
    for item in disclosures:
        _keys(item, {"id", "fact", "choice", "speaker", "recipients"})
        did = _id(item["id"], "disclosure.id")
        if did in seen_disclosures:
            raise CanonError("knowledge_duplicate_disclosure", did)
        seen_disclosures.add(did)
        if _id(item["fact"], "disclosure.fact") not in fact_ids:
            raise CanonError("knowledge_unknown_fact", did)
        choice_id = _id(item["choice"], "disclosure.choice")
        if choice_id not in choices:
            raise CanonError("knowledge_unknown_choice", did)
        speaker = _id(item["speaker"], "disclosure.speaker")
        if speaker != "narrator":
            if speaker not in actors:
                raise CanonError("knowledge_unknown_speaker", did)
            if choices[choice_id]["from"] not in actors[speaker]["scenes"]:
                raise CanonError("knowledge_absent_speaker", did)
        recipients = _ids(item["recipients"], "disclosure.recipients", 129)
        if not recipients or not set(recipients) <= allowed:
            raise CanonError("knowledge_invalid_recipients", did)
    lines = {line["id"]: line for line in cast["lines"]}
    claims = _list(obj["claims"], "claims", MAX_CLAIMS)
    claim_ids: set[str] = set()
    for item in claims:
        _keys(item, {"line", "fact"})
        lid = _id(item["line"], "claim.line")
        if lid in claim_ids:
            raise CanonError("knowledge_duplicate_claim", lid)
        claim_ids.add(lid)
        if lid not in lines or _id(item["fact"], "claim.fact") not in fact_ids:
            raise CanonError("knowledge_unknown_claim_reference", lid)
    if len(canonical(obj)) > MAX_BYTES:
        raise CanonError("knowledge_source_too_large")
    return obj


def propose_knowledge(
    world: Any, cast: Any, *, prompt: str, fact_id: str,
    title: str, detail: str, choice: str, speaker: str,
    recipient: str = "player",
) -> dict[str, Any]:
    """Turn an original author brief into a review-required typed reveal."""
    prove(world)
    validate_cast(cast, world)
    _text(prompt, "prompt", 4096)
    _id(fact_id, "fact_id")
    _text(title, "title", 200)
    _text(detail, "detail", 4096)
    _id(choice, "choice")
    _id(speaker, "speaker")
    _id(recipient, "recipient")
    actors = {actor["id"] for actor in cast["characters"]}
    if recipient not in actors | {"player"}:
        raise CanonError("knowledge_unknown_recipient")
    data = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "cast_digest": digest(cast),
        "facts": [{
            "id": fact_id, "title": title, "detail": detail,
            "initial_knowers": [speaker] if speaker != "narrator" else [],
        }],
        "disclosures": [{
            "id": "reveal_" + fact_id if len(fact_id) <= 40 else "reveal",
            "fact": fact_id, "choice": choice, "speaker": speaker,
            "recipients": [recipient],
        }],
        "claims": [], "approved": False,
        "review_note": "Original author review required: " + prompt[:400],
    }
    validate_knowledge(data, world, cast)
    prove_knowledge(data, world, cast)
    return data


def _knowledge_states(data: Any, world: Any, cast: Any):
    validate_knowledge(data, world, cast)
    actor_ids = sorted({actor["id"] for actor in cast["characters"]} | {"player"})
    fact_ids = sorted(fact["id"] for fact in data["facts"])
    fact_bit = {fid: 1 << index for index, fid in enumerate(fact_ids)}
    actor_index = {actor: index for index, actor in enumerate(actor_ids)}
    initial = [0] * len(actor_ids)
    for fact in data["facts"]:
        for actor in fact["initial_knowers"]:
            initial[actor_index[actor]] |= fact_bit[fact["id"]]
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for items in edges.values():
        items.sort(key=lambda choice: choice["id"])
    reveals: dict[str, list[dict[str, Any]]] = {}
    for item in data["disclosures"]:
        reveals.setdefault(item["choice"], []).append(item)
    claims = {item["line"]: item["fact"] for item in data["claims"]}
    lines: dict[str, list[dict[str, Any]]] = {}
    for line in cast["lines"]:
        if line["id"] in claims:
            lines.setdefault(line["scene"], []).append(line)
    endings = {item["scene"] for item in world["endings"]}
    start = (world["start"], frozenset(), tuple(initial))
    queue = deque([(start, ())])
    visited = {start}
    ending_witnesses: dict[str, list[dict[str, Any]]] = {}
    while queue:
        (scene, flags, knowledge), path = queue.popleft()
        for line in lines.get(scene, ()):
            if not set(line["requires_flags"]) <= flags:
                continue
            fact = claims[line["id"]]
            if not knowledge[actor_index[line["speaker"]]] & fact_bit[fact]:
                raise CanonError("knowledge_dialogue_leak", line["id"])
        if scene in endings:
            ending_witnesses.setdefault(scene, []).append({
                "choices": list(path),
                "player_facts": [
                    fid for fid in fact_ids
                    if knowledge[actor_index["player"]] & fact_bit[fid]
                ],
            })
            continue
        for choice in edges.get(scene, ()):
            if not set(choice["requires"]) <= flags:
                continue
            updated = list(knowledge)
            for disclosure in reveals.get(choice["id"], ()):
                fact = disclosure["fact"]
                speaker = disclosure["speaker"]
                if speaker != "narrator" and not (
                    knowledge[actor_index[speaker]] & fact_bit[fact]
                ):
                    raise CanonError("knowledge_unearned_disclosure",
                                     disclosure["id"])
                for recipient in disclosure["recipients"]:
                    updated[actor_index[recipient]] |= fact_bit[fact]
            target = (choice["to"],
                      flags | frozenset(choice["grants"]), tuple(updated))
            if target not in visited:
                visited.add(target)
                if len(visited) > MAX_STATES:
                    raise CanonError("knowledge_state_budget")
                queue.append((target, path + (choice["id"],)))
    return ending_witnesses, len(visited)


def prove_knowledge(data: Any, world: Any, cast: Any) -> dict[str, Any]:
    witnesses, count = _knowledge_states(data, world, cast)
    if set(witnesses) != {item["scene"] for item in world["endings"]}:
        raise CanonError("knowledge_ending_unreachable")
    return {
        "schema": "jeeves.world.knowledge_proof.v1",
        "world_digest": digest(world), "cast_digest": digest(cast),
        "knowledge_digest": digest(data), "states_explored": count,
        "ending_witnesses": {
            key: sorted(value, key=lambda item: item["choices"])
            for key, value in sorted(witnesses.items())
        },
        "scope": "declared_fact_claims_only",
        "confidence": "bounded_exhaustive_reachable_state_proof",
    }


def edit_knowledge(data: Any, world: Any, cast: Any, operation: Any) -> dict[str, Any]:
    validate_knowledge(data, world, cast)
    op = _keys(operation, {"action", "value"})
    batch = (_list(op["value"], "batch", 64) if op["action"] == "batch"
             else [op])
    if not batch:
        raise CanonError("knowledge_empty_batch")
    updated = strict_json(canonical(data))
    names = {"fact": ("facts", "id"), "disclosure": ("disclosures", "id"),
             "claim": ("claims", "line")}
    for item in batch:
        edit = _keys(item, {"action", "value"})
        action, value = edit["action"], edit["value"]
        if type(action) is not str:
            raise CanonError("knowledge_invalid_edit")
        verb, sep, kind = action.partition("_")
        if not sep or verb not in {"add", "replace", "remove"} or kind not in names:
            raise CanonError("knowledge_unsupported_edit")
        collection, key = names[kind]
        entries = updated[collection]
        if verb == "remove":
            _keys(value, {key})
            _id(value[key], "edit.target")
            matching = [index for index, entry in enumerate(entries)
                        if entry[key] == value[key]]
            if len(matching) != 1:
                raise CanonError("knowledge_unknown_edit_target")
            del entries[matching[0]]
        elif verb == "add":
            if type(value) is not dict:
                raise CanonError("knowledge_invalid_edit")
            entries.append(value)
        else:
            if type(value) is not dict or key not in value:
                raise CanonError("knowledge_invalid_edit")
            matching = [index for index, entry in enumerate(entries)
                        if entry[key] == value[key]]
            if len(matching) != 1:
                raise CanonError("knowledge_unknown_edit_target")
            entries[matching[0]] = value
    updated["approved"] = False
    updated["review_note"] = "Source changed: renewed original author review required"
    validate_knowledge(updated, world, cast)
    prove_knowledge(updated, world, cast)
    return updated


def approve_knowledge(data: Any, world: Any, cast: Any, note: str) -> dict[str, Any]:
    prove_knowledge(data, world, cast)
    _text(note, "review_note", 512)
    updated = strict_json(canonical(data))
    updated["approved"] = True
    updated["review_note"] = note
    return validate_knowledge(updated, world, cast)


def replay_knowledge(
    data: Any, world: Any, cast: Any, trace: Any,
) -> dict[str, Any]:
    """Independently replay legal choices, never trusting a supplied save state."""
    validate_knowledge(data, world, cast)
    if not data["approved"]:
        raise CanonError("knowledge_review_required")
    steps = _list(trace, "trace", MAX_TRACE)
    actor_ids = {actor["id"] for actor in cast["characters"]} | {"player"}
    known = {actor: set() for actor in actor_ids}
    for fact in data["facts"]:
        for actor in fact["initial_knowers"]:
            known[actor].add(fact["id"])
    choices = {choice["id"]: choice for choice in world["choices"]}
    disclosures: dict[str, list[dict[str, Any]]] = {}
    for disclosure in data["disclosures"]:
        disclosures.setdefault(disclosure["choice"], []).append(disclosure)
    endings = {ending["scene"] for ending in world["endings"]}
    scene, flags = world["start"], set()
    for item in steps:
        choice_id = _id(item, "trace.choice")
        choice = choices.get(choice_id)
        if (scene in endings or choice is None or choice["from"] != scene or
                not set(choice["requires"]) <= flags):
            raise CanonError("knowledge_invalid_replay", choice_id)
        for disclosure in disclosures.get(choice_id, ()):
            if (disclosure["speaker"] != "narrator" and
                    disclosure["fact"] not in known[disclosure["speaker"]]):
                raise CanonError("knowledge_unearned_disclosure",
                                 disclosure["id"])
            for recipient in disclosure["recipients"]:
                known[recipient].add(disclosure["fact"])
        flags.update(choice["grants"])
        scene = choice["to"]
    facts = {fact["id"]: fact for fact in data["facts"]}
    return {
        "schema": "jeeves.world.knowledge_player.v1",
        "world_id": world["id"], "world_digest": digest(world),
        "knowledge_digest": digest(data), "scene": scene,
        "choices": list(steps),
        "visible_facts": [
            {"id": fid, "title": facts[fid]["title"],
             "detail": facts[fid]["detail"]}
            for fid in sorted(known["player"])
        ],
        "scope": "player_known_facts_only",
    }


def compile_knowledge(data: Any, world: Any, cast: Any) -> dict[str, Any]:
    proof = prove_knowledge(data, world, cast)
    if not data["approved"]:
        raise CanonError("knowledge_review_required")
    return {
        "schema": HANDOFF_SCHEMA, "world": world, "cast": cast,
        "knowledge": data, "proof": proof,
        "qualification": "original_author_review_not_device_certification",
        "confidentiality": "none_embedded_author_content_visible_in_page_source",
    }


_PLAYER_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("knowledge-data").textContent);
const world = model.world, cast = model.cast, knowledge = model.knowledge;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const actors = new Map(cast.characters.map(a => [a.id, a]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const facts = new Map(knowledge.facts.map(f => [f.id, f]));
let scene = world.start, flags = new Set(), trace = [];
let known = new Map();
function resetKnowledge() {
  known = new Map([...actors.keys(), "player"].map(id => [id, new Set()]));
  for (const fact of knowledge.facts) {
    for (const actor of fact.initial_knowers) known.get(actor).add(fact.id);
  }
}
const root = document.getElementById("play");
function node(tag, value) {
  const element = document.createElement(tag);
  element.textContent = value;
  return element;
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  const lines = cast.lines.filter(line => line.scene === scene &&
    line.requires_flags.every(flag => flags.has(flag)))
    .sort((a,b) => a.order - b.order || a.id.localeCompare(b.id));
  for (const line of lines) {
    root.append(node("p", actors.get(line.speaker).name + ": " + line.text));
  }
  root.append(node("h2", "Discovered facts"));
  const visible = [...known.get("player")].sort();
  for (const fid of visible) {
    const fact = facts.get(fid);
    root.append(node("h3", fact.title), node("p", fact.detail));
  }
  root.append(node("p", "Choices: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = [];
      resetKnowledge(); render();
    });
    root.append(restart);
    return;
  }
  for (const choice of world.choices.filter(c => c.from === scene &&
      c.requires.every(flag => flags.has(flag)))) {
    const button = node("button", choice.label);
    button.addEventListener("click", () => {
      for (const reveal of knowledge.disclosures.filter(d => d.choice === choice.id)) {
        for (const recipient of reveal.recipients) known.get(recipient).add(reveal.fact);
      }
      flags = new Set([...flags, ...choice.grants]);
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
}
resetKnowledge();
render();
""".strip()


def render_knowledge_html(data: Any, world: Any, cast: Any) -> bytes:
    manifest = compile_knowledge(data, world, cast)
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    script_hash = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode()
    title = html.escape(world["id"], quote=True)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + script_hash +
        "'; style-src 'none'; connect-src 'none'; img-src 'none'; "
        'base-uri ' + "'none'; form-action 'none'" + '">'
        '<title>' + title + ' — reviewed knowledge</title></head><body>'
        '<main id="play" aria-live="polite"></main>'
        '<script id="knowledge-data" type="application/json">' + embedded +
        '</script><script>' + _PLAYER_JS + '</script></body></html>\n'
    )
    result = page.encode("utf-8")
    if len(result) > MAX_BYTES:
        raise CanonError("knowledge_artifact_too_large")
    return result


class KnowledgeStore:
    """Descriptor-held, optimistic source lease; fail-closed publication."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".knowledge.json"

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".knowledge.playable.html",
                world_id + ".knowledge.handoff.json",
                world_id + ".knowledge.receipt.json")

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        try:
            lock_fd = os.open(world_id + ".lock",
                              os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(lock_fd)

    def _sources(self, fd: int, world_id: str):
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        cast = strict_json(self.worlds._read(fd, world_id + ".cast.json"))
        validate_cast(cast, world)
        return world, cast

    def _read(self, fd: int, world_id: str, world: Any, cast: Any):
        data = strict_json(self.worlds._read(fd, self._name(world_id)))
        validate_knowledge(data, world, cast)
        prove_knowledge(data, world, cast)
        return data

    def read(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            return self._read(fd, world_id, world, cast)
        finally:
            os.close(fd)

    def publish(
        self, world_id: str, data: Any, *,
        expected_digest: str | None = None, create: bool = False,
    ) -> str:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                prove_knowledge(data, world, cast)
                try:
                    old = self._read(fd, world_id, world, cast)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("knowledge_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("stale_knowledge")
                self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, data: Any, world: Any, cast: Any):
        manifest = canonical(compile_knowledge(data, world, cast))
        playable = render_knowledge_html(data, world, cast)
        if len(manifest) > MAX_BYTES:
            raise CanonError("knowledge_artifact_too_large")
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cast_digest": digest(cast),
            "knowledge_digest": digest(data),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], (playable, manifest))
            },
            "qualification": "author_review_only_not_release_certified",
        }
        return receipt, (playable, manifest)

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                if digest(data) != expected_digest:
                    raise CanonError("stale_knowledge")
                receipt, artifacts = self._outputs(data, world, cast)
                names = self._names(world_id)
                for name, content in zip(names[:2], artifacts):
                    self.worlds._write(fd, name, content)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world, cast = self._sources(fd, world_id)
                data = self._read(fd, world_id, world, cast)
                receipt, artifacts = self._outputs(data, world, cast)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("knowledge_receipt_mismatch")
                for name, expected in zip(names[:2], artifacts):
                    if self.worlds._read(fd, name) != expected:
                        raise CanonError("knowledge_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, trace: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, cast = self._sources(fd, world_id)
            data = self._read(fd, world_id, world, cast)
            return replay_knowledge(data, world, cast, trace)
        finally:
            os.close(fd)
