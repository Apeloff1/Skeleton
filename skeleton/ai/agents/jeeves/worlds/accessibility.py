"""Reviewed scene accessibility narration, complete coverage and keyboard-playable handoff."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .session import SessionStore, replay_choices, validate_session
from .world_canon import CanonError, WorldStore, _id, _keys, _list, _text, canonical, digest, prove, strict_json

SCHEMA = "jeeves.world.accessibility.v1"
PROOF_SCHEMA = "jeeves.world.accessibility_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.accessibility_receipt.v1"


def validate_accessibility(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {"schema", "world_id", "world_digest", "prompt",
                         "approved", "review_note", "scenes", "choices", "endings"})
    if obj["schema"] != SCHEMA:
        raise CanonError("accessibility_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("accessibility_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("accessibility_invalid_approval")
    scenes = {item["id"]: item for item in world["scenes"]}
    choices = {item["id"]: item for item in world["choices"]}
    endings = {item["scene"]: item for item in world["endings"]}
    scene_rows = _list(obj["scenes"], "accessibility.scenes", 128)
    choice_rows = _list(obj["choices"], "accessibility.choices", 512)
    ending_rows = _list(obj["endings"], "accessibility.endings", 128)
    scene_ids = []
    for row in scene_rows:
        _keys(row, {"id", "summary", "landmark"})
        sid = _id(row["id"], "accessibility.scene.id")
        if sid not in scenes:
            raise CanonError("accessibility_unknown_scene")
        scene_ids.append(sid)
        _text(row["summary"], "accessibility.scene.summary", 2048)
        if type(row["landmark"]) is not str or row["landmark"] not in ("main", "region"):
            raise CanonError("accessibility_invalid_landmark")
    if scene_ids != sorted(scenes):
        raise CanonError("accessibility_scene_coverage")
    choice_ids = []
    action_by_scene: dict[str, set[str]] = {}
    for row in choice_rows:
        _keys(row, {"id", "action"})
        cid = _id(row["id"], "accessibility.choice.id")
        if cid not in choices:
            raise CanonError("accessibility_unknown_choice")
        choice_ids.append(cid)
        action = _text(row["action"], "accessibility.choice.action", 512)
        scene = choices[cid]["from"]
        if action in action_by_scene.setdefault(scene, set()):
            raise CanonError("accessibility_ambiguous_action")
        action_by_scene[scene].add(action)
    if choice_ids != sorted(choices):
        raise CanonError("accessibility_choice_coverage")
    ending_ids = []
    for row in ending_rows:
        _keys(row, {"scene", "summary"})
        sid = _id(row["scene"], "accessibility.ending.scene")
        if sid not in endings:
            raise CanonError("accessibility_unknown_ending")
        ending_ids.append(sid)
        _text(row["summary"], "accessibility.ending.summary", 2048)
    if ending_ids != sorted(endings):
        raise CanonError("accessibility_ending_coverage")
    if len(canonical(obj)) > 524288:
        raise CanonError("accessibility_too_large")
    return obj


def prove_accessibility(source: Any, world: Any) -> dict[str, Any]:
    obj = validate_accessibility(source, world)
    proof = prove(world).as_dict()
    return {"schema": PROOF_SCHEMA, "world_digest": digest(world),
            "accessibility_digest": digest(obj),
            "scene_count": len(obj["scenes"]),
            "choice_count": len(obj["choices"]),
            "ending_count": len(obj["endings"]),
            "ending_witnesses": proof["ending_witnesses"],
            "visited_scenes": proof["visited_scenes"],
            "states_explored": proof["states_explored"]}


def propose_accessibility(world: Any, *, prompt: str, scenes: Any,
                          choices: Any, endings: Any) -> dict[str, Any]:
    """Typed author-supplied descriptions; never generate false accessibility claims."""
    obj = {"schema": SCHEMA, "world_id": world["id"],
           "world_digest": digest(world), "prompt": prompt,
           "approved": False, "review_note": "Accessibility narration requires review",
           "scenes": scenes, "choices": choices, "endings": endings}
    prove_accessibility(obj, world)
    return obj


def edit_accessibility(source: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_accessibility(source, world)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(source))
    action, value = op["action"], op["value"]
    if action in ("replace_scene", "replace_choice", "replace_ending"):
        collection = ("scenes" if action == "replace_scene" else
                      "choices" if action == "replace_choice" else "endings")
        required = ({"id", "summary", "landmark"} if collection == "scenes"
                    else {"id", "action"} if collection == "choices"
                    else {"scene", "summary"})
        _keys(value, required)
        key = "scene" if collection == "endings" else "id"
        matches = [i for i, item in enumerate(candidate[collection])
                   if item[key] == value[key]]
        if len(matches) != 1:
            raise CanonError("accessibility_unknown_edit")
        candidate[collection][matches[0]] = value
    else:
        raise CanonError("accessibility_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Changed accessibility descriptions need renewed review"
    prove_accessibility(candidate, world)
    return candidate


def accessible_replay(source: Any, world: Any, choices: Any) -> dict[str, Any]:
    validate_accessibility(source, world)
    replay = replay_choices(world, choices)
    scenes = {item["id"]: item for item in source["scenes"]}
    actions = {item["id"]: item["action"] for item in source["choices"]}
    endings = {item["scene"]: item["summary"] for item in source["endings"]}
    return {"world_digest": digest(world), "accessibility_digest": digest(source),
            "scene": scenes[replay["scene"]],
            "ending": endings.get(replay["scene"]),
            "steps": [{"scene": scenes[step["scene"]],
                       "choice": step["choice"],
                       "accessible_action": (actions[step["choice"]]
                                             if step["choice"] is not None else None)}
                      for step in replay["steps"]]}


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("access-data").textContent);
const world = data.world, access = data.accessibility;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const descriptions = new Map(access.scenes.map(s => [s.id, s]));
const actions = new Map(access.choices.map(c => [c.id, c.action]));
const endings = new Map(access.endings.map(e => [e.scene, e.summary]));
const root = document.getElementById("play");
let scene = world.start, flags = new Set(), trace = [];
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
function render() {
  root.replaceChildren();
  const current = scenes.get(scene), description = descriptions.get(scene);
  const heading = node("h1", current.title);
  heading.tabIndex = -1;
  root.append(heading, node("p", current.narrative));
  const narration = node("p", description.summary);
  narration.setAttribute("aria-label", "Scene description");
  if (description.landmark === "region") narration.setAttribute("role", "region");
  root.append(narration);
  root.append(node("p", "Choice history: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", endings.get(scene)));
    const restart = node("button", "Restart from the beginning");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = []; render();
    });
    root.append(restart); heading.focus(); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(flag => flags.has(flag))) continue;
    const button = node("button", actions.get(choice.id));
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
  heading.focus();
}
render();
""".strip()


