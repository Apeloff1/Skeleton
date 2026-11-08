"""Original chapter/act organization for authored branching worlds.

Chapters are editorial navigation, not fabricated story content. All canonical
scenes belong to exactly one act; cross-act choices and doublebacks remain
legal and are proven from the real world graph and replayed player sessions.
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

SCHEMA = "jeeves.world.chapters.v1"
PROOF_SCHEMA = "jeeves.world.chapters_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.chapters_receipt.v1"
ENGINE_SCHEMA = "jeeves.world.chapters_engine.v1"
MAX_CHAPTERS = 64
MAX_ACTS = 128
MAX_SCENES = 128


def validate_chapters(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {"schema", "world_id", "world_digest", "prompt",
                         "approved", "review_note", "chapters"})
    if obj["schema"] != SCHEMA:
        raise CanonError("chapters_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("chapters_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("chapters_invalid_approval")
    chapters = _list(obj["chapters"], "chapters", MAX_CHAPTERS)
    if not chapters:
        raise CanonError("chapters_empty")
    chapter_ids: set[str] = set()
    act_ids: set[str] = set()
    scene_ids: set[str] = set()
    acts_total = 0
    for chapter in chapters:
        _keys(chapter, {"id", "title", "summary", "acts"})
        cid = _id(chapter["id"], "chapter.id")
        if cid in chapter_ids:
            raise CanonError("chapters_duplicate_chapter", cid)
        chapter_ids.add(cid)
        _text(chapter["title"], "chapter.title", 256)
        _text(chapter["summary"], "chapter.summary", 2048)
        acts = _list(chapter["acts"], "acts", MAX_ACTS)
        if not acts:
            raise CanonError("chapters_empty_chapter", cid)
        acts_total += len(acts)
        for act in acts:
            _keys(act, {"id", "title", "summary", "scenes"})
            aid = _id(act["id"], "act.id")
            if aid in act_ids:
                raise CanonError("chapters_duplicate_act", aid)
            act_ids.add(aid)
            _text(act["title"], "act.title", 256)
            _text(act["summary"], "act.summary", 2048)
            scenes = _list(act["scenes"], "scenes", MAX_SCENES)
            if not scenes:
                raise CanonError("chapters_empty_act", aid)
            for value in scenes:
                sid = _id(value, "act.scene")
                if sid in scene_ids:
                    raise CanonError("chapters_duplicate_scene", sid)
                scene_ids.add(sid)
    if acts_total > MAX_ACTS:
        raise CanonError("chapters_act_budget")
    world_scenes = {s["id"] for s in world["scenes"]}
    if scene_ids != world_scenes:
        raise CanonError("chapters_scene_coverage")
    if len(canonical(obj)) > 524288:
        raise CanonError("chapters_too_large")
    return obj


def scene_index(source: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chapter_index, chapter in enumerate(source["chapters"]):
        for act_index, act in enumerate(chapter["acts"]):
            for scene_index_value, sid in enumerate(act["scenes"]):
                result[sid] = {
                    "chapter": chapter["id"], "chapter_title": chapter["title"],
                    "chapter_index": chapter_index,
                    "act": act["id"], "act_title": act["title"],
                    "act_index": act_index, "scene_index": scene_index_value,
                }
    return result


def prove_chapters(source: Any, world: Any) -> dict[str, Any]:
    obj = validate_chapters(source, world)
    index = scene_index(obj)
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for values in edges.values():
        values.sort(key=lambda e: e["id"])
    initial = (world["start"], frozenset())
    queue = deque([(initial, ())])
    visited = {initial}
    chapter_witnesses: dict[str, list[str]] = {}
    act_witnesses: dict[str, list[str]] = {}
    transitions: set[tuple[str, str, str]] = set()
    while queue:
        (scene, flags), path = queue.popleft()
        entry = index[scene]
        chapter_witnesses.setdefault(entry["chapter"], list(path))
        act_witnesses.setdefault(entry["act"], list(path))
        for choice in edges.get(scene, []):
            if not set(choice["requires"]) <= flags:
                continue
            target = choice["to"]
            target_entry = index[target]
            if entry["act"] != target_entry["act"]:
                transitions.add((entry["act"], target_entry["act"], choice["id"]))
            state = (target, flags | frozenset(choice["grants"]))
            if state not in visited:
                if len(visited) >= 2048:
                    raise CanonError("chapters_state_budget")
                visited.add(state)
                queue.append((state, path + (choice["id"],)))
    if set(chapter_witnesses) != {c["id"] for c in obj["chapters"]}:
        raise CanonError("chapters_unreachable_chapter")
    if set(act_witnesses) != {a["id"] for c in obj["chapters"] for a in c["acts"]}:
        raise CanonError("chapters_unreachable_act")
    return {
        "schema": PROOF_SCHEMA, "world_digest": digest(world),
        "chapters_digest": digest(obj), "states_explored": len(visited),
        "chapter_entry_witnesses": {k: chapter_witnesses[k] for k in sorted(chapter_witnesses)},
        "act_entry_witnesses": {k: act_witnesses[k] for k in sorted(act_witnesses)},
        "cross_act_choices": [{"from": a, "to": b, "choice": c}
                              for a, b, c in sorted(transitions)],
    }


def propose_chapters(world: Any, *, prompt: str, chapters: Any) -> dict[str, Any]:
    source = {
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "prompt": prompt,
        "approved": False,
        "review_note": "Chapter and act organization requires author review",
        "chapters": chapters,
    }
    prove_chapters(source, world)
    return source


def edit_chapters(source: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_chapters(source, world)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(source))
    action, value = op["action"], op["value"]
    if action == "replace_chapter":
        _keys(value, {"id", "title", "summary", "acts"})
        matches = [i for i, item in enumerate(candidate["chapters"])
                   if item["id"] == value["id"]]
        if len(matches) != 1:
            raise CanonError("chapters_unknown_edit_target")
        candidate["chapters"][matches[0]] = value
    elif action == "replace_act":
        _keys(value, {"chapter", "act"})
        _id(value["chapter"], "chapter.id")
        _keys(value["act"], {"id", "title", "summary", "scenes"})
        matches = [c for c in candidate["chapters"]
                   if c["id"] == value["chapter"]]
        if len(matches) != 1:
            raise CanonError("chapters_unknown_edit_target")
        acts = matches[0]["acts"]
        indices = [i for i, act in enumerate(acts)
                   if act["id"] == value["act"]["id"]]
        if len(indices) != 1:
            raise CanonError("chapters_unknown_edit_target")
        acts[indices[0]] = value["act"]
    else:
        raise CanonError("chapters_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Edited chapter organization requires renewed review"
    prove_chapters(candidate, world)
    return candidate


def replay_chapters(source: Any, world: Any, choices: Any) -> dict[str, Any]:
    validate_chapters(source, world)
    replay = replay_choices(world, choices)
    index = scene_index(source)
    seen_chapters: set[str] = set()
    seen_acts: set[str] = set()
    visits = []
    for step in replay["steps"]:
        entry = index[step["scene"]]
        seen_chapters.add(entry["chapter"])
        seen_acts.add(entry["act"])
        visits.append({"scene": step["scene"], "choice": step["choice"],
                       "chapter": entry["chapter"], "act": entry["act"]})
    return {
        "schema": "jeeves.world.chapters_replay.v1",
        "world_digest": digest(world), "chapters_digest": digest(source),
        "scene": replay["scene"], "ending": replay["ending"],
        "current": index[replay["scene"]],
        "visited_chapters": sorted(seen_chapters),
        "visited_acts": sorted(seen_acts),
        "visits": visits,
    }


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("chapters-data").textContent);
const world = data.world, book = data.chapters;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const index = new Map();
for (const chapter of book.chapters) for (const act of chapter.acts)
  for (const sid of act.scenes) index.set(sid, {chapter, act});
const root = document.getElementById("play");
let scene, flags, trace, visited;
function node(tag, text) { const n = document.createElement(tag); n.textContent = text; return n; }
function button(label, fn) {
  const n = node("button", label); n.type = "button";
  n.addEventListener("click", fn); root.append(n);
}
function reset() {
  scene = world.start; flags = new Set(); trace = []; visited = new Set([scene]); render();
}
function advance(choice) {
  for (const flag of choice.grants) flags.add(flag);
  trace.push(choice.id); scene = choice.to; visited.add(scene); render();
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene), entry = index.get(scene);
  root.append(node("h1", entry.chapter.title), node("h2", entry.act.title),
              node("h3", current.title), node("p", current.narrative));
  const visitedActs = new Set(Array.from(visited).map(id => index.get(id).act.id));
  const nav = node("nav", "Visited acts: " + Array.from(visitedActs).sort().join(", "));
  nav.setAttribute("aria-label", "Story progress"); root.append(nav);
  root.append(node("p", "Choices taken: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    button("Restart", reset); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene &&
    c.requires.every(f => flags.has(f)))) button(choice.label, () => advance(choice));
}
reset();
""".strip()


