"""Source-leased, fully covered original narrative localization and offline play."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
import re
from typing import Any

from .bundle import _artifact_read
from .session import SessionStore, replay_choices, validate_session
from .world_canon import CanonError, WorldStore, _id, _keys, _list, _text, canonical, digest, prove, strict_json

SCHEMA = "jeeves.world.localization.v1"
PROOF_SCHEMA = "jeeves.world.localization_proof.v1"
RECEIPT_SCHEMA = "jeeves.world.localization_receipt.v1"
LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
PLACEHOLDER_RE = re.compile(r"\{[a-z][a-z0-9_]*\}")


def _locale_tag(value: Any) -> str:
    if type(value) is not str or LOCALE_RE.fullmatch(value) is None:
        raise CanonError("localization_invalid_locale")
    return value


def _placeholders(value: str) -> list[str]:
    return sorted(PLACEHOLDER_RE.findall(value))


def _equivalent_text(original: str, translated: Any, field: str, limit: int) -> str:
    _text(translated, field, limit)
    if _placeholders(original) != _placeholders(translated):
        raise CanonError("localization_placeholder_mismatch", field)
    return translated


def validate_localization(source: Any, world: Any) -> dict[str, Any]:
    prove(world)
    obj = _keys(source, {"schema", "world_id", "world_digest", "prompt",
                         "approved", "review_note", "locales"})
    if obj["schema"] != SCHEMA:
        raise CanonError("localization_schema_mismatch")
    if obj["world_id"] != world["id"] or obj["world_digest"] != digest(world):
        raise CanonError("localization_source_lease_mismatch")
    _text(obj["prompt"], "prompt", 4096)
    _text(obj["review_note"], "review_note", 512)
    if type(obj["approved"]) is not bool:
        raise CanonError("localization_invalid_approval")
    scenes = {scene["id"]: scene for scene in world["scenes"]}
    choices = {choice["id"]: choice for choice in world["choices"]}
    endings = {ending["scene"]: ending for ending in world["endings"]}
    locales = _list(obj["locales"], "locales", 16)
    if not locales:
        raise CanonError("localization_empty")
    tags = []
    for locale in locales:
        _keys(locale, {"tag", "scenes", "choices", "endings"})
        tags.append(_locale_tag(locale["tag"]))
        scene_rows = _list(locale["scenes"], "locale.scenes", 128)
        choice_rows = _list(locale["choices"], "locale.choices", 512)
        ending_rows = _list(locale["endings"], "locale.endings", 128)
        scene_ids = []
        for row in scene_rows:
            _keys(row, {"id", "title", "narrative"})
            sid = _id(row["id"], "locale.scene.id")
            if sid not in scenes:
                raise CanonError("localization_unknown_scene")
            scene_ids.append(sid)
            _equivalent_text(scenes[sid]["title"], row["title"], "locale.title", 400)
            _equivalent_text(scenes[sid]["narrative"], row["narrative"],
                             "locale.narrative", 4096)
        if scene_ids != sorted(scenes):
            raise CanonError("localization_scene_coverage")
        choice_ids = []
        for row in choice_rows:
            _keys(row, {"id", "label"})
            cid = _id(row["id"], "locale.choice.id")
            if cid not in choices:
                raise CanonError("localization_unknown_choice")
            choice_ids.append(cid)
            _equivalent_text(choices[cid]["label"], row["label"], "locale.choice", 400)
        if choice_ids != sorted(choices):
            raise CanonError("localization_choice_coverage")
        ending_ids = []
        for row in ending_rows:
            _keys(row, {"scene", "label"})
            eid = _id(row["scene"], "locale.ending.scene")
            if eid not in endings:
                raise CanonError("localization_unknown_ending")
            ending_ids.append(eid)
            _equivalent_text(endings[eid]["label"], row["label"], "locale.ending", 400)
        if ending_ids != sorted(endings):
            raise CanonError("localization_ending_coverage")
    if tags != sorted(set(tags)):
        raise CanonError("localization_noncanonical_locales")
    if len(canonical(obj)) > 524288:
        raise CanonError("localization_too_large")
    return obj


def prove_localization(source: Any, world: Any) -> dict[str, Any]:
    obj = validate_localization(source, world)
    world_proof = prove(world).as_dict()
    return {"schema": PROOF_SCHEMA, "world_digest": digest(world),
            "localization_digest": digest(obj), "locales": [
                {"tag": item["tag"], "scene_count": len(item["scenes"]),
                 "choice_count": len(item["choices"]),
                 "ending_count": len(item["endings"]),
                 "ending_witnesses": world_proof["ending_witnesses"]}
                for item in obj["locales"]],
            "world_states_explored": world_proof["states_explored"]}


def propose_localization(world: Any, *, prompt: str, locale: Any) -> dict[str, Any]:
    """Use explicitly authored translations, never pretend a copied draft is translated."""
    obj = {"schema": SCHEMA, "world_id": world["id"],
           "world_digest": digest(world), "prompt": prompt,
           "approved": False, "review_note": "Author translation review required",
           "locales": [locale]}
    prove_localization(obj, world)
    return obj


def edit_localization(source: Any, world: Any, operation: Any) -> dict[str, Any]:
    validate_localization(source, world)
    op = _keys(operation, {"action", "value"})
    candidate = strict_json(canonical(source))
    action, value = op["action"], op["value"]
    if action in ("add_locale", "replace_locale"):
        _keys(value, {"tag", "scenes", "choices", "endings"})
        if action == "add_locale":
            candidate["locales"].append(value)
        else:
            matches = [i for i, item in enumerate(candidate["locales"])
                       if item["tag"] == value["tag"]]
            if len(matches) != 1:
                raise CanonError("localization_unknown_edit")
            candidate["locales"][matches[0]] = value
        candidate["locales"].sort(key=lambda item: item["tag"])
    elif action == "remove_locale":
        _keys(value, {"tag"})
        old = len(candidate["locales"])
        candidate["locales"] = [item for item in candidate["locales"]
                                if item["tag"] != value["tag"]]
        if len(candidate["locales"]) != old - 1:
            raise CanonError("localization_unknown_edit")
    else:
        raise CanonError("localization_unsupported_edit")
    candidate["approved"] = False
    candidate["review_note"] = "Changed translations require renewed review"
    prove_localization(candidate, world)
    return candidate


def localized_replay(source: Any, world: Any, choices: Any, locale_tag: str) -> dict[str, Any]:
    validate_localization(source, world)
    _locale_tag(locale_tag)
    selected = next((item for item in source["locales"] if item["tag"] == locale_tag), None)
    if selected is None:
        raise CanonError("localization_missing_locale")
    replay = replay_choices(world, choices)
    scenes = {item["id"]: item for item in selected["scenes"]}
    choice_labels = {item["id"]: item["label"] for item in selected["choices"]}
    endings = {item["scene"]: item["label"] for item in selected["endings"]}
    return {"world_digest": digest(world), "localization_digest": digest(source),
            "locale": locale_tag, "scene": scenes[replay["scene"]],
            "ending": endings.get(replay["scene"]),
            "steps": [{"scene": scenes[step["scene"]],
                       "choice": step["choice"],
                       "choice_label": (choice_labels[step["choice"]]
                                        if step["choice"] is not None else None)}
                      for step in replay["steps"]]}


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("locale-data").textContent);
const world = data.world, locales = data.localization.locales;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Set(world.endings.map(e => e.scene));
const root = document.getElementById("play");
let locale = locales[0], scene = world.start, flags = new Set(), trace = [];
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
function render() {
  root.replaceChildren();
  const select = document.createElement("select");
  for (const option of locales) {
    const item = document.createElement("option");
    item.value = option.tag; item.textContent = option.tag;
    item.selected = option.tag === locale.tag; select.append(item);
  }
  select.addEventListener("change", () => {
    locale = locales.find(item => item.tag === select.value); render();
  });
  root.append(node("label", "Language: "), select);
  const current = locale.scenes.find(item => item.id === scene);
  root.append(node("h1", current.title), node("p", current.narrative));
  root.append(node("p", "Choice history: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", locale.endings.find(item => item.scene === scene).label));
    const restart = node("button", "Restart");
    restart.addEventListener("click", () => {
      scene = world.start; flags = new Set(); trace = []; render();
    });
    root.append(restart); return;
  }
  for (const choice of world.choices.filter(item => item.from === scene)) {
    if (!choice.requires.every(flag => flags.has(flag))) continue;
    const label = locale.choices.find(item => item.id === choice.id).label;
    const button = node("button", label);
    button.addEventListener("click", () => {
      for (const flag of choice.grants) flags.add(flag);
      trace.push(choice.id); scene = choice.to; render();
    });
    root.append(button);
  }
}
render();
""".strip()


