"""Playable-adapter handoff for original quest experience, NPC trust and dialogue.

All inputs are independently replayed against one authoritative source and
one canonical action history. An HTML walkthrough is not a native game test.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json
from .studio_quest_branch_review import compile_quest_branch_handoff
from .studio_quest_npc_relationships import compile_npc_relationship_handoff
from .studio_quest_dialogue import compile_quest_dialogue_handoff
from .studio_quest_experience_handoff import compile_quest_experience_handoff

SCHEMA = "skeleton.game_builder.studio_quest_character_experience.v1"
HANDOFF_SCHEMA = "skeleton.game_builder.studio_quest_character_experience_handoff.v1"
FILENAME = "studio_quest_character_experience.json"
MAX_SOURCE = 256 * 1024
MAX_RECEIPT = 393216
MAX_HTML = 524288


def compile_quest_character_experience(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    localization: object, achievements: object, pacing: object,
    advisories: object, accepted_topics: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("character experience requires authorization")
    before = _canonical(documents)
    if len(before) > MAX_SOURCE:
        raise StudioQuestError("character experience source exceeds byte budget")
    program = compile_quest_program(documents)
    route = compile_quest_branch_handoff(documents, branch, authorized=True)
    people = compile_npc_relationship_handoff(documents, npc, authorized=True)
    lines = compile_quest_dialogue_handoff(
        documents, npc, dialogue, authorized=True)
    experience = compile_quest_experience_handoff(
        documents, localization, achievements, pacing, advisories,
        accepted_topics, authorized=True)
    components = (route, people, lines, experience)
    if any(x["source_digest"] != program.source_digest for x in components):
        raise StudioQuestError("character experience source leases diverged")
    if (len({x["session_digest"] for x in components}) != 1
            or len({x["target_ending"] for x in components}) != 1
            or any(x["canonical_choices"] != route["canonical_choices"]
                   for x in components)):
        raise StudioQuestError("character experience actions or endings diverged")
    session = replay_quest(
        documents, route["canonical_choices"], authorized=True)
    if session.digest != route["session_digest"]:
        raise StudioQuestError("character experience canonical replay diverged")
    events: list[dict[str, Any]] = []
    for index, (stage, choice) in enumerate(session.choices):
        event = {
            "index": index, "stage_id": stage, "choice": choice,
            "dialogue": [x for x in lines["authored_dialogue_lines"]
                         if x["stage_id"] == stage and x["choice"] == choice],
            "npc_trust_effects": [x for x in people["applied_relationship_effects"]
                                  if x["stage_id"] == stage and x["choice"] == choice],
            "pacing": next((x for x in experience["pacing_timeline"]
                            if x["stage_id"] == stage and x["choice"] == choice), None),
        }
        if event["pacing"] is None or not event["dialogue"]:
            raise StudioQuestError("character experience missing played event evidence")
        events.append(event)
    if _canonical(documents) != before:
        raise StudioQuestError("character experience source changed during assembly")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": program.source_digest,
        "session_digest": session.digest,
        "target_ending": route["target_ending"],
        "branch_review_digest": route["branch_review_digest"],
        "npc_relationship_digest": people["relationship_digest"],
        "dialogue_digest": lines["dialogue_digest"],
        "experience_bundle_digest": experience["bundle_digest"],
        "accepted_topics": experience["current_consent"]["accepted_topics"],
        "current_consent_digest": experience["current_consent"]["consent_digest"],
        "event_count": len(events), "events": events,
        "final_trust": people["final_trust"],
        "localized_display_rows": experience["localized_display_rows"],
        "advisory_descriptors": experience["advisory_descriptors"],
        "unlocked_achievements": experience["unlocked_achievements"],
        "sandbox_points": experience["sandbox_points"],
        "canonical_quest_replay_verified": True,
        "npc_behavior_observed": False, "voice_audio_generated": False,
        "native_gameplay_verified": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("character experience receipt exceeds byte budget")
    result["character_experience_digest"] = _digest(result)
    return result


def compile_quest_character_experience_handoff(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    localization: object, achievements: object, pacing: object,
    advisories: object, accepted_topics: object, *, authorized: bool,
) -> dict[str, Any]:
    checked = compile_quest_character_experience(
        documents, branch, npc, dialogue, localization, achievements,
        pacing, advisories, accepted_topics, authorized=authorized)
    result = {
        "schema": HANDOFF_SCHEMA, "project_id": checked["project_id"],
        "source_digest": checked["source_digest"],
        "session_digest": checked["session_digest"],
        "target_ending": checked["target_ending"],
        "character_experience_digest": checked["character_experience_digest"],
        "events": checked["events"],
        "final_trust": checked["final_trust"],
        "localized_display_rows": checked["localized_display_rows"],
        "advisory_descriptors": checked["advisory_descriptors"],
        "unlocked_achievements": checked["unlocked_achievements"],
        "sandbox_points": checked["sandbox_points"],
        "canonical_quest_replay_verified": True,
        "native_gameplay_verified": False, "release_certified": False,
    }
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_character_experience(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    localization: object, achievements: object, pacing: object,
    advisories: object, accepted_topics: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    checked = compile_quest_character_experience(
        documents, branch, npc, dialogue, localization, achievements,
        pacing, advisories, accepted_topics, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("character experience publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".quest-character-experience-" + secrets.token_hex(16) + ".tmp"
    created = False
    linked = False
    try:
        before = os.fstat(fd)
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        linked = True
        os.fsync(fd)
        verify_fd = _open_directory(directory)
        try:
            after = os.fstat(verify_fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise StudioQuestError("character experience output directory changed")
        finally:
            os.close(verify_fd)
    except BaseException:
        if linked:
            os.unlink(FILENAME, dir_fd=fd)
            os.fsync(fd)
        raise
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / FILENAME),
            "character_experience_digest": checked["character_experience_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_character_experience(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    localization: object, achievements: object, pacing: object,
    advisories: object, accepted_topics: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("character experience restore requires authorization")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    current = compile_quest_character_experience(
        documents, branch, npc, dialogue, localization, achievements,
        pacing, advisories, accepted_topics, authorized=True)
    if _canonical(current) != _canonical(stored):
        raise StudioQuestError("character experience receipt differs from replay")
    return current


_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const events = JSON.parse(byId('events').textContent);
  let index = 0;
  function show() {
    const e = events[index];
    byId('stage').textContent = e.stage_id + ' / ' + e.choice;
    byId('lines').textContent = e.dialogue.map(x => x.speaker + ': ' + x.text).join('\\n');
    byId('trust').textContent = e.npc_trust_effects.map(x =>
      x.actor_id + ' ' + x.before + ' → ' + x.after).join(', ');
    byId('position').textContent = (index + 1) + ' / ' + events.length;
  }
  byId('prev').addEventListener('click', () => { index = Math.max(0, index - 1); show(); });
  byId('next').addEventListener('click', () => { index = Math.min(events.length - 1, index + 1); show(); });
  show();
})();"""


def render_quest_character_walkthrough_html(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    localization: object, achievements: object, pacing: object,
    advisories: object, accepted_topics: object, *, authorized: bool,
) -> bytes:
    checked = compile_quest_character_experience(
        documents, branch, npc, dialogue, localization, achievements,
        pacing, advisories, accepted_topics, authorized=authorized)
    if not checked["events"]:
        raise StudioQuestError("character walkthrough requires played events")
    events_json = _canonical(checked["events"]).decode("ascii").replace("<", "\\u003c")
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original quest character walkthrough</title></head><body><main>'
        '<h1>Canonical quest character walkthrough</h1>'
        '<p>This is an offline authored replay preview, not native gameplay.</p>'
        '<h2 id="stage"></h2><pre id="lines"></pre><p id="trust"></p>'
        '<p id="position" role="status" aria-live="polite"></p>'
        '<button type="button" id="prev">Previous event</button>'
        '<button type="button" id="next">Next event</button>'
        '<script type="application/json" id="events">' + events_json + '</script>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("character walkthrough exceeds HTML byte budget")
    return html
