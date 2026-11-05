"""Reviewed deterministic scene weather with replay-bound engine handoff."""
from __future__ import annotations

import html
import os
from hashlib import sha256
from typing import Any

from .session import SessionStore, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, _keys, _list, _text,
    canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.weather.v1"
PLAYER_SCHEMA = "jeeves.world.weather_player.v1"
RECEIPT_SCHEMA = "jeeves.world.weather_receipt.v1"
WEATHERS = frozenset({"clear", "rain", "snow", "fog", "storm", "wind"})
VISIBILITIES = frozenset({"clear", "limited", "obscured"})


def validate_weather(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {
        "schema", "world_id", "world_digest", "prompt", "scenes",
        "overrides", "approved", "review_note",
    })
    if obj["schema"] != SCHEMA or obj["world_id"] != world["id"]:
        raise CanonError("weather_schema_mismatch")
    if obj["world_digest"] != digest(world):
        raise CanonError("weather_world_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    if type(obj["approved"]) is not bool or type(obj["review_note"]) is not str:
        raise CanonError("weather_invalid_review")
    if obj["approved"]:
        _text(obj["review_note"], "review_note", 1000)
    elif obj["review_note"]:
        raise CanonError("weather_unapproved_note")
    scenes = _list(obj["scenes"], "scenes", 128)
    ids = []
    for item in scenes:
        row = _keys(item, {"scene", "weather", "visibility", "description"})
        ids.append(_id(row["scene"], "scene"))
        if type(row["weather"]) is not str or row["weather"] not in WEATHERS:
            raise CanonError("weather_unknown_condition")
        if type(row["visibility"]) is not str or row["visibility"] not in VISIBILITIES:
            raise CanonError("weather_unknown_visibility")
        _text(row["description"], "description", 1024)
    if ids != sorted(set(ids)) or set(ids) != {s["id"] for s in world["scenes"]}:
        raise CanonError("weather_scene_coverage")
    overrides = _list(obj["overrides"], "overrides", 512)
    choice_ids = {c["id"] for c in world["choices"]}
    overrides_seen = []
    for item in overrides:
        row = _keys(item, {"choice", "weather", "visibility"})
        cid = _id(row["choice"], "choice")
        overrides_seen.append(cid)
        if cid not in choice_ids:
            raise CanonError("weather_unknown_choice")
        if type(row["weather"]) is not str or row["weather"] not in WEATHERS:
            raise CanonError("weather_unknown_condition")
        if type(row["visibility"]) is not str or row["visibility"] not in VISIBILITIES:
            raise CanonError("weather_unknown_visibility")
    if overrides_seen != sorted(set(overrides_seen)):
        raise CanonError("weather_duplicate_or_unsorted_overrides")
    if len(canonical(obj)) > 524288:
        raise CanonError("weather_source_too_large")
    return obj


def propose_weather(world: Any, *, prompt: str, scenes: Any,
                    overrides: Any) -> dict[str, Any]:
    """Typed authored proposal, not an assertion of model-generated prose."""
    return validate_weather({
        "schema": SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "prompt": prompt,
        "scenes": scenes, "overrides": overrides,
        "approved": False, "review_note": "",
    }, world)


def engine_handoff(source: Any, world: Any) -> dict[str, Any]:
    validate_weather(source, world)
    if not source["approved"]:
        raise CanonError("weather_review_required")
    return {
        "schema": "jeeves.world.weather_engine.v1",
        "world_digest": digest(world), "source_digest": digest(source),
        "scene_environment": source["scenes"],
        "choice_overrides": source["overrides"],
        "qualification": "reviewed_engine_recipe_not_built_or_device_certified",
    }


def player_view(source: Any, world: Any, session: Any) -> dict[str, Any]:
    validate_weather(source, world)
    validate_session(session, world)
    if not source["approved"]:
        raise CanonError("weather_review_required")
    scenes = {row["scene"]: row for row in source["scenes"]}
    overrides = {row["choice"]: row for row in source["overrides"]}
    choices = {row["id"]: row for row in world["choices"]}
    current = world["start"]
    timeline = [{
        "scene": current, "choice": None,
        "weather": scenes[current]["weather"],
        "visibility": scenes[current]["visibility"],
    }]
    for cid in session["choices"]:
        edge = choices[cid]
        if edge["from"] != current:
            raise CanonError("weather_replay_diverged")
        current = edge["to"]
        condition = overrides.get(cid, scenes[current])
        timeline.append({
            "scene": current, "choice": cid,
            "weather": condition["weather"],
            "visibility": condition["visibility"],
        })
    if current != session["scene"]:
        raise CanonError("weather_replay_diverged")
    last = timeline[-1]
    return {
        "schema": PLAYER_SCHEMA, "world_id": world["id"],
        "world_digest": digest(world), "weather_digest": digest(source),
        "session_digest": digest(session), "scene": current,
        "weather": last["weather"], "visibility": last["visibility"],
        "description": scenes[current]["description"],
        "timeline": timeline, "ending": session["ending"],
        "qualification": "replay_verified_not_device_certified",
    }


def render_html(view: Any) -> bytes:
    obj = _keys(view, {
        "schema", "world_id", "world_digest", "weather_digest",
        "session_digest", "scene", "weather", "visibility", "description",
        "timeline", "ending", "qualification",
    })
    if obj["schema"] != PLAYER_SCHEMA:
        raise CanonError("weather_invalid_player")
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    for step in _list(obj["timeline"], "timeline", 513):
        row = _keys(step, {"scene", "choice", "weather", "visibility"})
        rows.append("<li>" + esc(row["scene"]) + ": " + esc(row["weather"]) +
                    " / " + esc(row["visibility"]) + "</li>")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'none'; connect-src 'none'; img-src 'none'; "
        "style-src 'none'; base-uri 'none'; form-action 'none'" + '">'
        '<title>World weather replay</title></head><body><main>'
        '<h1>Scene weather: ' + esc(obj["weather"]) + '</h1>'
        '<p>' + esc(obj["description"]) + '</p>'
        '<p>Visibility: ' + esc(obj["visibility"]) + '</p><ol>' +
        "".join(rows) + '</ol><p>Source-verified; not device certified.</p>'
        '</main></body></html>\n'
    ).encode("utf-8")
    if len(page) > 524288:
        raise CanonError("weather_html_too_large")
    return page



