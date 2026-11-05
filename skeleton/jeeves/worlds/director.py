"""Unified authored chapter navigation and cinematic playback with exact-source proof."""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .chapters import ChapterStore, prove_chapters, replay_chapters, scene_index
from .cinematics import CinematicsStore, prove_cinematics, replay_cinematics
from .session import SessionStore, validate_session
from .world_canon import (
    CanonError, WorldStore, _id, canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.director.v1"
RECEIPT_SCHEMA = "jeeves.world.director_receipt.v1"
PLAYER_SCHEMA = "jeeves.world.director_player.v1"
SOURCE_NAMES = ("world", "chapters", "cinematics")


def compile_director(world: Any, chapters: Any, cinematics: Any) -> dict[str, Any]:
    prove(world)
    chapter_proof = prove_chapters(chapters, world)
    cinema_proof = prove_cinematics(cinematics, world)
    if not chapters["approved"] or not cinematics["approved"]:
        raise CanonError("director_review_required")
    index = scene_index(chapters)
    scene_cues = {item["scene"]: item["beats"] for item in cinematics["sequences"]}
    return {
        "schema": SCHEMA, "world_id": world["id"],
        "source_digests": dict(zip(SOURCE_NAMES, map(digest, (
            world, chapters, cinematics)))),
        "proof_digests": {"chapters": digest(chapter_proof),
                          "cinematics": digest(cinema_proof)},
        "world": world, "chapters": chapters, "cinematics": cinematics,
        "scene_direction": {
            sid: {"chapter": index[sid], "cinematic_beats": scene_cues.get(sid, [])}
            for sid in sorted(index)
        },
        "timing_policy": "explicit_player_advance_no_automatic_timers",
        "qualification": "reviewed_source_playable_not_device_or_release_certified",
    }


def replay_director(world: Any, chapters: Any, cinematics: Any,
                    choices: Any) -> dict[str, Any]:
    manifest = compile_director(world, chapters, cinematics)
    chapter_view = replay_chapters(chapters, world, choices)
    cinema_view = replay_cinematics(cinematics, world, choices)
    if chapter_view["scene"] != cinema_view["scene"]:
        raise CanonError("director_replay_disagreement")
    return {
        "schema": PLAYER_SCHEMA, "world_id": world["id"],
        "source_digests": manifest["source_digests"],
        "scene": chapter_view["scene"], "ending": chapter_view["ending"],
        "chapters": chapter_view, "cinematics": cinema_view,
        "qualification": "source_replay_not_device_certified",
    }


_PLAYER_JS = r"""
"use strict";
const data = JSON.parse(document.getElementById("director-data").textContent);
const world = data.world, root = document.getElementById("play");
const scenes = new Map(world.scenes.map(s => [s.id, s]));
const endings = new Map(world.endings.map(e => [e.scene, e.label]));
const directions = data.scene_direction;
let scene, flags, trace, beatIndex, visited;
function node(tag, text) {
  const n = document.createElement(tag); n.textContent = text; return n;
}
function button(text, fn) {
  const n = node("button", text); n.type = "button";
  n.addEventListener("click", fn); root.append(n); return n;
}
function reset() {
  scene = world.start; flags = new Set(); trace = []; beatIndex = 0;
  visited = new Set([scene]); render();
}
function advance(choice) {
  for (const flag of choice.grants) flags.add(flag);
  trace.push(choice.id); scene = choice.to; visited.add(scene);
  beatIndex = 0; render();
}
function render() {
  root.replaceChildren();
  const current = scenes.get(scene), direction = directions[scene];
  root.append(node("h1", direction.chapter.chapter_title),
              node("h2", direction.chapter.act_title),
              node("h3", current.title), node("p", current.narrative));
  const beats = direction.cinematic_beats;
  if (beatIndex < beats.length) {
    const beat = beats[beatIndex];
    root.append(node("h4", "Storyboard: " + beat.cue),
                node("p", beat.caption),
                node("p", "Beat " + (beatIndex + 1) + " of " + beats.length));
    const next = button(beatIndex + 1 === beats.length ? "Finish scene" : "Continue", () => {
      beatIndex += 1; render();
    });
    next.focus(); return;
  }
  const visitedActs = new Set(Array.from(visited).map(sid => directions[sid].chapter.act));
  const progress = node("nav", "Visited acts: " + Array.from(visitedActs).sort().join(", "));
  progress.setAttribute("aria-label", "Story progress"); root.append(progress);
  root.append(node("p", "Choices taken: " + trace.join(", ")));
  if (endings.has(scene)) {
    root.append(node("h2", "Ending: " + endings.get(scene)));
    button("Restart", reset); return;
  }
  for (const choice of world.choices.filter(c => c.from === scene &&
    c.requires.every(flag => flags.has(flag)))) button(choice.label, () => advance(choice));
}
reset();
""".strip()


def render_director_html(manifest: Any) -> bytes:
    if type(manifest) is not dict or manifest.get("schema") != SCHEMA:
        raise CanonError("director_invalid_manifest")
    # Do not trust caller-supplied proofs or source digests.
    expected = compile_director(
        manifest["world"], manifest["chapters"], manifest["cinematics"])
    if manifest != expected:
        raise CanonError("director_manifest_mismatch")
    payload = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_PLAYER_JS.encode()).digest()).decode("ascii")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "script-src 'sha256-" + policy + "'; connect-src 'none'; "
            'style-src \'none\'; img-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<title>' + html.escape(manifest["world_id"], quote=True) + ' director</title>'
            '</head><body><main id="play" aria-live="polite"></main>'
            '<script id="director-data" type="application/json">' + payload + '</script>'
            '<script>' + _PLAYER_JS + '</script></body></html>\n').encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("director_playable_too_large")
    return page