def render_accessibility_html(source: Any, world: Any) -> bytes:
    prove_accessibility(source, world)
    if not source["approved"]:
        raise CanonError("accessibility_review_required")
    payload = canonical({"world": world, "accessibility": source}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + title + ' accessible world</title></head><body>'
            '<main id="play" aria-live="polite"></main>'
            '<script id="access-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("accessibility_playable_too_large")
    return page


class AccessibilityStore:
    """Source-bound accessible narrative, author review and verified HTML5 handoff."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".accessibility.json",
                world_id + ".accessibility.playable.html",
                world_id + ".accessibility.receipt.json")

    def _world(self, fd: int, world_id: str) -> Any:
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _read(self, fd: int, world_id: str, world: Any) -> Any:
        return validate_accessibility(
            strict_json(self.worlds._read(fd, self._names(world_id)[0])), world)

    def _locked(self, fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def propose(self, world_id: str, **kwargs: Any) -> Any:
        fd = self.worlds._directory()
        try:
            return propose_accessibility(self._world(fd, world_id), **kwargs)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            source = self._read(fd, world_id, world)
            return {"accessibility": source, "proof": prove_accessibility(source, world)}
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
                candidate["review_note"] = "Published accessibility source requires review"
                prove_accessibility(candidate, world)
                try:
                    old = self._read(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("accessibility_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("accessibility_stale_edit")
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
                    raise CanonError("accessibility_stale_edit")
                source["approved"] = True
                source["review_note"] = review_note
                prove_accessibility(source, world)
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
                raise CanonError("accessibility_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
            return {"slot": slot, "session_digest": digest(session),
                    "revision": session["revision"],
                    "player": accessible_replay(source, world, session["choices"])}
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_accessibility(source, world)
        playable = render_accessibility_html(source, world)
        receipt = {"schema": RECEIPT_SCHEMA, "world_id": world["id"],
                   "world_digest": digest(world),
                   "accessibility_digest": digest(source), "proof_digest": digest(proof),
                   "html_file": self._names(world["id"])[1],
                   "html_sha256": sha256(playable).hexdigest(),
                   "qualification": "authored_accessibility_not_device_certified"}
        return receipt, playable

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("accessibility_stale_edit")
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
                    raise CanonError("accessibility_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("accessibility_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .accessibility_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("accessibility_stale_edit")
                page = render_editor(source, world)
                name = world_id + ".accessibility.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "accessibility_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