def render_chapters_html(source: Any, world: Any) -> bytes:
    prove_chapters(source, world)
    if not source["approved"]:
        raise CanonError("chapters_review_required")
    payload = canonical({"world": world, "chapters": source}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(world["id"], quote=True) + ' chapters</title></head>'
            '<body><main id="play" aria-live="polite"></main>'
            '<script id="chapters-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("chapters_playable_too_large")
    return page


def engine_handoff(source: Any, world: Any) -> dict[str, Any]:
    proof = prove_chapters(source, world)
    if not source["approved"]:
        raise CanonError("chapters_review_required")
    return {
        "schema": ENGINE_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "chapters_digest": digest(source),
        "chapters": source["chapters"],
        "cross_act_choices": proof["cross_act_choices"],
        "entry_witnesses": proof["act_entry_witnesses"],
        "navigation_policy": "actual_choice_graph_not_linearized",
        "qualification": "reviewed_story_structure_not_release_certified",
    }


class ChapterStore:
    """Private descriptor-anchored custody under the canonical world-wide lease."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".chapters.json", world_id + ".chapters.playable.html",
                world_id + ".chapters.engine.json", world_id + ".chapters.receipt.json")

    def _world(self, fd: int, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _source(self, fd: int, world_id: str, world: Any) -> dict[str, Any]:
        return validate_chapters(
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
                chapters: Any) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            return propose_chapters(self._world(fd, world_id),
                                    prompt=prompt, chapters=chapters)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            source = self._source(fd, world_id, world)
            return {"chapters": source, "proof": prove_chapters(source, world)}
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
                candidate["review_note"] = "Published chapter organization requires review"
                prove_chapters(candidate, world)
                try:
                    old = self._source(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("chapters_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("chapters_stale_edit")
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
                    raise CanonError("chapters_stale_edit")
                source["approved"] = True
                source["review_note"] = note
                prove_chapters(source, world)
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
                raise CanonError("chapters_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
            return {
                "slot": slot, "session_digest": digest(session),
                "revision": session["revision"],
                "player": replay_chapters(source, world, session["choices"]),
            }
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any) -> tuple[dict[str, Any], bytes, bytes]:
        proof = prove_chapters(source, world)
        playable = render_chapters_html(source, world)
        engine = canonical(engine_handoff(source, world))
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "chapters_digest": digest(source),
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
                    raise CanonError("chapters_stale_edit")
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
                    raise CanonError("chapters_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable or _artifact_read(fd, names[2]) != engine:
                    raise CanonError("chapters_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .chapters_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._source(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("chapters_stale_edit")
                page = render_editor(source, world)
                name = world_id + ".chapters.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "chapters_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