def render_localization_html(source: Any, world: Any) -> bytes:
    prove_localization(source, world)
    if not source["approved"]:
        raise CanonError("localization_review_required")
    payload = canonical({"world": world, "localization": source}).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(world["id"], quote=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + title + ' localized world</title></head><body>'
            '<main id="play" aria-live="polite"></main>'
            '<script id="locale-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("localization_playable_too_large")
    return page


class LocalizationStore:
    """Source-verified original translations, reviewed edits and offline compile."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".localization.json",
                world_id + ".localization.playable.html",
                world_id + ".localization.receipt.json")

    def _world(self, fd: int, world_id: str) -> Any:
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        return world

    def _read(self, fd: int, world_id: str, world: Any) -> Any:
        return validate_localization(
            strict_json(self.worlds._read(fd, self._names(world_id)[0])), world)

    def _locked(self, fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def propose(self, world_id: str, *, prompt: str, locale: Any) -> Any:
        fd = self.worlds._directory()
        try:
            return propose_localization(self._world(fd, world_id),
                                        prompt=prompt, locale=locale)
        finally:
            os.close(fd)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            source = self._read(fd, world_id, world)
            return {"localization": source, "proof": prove_localization(source, world)}
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
                candidate["review_note"] = "Published translations require review"
                prove_localization(candidate, world)
                try:
                    old = self._read(fd, world_id, world)
                except CanonError as exc:
                    if exc.code != "not_found":
                        raise
                    old = None
                if create:
                    if old is not None or expected_digest is not None:
                        raise CanonError("localization_already_exists")
                elif old is None or digest(old) != expected_digest:
                    raise CanonError("localization_stale_edit")
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
                    raise CanonError("localization_stale_edit")
                source["approved"] = True
                source["review_note"] = review_note
                prove_localization(source, world)
                self.worlds._write(fd, self._names(world_id)[0], canonical(source))
                return digest(source)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str, locale_tag: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            world = self._world(fd, world_id)
            source = self._read(fd, world_id, world)
            if not source["approved"]:
                raise CanonError("localization_review_required")
            session = validate_session(
                strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
            return {"slot": slot, "session_digest": digest(session),
                    "revision": session["revision"],
                    "player": localized_replay(source, world, session["choices"], locale_tag)}
        finally:
            os.close(fd)

    def _outputs(self, source: Any, world: Any) -> tuple[dict[str, Any], bytes]:
        proof = prove_localization(source, world)
        playable = render_localization_html(source, world)
        receipt = {"schema": RECEIPT_SCHEMA, "world_id": world["id"],
                   "world_digest": digest(world),
                   "localization_digest": digest(source), "proof_digest": digest(proof),
                   "html_file": self._names(world["id"])[1],
                   "html_sha256": sha256(playable).hexdigest(),
                   "qualification": "reviewed_original_translation_not_release_certified"}
        return receipt, playable

    def compile(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("localization_stale_edit")
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
                    raise CanonError("localization_receipt_mismatch")
                if _artifact_read(fd, names[1]) != playable:
                    raise CanonError("localization_playable_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def editor(self, world_id: str, expected_digest: str) -> dict[str, Any]:
        from .localization_editor import render_editor
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                world = self._world(fd, world_id)
                source = self._read(fd, world_id, world)
                if digest(source) != expected_digest:
                    raise CanonError("localization_stale_edit")
                page = render_editor(source, world)
                name = world_id + ".localization.editor.html"
                self.worlds._write(fd, name, page)
                return {"html_file": name, "html_sha256": sha256(page).hexdigest(),
                        "localization_digest": digest(source)}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
