"""Unified original-world playable: testimony, rumors, locales, access and pacing.

All authored source planes are read under one world lease. Compilation and
verification are deterministic; private notes and unapproved edits are excluded.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .cast import CastStore, validate_cast
from .testimony import TestimonyStore, prove_testimony, replay_testimony
from .rumors import RumorStore, prove_rumors, replay_rumors
from .localization import LocalizationStore, prove_localization, localized_replay
from .accessibility import AccessibilityStore, prove_accessibility, accessible_replay
from .pacing import PacingStore, prove_pacing, replay_pacing
from .studio_canon import prove_studio_cross_canon
from .session import SessionStore, replay_choices, validate_session
from .world_canon import CanonError, WorldStore, _id, canonical, digest, prove, strict_json

SCHEMA = "jeeves.world.studio_assembly.v1"
RECEIPT_SCHEMA = "jeeves.world.studio_assembly_receipt.v1"
PLAYER_SCHEMA = "jeeves.world.studio_assembly_player.v1"
SOURCE_NAMES = ("world", "cast", "testimony", "rumors",
                "localization", "accessibility", "pacing")


def compile_studio_assembly(world: Any, cast: Any, testimony: Any, rumors: Any,
                            localization: Any, accessibility: Any, pacing: Any) -> dict[str, Any]:
    prove(world)
    validate_cast(cast, world)
    proofs = {
        "testimony": prove_testimony(testimony, world, cast),
        "rumors": prove_rumors(rumors, world, cast),
        "localization": prove_localization(localization, world),
        "accessibility": prove_accessibility(accessibility, world),
        "pacing": prove_pacing(pacing, world),
        "cross_plane": prove_studio_cross_canon(world, cast, testimony, rumors),
    }
    if not all(source["approved"] for source in (
            cast, testimony, rumors, localization, accessibility, pacing)):
        raise CanonError("studio_assembly_review_required")
    sources = {"world": world, "cast": cast, "testimony": testimony,
               "rumors": rumors, "localization": localization,
               "accessibility": accessibility, "pacing": pacing}
    return {"schema": SCHEMA, "world_id": world["id"],
            "source_digests": {name: digest(value) for name, value in sources.items()},
            "proof_digests": {name: digest(value) for name, value in proofs.items()},
            "sources": sources,
            "qualification": "reviewed_source_only_not_device_or_release_certified"}


def replay_studio_assembly(world: Any, cast: Any, testimony: Any, rumors: Any,
                           localization: Any, accessibility: Any, pacing: Any,
                           choices: Any, locale: str) -> dict[str, Any]:
    manifest = compile_studio_assembly(
        world, cast, testimony, rumors, localization, accessibility, pacing)
    canonical_replay = replay_choices(world, choices)
    views = {
        "testimony": replay_testimony(testimony, world, cast, choices),
        "rumors": replay_rumors(rumors, world, cast, choices),
        "localization": localized_replay(localization, world, choices, locale),
        "accessibility": accessible_replay(accessibility, world, choices),
        "pacing": replay_pacing(pacing, world, choices),
    }
    if any(view["scene"] != canonical_replay["scene"] if type(view["scene"]) is str
           else view["scene"]["id"] != canonical_replay["scene"]
           for view in views.values()):
        raise CanonError("studio_assembly_replay_disagreement")
    return {"schema": PLAYER_SCHEMA, "world_id": world["id"],
            "source_digests": manifest["source_digests"],
            "scene": canonical_replay["scene"], "ending": canonical_replay["ending"],
            "locale": locale, "views": views,
            "qualification": "source_replay_not_device_certified"}


_PLAYER_JS = r"""
"use strict";
const manifest = JSON.parse(document.getElementById("studio-data").textContent);
const data = manifest.sources, world = data.world;
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const actors = new Map(data.cast.characters.map(a => [a.id, a]));
const beats = new Map(data.pacing.beats.map(b => [b.scene, b]));
const accessScenes = new Map(data.accessibility.scenes.map(s => [s.id, s]));
const accessActions = new Map(data.accessibility.choices.map(c => [c.id, c.action]));
const root = document.getElementById("play");
let locale = data.localization.locales[0];
let scene = world.start, flags = new Set(), trace = [], revealed = new Set();
let known = new Map(data.rumors.rumors.map(r => [r.id, new Set()]));
function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
function reset() {
  scene = world.start; flags = new Set(); trace = []; revealed = new Set();
  known = new Map(data.rumors.rumors.map(r => [r.id, new Set()])); render();
}
function advance(choice) {
  const before = new Map(Array.from(known, ([id, actors]) => [id, new Set(actors)]));
  for (const rumor of data.rumors.rumors)
    if (rumor.seed_choice === choice.id) known.get(rumor.id).add(rumor.origin);
  for (const route of data.rumors.routes)
    if (route.choice === choice.id && before.get(route.rumor).has(route.from_actor))
      known.get(route.rumor).add(route.to_actor);
  for (const item of data.testimony.statements)
    if (item.choice === choice.id) revealed.add(item.id);
  for (const flag of choice.grants) flags.add(flag);
  trace.push(choice.id); scene = choice.to; render();
}
function render() {
  root.replaceChildren();
  const select = document.createElement("select");
  for (const option of data.localization.locales) {
    const item = document.createElement("option");
    item.value = option.tag; item.textContent = option.tag;
    item.selected = option.tag === locale.tag; select.append(item);
  }
  select.addEventListener("change", () => {
    locale = data.localization.locales.find(item => item.tag === select.value); render();
  });
  root.append(node("label", "Language: "), select);
  const localized = locale.scenes.find(item => item.id === scene);
  const heading = node("h1", localized.title); heading.tabIndex = -1;
  root.append(heading, node("p", localized.narrative));
  const summary = node("p", accessScenes.get(scene).summary);
  summary.setAttribute("aria-label", "Scene description");
  if (accessScenes.get(scene).landmark === "region") summary.setAttribute("role", "region");
  root.append(summary);
  const beat = beats.get(scene);
  root.append(node("p", "Narrative phase: " + beat.phase + " / " + beat.intensity));
  root.append(node("p", beat.note));
  for (const item of data.testimony.statements)
    if (item.scene === scene && revealed.has(item.id))
      root.append(node("blockquote", actors.get(item.actor).name + ": " + item.text));
  for (const rumor of data.rumors.rumors)
    for (const actor of known.get(rumor.id))
      if (actors.get(actor).scenes.includes(scene))
        root.append(node("p", actors.get(actor).name + " heard: " + rumor.text));
  root.append(node("p", "Choice history: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", locale.endings.find(item => item.scene === scene).label));
    root.append(node("p", data.accessibility.endings.find(item => item.scene === scene).summary));
    const restart = node("button", "Restart");
    restart.addEventListener("click", reset); root.append(restart);
    heading.focus(); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene)) {
    if (!choice.requires.every(flag => flags.has(flag))) continue;
    const localizedChoice = locale.choices.find(item => item.id === choice.id);
    const button = node("button", localizedChoice.label);
    button.setAttribute("aria-label", accessActions.get(choice.id));
    button.addEventListener("click", () => advance(choice)); root.append(button);
  }
  heading.focus();
}
render();
""".strip()


def render_studio_html(manifest: Any) -> bytes:
    if type(manifest) is not dict or manifest.get("schema") != SCHEMA:
        raise CanonError("studio_assembly_invalid_manifest")
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    title = html.escape(manifest["world_id"], quote=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + title + ' original world studio</title></head><body>'
            '<main id="play" aria-live="polite"></main>'
            '<script id="studio-data" type="application/json">' + embedded + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("studio_assembly_playable_too_large")
    return page


class StudioAssemblyStore:
    """One world lock protects all source reads, receipt-last writes and verification."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.cast = CastStore(root)
        self.testimony = TestimonyStore(root)
        self.rumors = RumorStore(root)
        self.localization = LocalizationStore(root)
        self.accessibility = AccessibilityStore(root)
        self.pacing = PacingStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".studio.playable.html",
                world_id + ".studio.manifest.json",
                world_id + ".studio.receipt.json")

    def _locked(self, fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def _sources(self, fd: int, world_id: str) -> tuple[Any, ...]:
        world = self.cast._world(fd, world_id)
        cast = self.cast._cast(fd, world_id, world)
        testimony = self.testimony._read(fd, world_id, world, cast)
        rumors = self.rumors._read(fd, world_id, world, cast)
        localization = self.localization._read(fd, world_id, world)
        accessibility = self.accessibility._read(fd, world_id, world)
        pacing = self.pacing._read(fd, world_id, world)
        return world, cast, testimony, rumors, localization, accessibility, pacing

    def _outputs(self, sources: tuple[Any, ...]) -> tuple[dict[str, Any], tuple[bytes, bytes]]:
        manifest = compile_studio_assembly(*sources)
        contents = (render_studio_html(manifest), canonical(manifest))
        if max(map(len, contents)) > 1572864:
            raise CanonError("studio_assembly_artifact_too_large")
        names = self._names(sources[0]["id"])
        receipt = {"schema": RECEIPT_SCHEMA, "world_id": sources[0]["id"],
                   "source_digests": manifest["source_digests"],
                   "proof_digests": manifest["proof_digests"],
                   "artifacts": {name: sha256(content).hexdigest()
                                 for name, content in zip(names[:2], contents)},
                   "qualification": "source_verified_not_release_certified"}
        return receipt, contents

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                manifest = compile_studio_assembly(*self._sources(fd, world_id))
                return {"source_digests": manifest["source_digests"],
                        "proof_digests": manifest["proof_digests"],
                        "qualification": manifest["qualification"]}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def compile(self, world_id: str, expected_digests: Any) -> dict[str, Any]:
        if type(expected_digests) is not dict or set(expected_digests) != set(SOURCE_NAMES):
            raise CanonError("studio_assembly_invalid_lease")
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                receipt, contents = self._outputs(sources)
                if receipt["source_digests"] != expected_digests:
                    raise CanonError("studio_assembly_stale_source")
                names = self._names(world_id)
                for name, content in zip(names[:2], contents):
                    self.worlds._write(fd, name, content)
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
                receipt, contents = self._outputs(self._sources(fd, world_id))
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("studio_assembly_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if _artifact_read(fd, name) != content:
                        raise CanonError("studio_assembly_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str, locale: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                session = validate_session(
                    strict_json(self.worlds._read(
                        fd, SessionStore._name(world_id, slot))), sources[0])
                result = replay_studio_assembly(*sources, session["choices"], locale)
                return {"slot": slot, "session_digest": digest(session),
                        "revision": session["revision"], "player": result}
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def preview(self, world_id: str, choices: Any, locale: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._locked(fd, world_id)
            try:
                return replay_studio_assembly(
                    *self._sources(fd, world_id), choices, locale)
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