class DirectorStore:
    """One canonical world lease for all source reads, compile and verify."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.chapters = ChapterStore(root)
        self.cinematics = CinematicsStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".director.playable.html",
                world_id + ".director.manifest.json",
                world_id + ".director.receipt.json")

    def _sources(self, fd: int, world_id: str) -> tuple[Any, Any, Any]:
        _id(world_id, "world_id")
        world = strict_json(self.worlds._read(fd, world_id + ".json"))
        prove(world)
        if world["id"] != world_id:
            raise CanonError("identity_mismatch")
        chapters = self.chapters._source(fd, world_id, world)
        cinematics = self.cinematics._source(fd, world_id, world)
        return world, chapters, cinematics

    @staticmethod
    def _lock(fd: int, world_id: str) -> None:
        _id(world_id, "world_id")
        try:
            handle = os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                             os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None
        os.close(handle)

    def inspect(self, world_id: str) -> dict[str, Any]:
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                manifest = compile_director(*self._sources(fd, world_id))
                return {
                    "schema": SCHEMA, "world_id": world_id,
                    "source_digests": manifest["source_digests"],
                    "proof_digests": manifest["proof_digests"],
                    "scene_count": len(manifest["scene_direction"]),
                    "qualification": manifest["qualification"],
                }
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
                world, chapters, cinematics = self._sources(fd, world_id)
                session = validate_session(
                    strict_json(self.worlds._read(fd, SessionStore._name(world_id, slot))), world)
                return {
                    "slot": slot, "session_digest": digest(session),
                    "revision": session["revision"],
                    "player": replay_director(world, chapters, cinematics, session["choices"]),
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def _outputs(self, sources: tuple[Any, Any, Any]) -> tuple[dict[str, Any], bytes, bytes]:
        manifest = compile_director(*sources)
        playable = render_director_html(manifest)
        engine = canonical(manifest)
        if len(engine) > 1572864:
            raise CanonError("director_manifest_too_large")
        names = self._names(sources[0]["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": sources[0]["id"],
            "source_digests": manifest["source_digests"],
            "proof_digests": manifest["proof_digests"],
            "artifacts": {names[0]: sha256(playable).hexdigest(),
                          names[1]: sha256(engine).hexdigest()},
            "qualification": "source_verified_not_release_certified",
        }
        return receipt, playable, engine

    def compile(self, world_id: str, expected_digests: Any) -> dict[str, Any]:
        if type(expected_digests) is not dict or set(expected_digests) != set(SOURCE_NAMES):
            raise CanonError("director_invalid_lease")
        fd = self.worlds._directory()
        try:
            self._lock(fd, world_id)
            try:
                sources = self._sources(fd, world_id)
                receipt, playable, engine = self._outputs(sources)
                if receipt["source_digests"] != expected_digests:
                    raise CanonError("director_stale_source")
                names = self._names(world_id)
                self.worlds._write(fd, names[0], playable)
                self.worlds._write(fd, names[1], engine)
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
                receipt, playable, engine = self._outputs(sources)
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("director_receipt_mismatch")
                if _artifact_read(fd, names[0]) != playable or _artifact_read(fd, names[1]) != engine:
                    raise CanonError("director_artifact_mismatch")
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