_PLAYABLE_JS = r"""
"use strict";
const model = JSON.parse(document.getElementById("weather-data").textContent);
const world = model.world, weather = model.weather;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const conditions = new Map(weather.scenes.map(s => [s.scene, s]));
const overrides = new Map(weather.overrides.map(o => [o.choice, o]));
const root = document.getElementById("play");
let scene = world.start, flags = new Set(), choices = [];
let condition = conditions.get(scene);
function node(tag, value) {
  const el = document.createElement(tag);
  el.textContent = value; return el;
}
function reset() {
  scene = world.start; flags = new Set(); choices = [];
  condition = conditions.get(scene); render();
}
function advance(choice) {
  if (choice.from !== scene || !choice.requires.every(f => flags.has(f))) return;
  for (const flag of choice.grants) flags.add(flag);
  choices.push(choice.id); scene = choice.to;
  condition = overrides.get(choice.id) || conditions.get(scene);
  render();
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene);
  root.append(node("h1", current.title));
  root.append(node("p", current.narrative));
  root.append(node("h2", "Weather: " + condition.weather));
  root.append(node("p", "Visibility: " + condition.visibility));
  root.append(node("p", conditions.get(scene).description));
  root.append(node("p", "Choices taken: " + choices.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    const restart = node("button", "Restart");
    restart.addEventListener("click", reset); root.append(restart); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(f => flags.has(f))) continue;
    const button = node("button", choice.label);
    button.addEventListener("click", () => advance(choice));
    root.append(button);
  }
}
render();
""".strip()


def render_weather_playable(source: Any, world: Any) -> bytes:
    """Compile actual offline choice traversal, not a static scene catalogue."""
    import base64
    validate_weather(source, world)
    if not source["approved"]:
        raise CanonError("weather_review_required")
    payload = canonical({"world": world, "weather": source}).decode("utf-8")
    payload = payload.replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYABLE_JS.encode()).digest()).decode("ascii")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; script-src 'sha256-" + policy +
        "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
        "base-uri 'none'; form-action 'none'" + '">'
        '<title>Original weather-driven world</title></head><body>'
        '<main id="play" aria-live="polite"></main>'
        '<script id="weather-data" type="application/json">' + payload +
        '</script><script>' + _PLAYABLE_JS + '</script></body></html>\n'
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("weather_playable_too_large")
    return page


class WeatherStore:
    """World-scoped descriptor-anchored custody, review and replay."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.sessions = SessionStore(root)

    @staticmethod
    def _name(world_id: str) -> str:
        return _id(world_id, "world_id") + ".weather.json"

    @staticmethod
    def _artifacts(world_id: str, slot: str) -> tuple[str, str]:
        stem = _id(world_id, "world_id") + "." + _id(slot, "slot")
        return stem + ".weather.html", stem + ".weather.receipt.json"

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any]:
        world = self.sessions._world(fd, world_id)
        source = validate_weather(
            strict_json(self.worlds._read(fd, self._name(world_id))), world)
        return world, source

    def _locked(self, fd: int, world_id: str) -> None:
        os.close(self.sessions._lock(fd, world_id))

    def propose(self, world_id: str, *, prompt: str, scenes: Any,
                overrides: Any) -> dict[str, Any]:
        return propose_weather(self.worlds.read(world_id), prompt=prompt,
                               scenes=scenes, overrides=overrides)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, source = self._sources(fd, world_id)
            return {"source": source, "source_digest": digest(source),
                    "world_digest": digest(world),
                    "review_required": not source["approved"]}
        finally:
            os.close(fd)

    def publish(self, world_id: str, source: Any, *,
                expected_digest: str | None = None,
                create: bool = False) -> str:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self.sessions._world(fd, world_id)
                data = validate_weather(source, world)
                if data["approved"]:
                    raise CanonError("weather_approval_bypass")
                try:
                    existing = validate_weather(
                        strict_json(self.worlds._read(fd, self._name(world_id))),
                        world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    if not create or expected_digest is not None:
                        raise CanonError("weather_missing_source") from None
                else:
                    if create or digest(existing) != expected_digest:
                        raise CanonError("weather_stale_source")
                if create:
                    from .branching import _publish_once
                    _publish_once(fd, self._name(world_id), canonical(data))
                else:
                    self.worlds._write(fd, self._name(world_id), canonical(data))
                return digest(data)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def approve(self, world_id: str, expected_digest: str, note: str) -> str:
        _text(note, "review_note", 1000)
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, source = self._sources(fd, world_id)
                if digest(source) != expected_digest:
                    raise CanonError("weather_stale_source")
                if source["approved"]:
                    raise CanonError("weather_already_approved")
                approved = {**source, "approved": True, "review_note": note}
                validate_weather(approved, world)
                self.worlds._write(fd, self._name(world_id), canonical(approved))
                return digest(approved)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world, source = self._sources(fd, world_id)
            session = self.sessions._session(fd, world_id, slot, world)
            return player_view(source, world, session)
        finally:
            os.close(fd)

    def _view(self, fd: int, world_id: str, slot: str) -> dict[str, Any]:
        world, source = self._sources(fd, world_id)
        session = self.sessions._session(fd, world_id, slot, world)
        return player_view(source, world, session)

    @staticmethod
    def _receipt(view: Any, page: bytes) -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA, "world_id": view["world_id"],
            "world_digest": view["world_digest"],
            "weather_digest": view["weather_digest"],
            "session_digest": view["session_digest"],
            "html_sha256": sha256(page).hexdigest(),
        }

    def compile(self, world_id: str, slot: str, source_digest: str,
                session_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                view = self._view(fd, world_id, slot)
                if (view["weather_digest"] != source_digest or
                        view["session_digest"] != session_digest):
                    raise CanonError("weather_stale_lease")
                page = render_html(view)
                receipt = self._receipt(view, page)
                names = self._artifacts(world_id, slot)
                self.worlds._write(fd, names[0], page)
                self.worlds._write(fd, names[1], canonical(receipt))
                return {**receipt, "html_file": names[0], "receipt_file": names[1]}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str, slot: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                names = self._artifacts(world_id, slot)
                recorded = strict_json(self.worlds._read(fd, names[1]))
                view = self._view(fd, world_id, slot)
                page = render_html(view)
                receipt = self._receipt(view, page)
                if recorded != receipt:
                    raise CanonError("weather_receipt_mismatch")
                if self.worlds._read(fd, names[0]) != page:
                    raise CanonError("weather_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .weather_editor import render_weather_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world, source = self._sources(fd, world_id)
                if digest(source) != expected_digest:
                    raise CanonError("weather_stale_source")
                page = render_weather_editor(source, world)
                name = world_id + ".weather.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "source_digest": digest(source), "review_required": True}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    @staticmethod
    def _playable_artifacts(world_id: str) -> tuple[str, str]:
        stem = _id(world_id, "world_id")
        return stem + ".weather.playable.html", stem + ".weather.playable.receipt.json"

    def _playable(self, fd: int, world_id: str) -> tuple[dict[str, Any], bytes]:
        world, source = self._sources(fd, world_id)
        page = render_weather_playable(source, world)
        receipt = {
            "schema": "jeeves.world.weather_playable_receipt.v1",
            "world_id": world_id, "world_digest": digest(world),
            "weather_digest": digest(source),
            "html_sha256": sha256(page).hexdigest(),
        }
        return receipt, page

    def compile_playable(self, world_id: str,
                         expected_source_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                receipt, page = self._playable(fd, world_id)
                if receipt["weather_digest"] != expected_source_digest:
                    raise CanonError("weather_stale_source")
                names = self._playable_artifacts(world_id)
                self.worlds._write(fd, names[0], page)
                self.worlds._write(fd, names[1], canonical(receipt))
                return {**receipt, "html_file": names[0],
                        "receipt_file": names[1]}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify_playable(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                names = self._playable_artifacts(world_id)
                recorded = strict_json(self.worlds._read(fd, names[1]))
                receipt, page = self._playable(fd, world_id)
                if recorded != receipt:
                    raise CanonError("weather_playable_receipt_mismatch")
                if self.worlds._read(fd, names[0]) != page:
                    raise CanonError("weather_playable_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
