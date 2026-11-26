"""Locale-consistent original quest character playback handoff.

Combines reviewed original dialogue translations with canonical NPC trust,
stage localization, pacing, content consent and chosen ending. Never changes
quest outcomes or claims native gameplay.
"""
from __future__ import annotations

from html import escape
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _open_directory, _write_all,
)
from .studio_quest_private_io import read_studio_private_json
from .studio_quest_character_experience import (
    compile_quest_character_experience_handoff,
)
from .studio_quest_dialogue_localization import (
    compile_dialogue_localized_handoff,
)

SCHEMA = "skeleton.game_builder.studio_quest_character_locale_handoff.v1"
FILENAME = "studio_quest_character_locale.json"
MAX_RECEIPT = 524288
MAX_HTML = 524288


def compile_quest_character_locale_handoff(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    dialogue_locale: object, localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("localized character experience requires authorization")
    before = _canonical(documents)
    if len(before) > 256 * 1024:
        raise StudioQuestError("localized character source exceeds byte budget")
    character = compile_quest_character_experience_handoff(
        documents, branch, npc, dialogue, localization, achievements,
        pacing, advisories, accepted_topics, authorized=True)
    translated = compile_dialogue_localized_handoff(
        documents, npc, dialogue, dialogue_locale, authorized=True)
    if (translated["source_digest"] != character["source_digest"]
            or translated["session_digest"] != character["session_digest"]
            or translated["target_ending"] != character["target_ending"]
            or translated["canonical_choices"] != [
                [x["stage_id"], x["choice"]] for x in character["events"]]):
        raise StudioQuestError("localized character source/session/ending diverged")
    stage_locale = localization["authoring"]["locale"]
    if stage_locale != translated["locale"]:
        raise StudioQuestError("mixed stage and dialogue locales are not playable")
    indexed = {
        (x["stage_id"], x["choice"], x["beat_index"], x["speaker"]): x
        for x in translated["localized_dialogue_lines"]
    }
    if len(indexed) != len(translated["localized_dialogue_lines"]):
        raise StudioQuestError("duplicate localized dialogue identity")
    events: list[dict[str, Any]] = []
    used: set[tuple[str, str, int, str]] = set()
    for event in character["events"]:
        lines = []
        for original in event["dialogue"]:
            key = (original["stage_id"], original["choice"],
                   original["beat_index"], original["speaker"])
            row = indexed.get(key)
            if row is None or row["original"] != original["text"]:
                raise StudioQuestError("localized character dialogue identity diverged")
            used.add(key)
            lines.append({
                "stage_id": original["stage_id"], "choice": original["choice"],
                "beat_index": original["beat_index"], "speaker": original["speaker"],
                "original": original["text"], "display": row["display"],
                "delivery": original["delivery"], "reviewed": True,
            })
        events.append({**event, "dialogue": lines})
    if len(used) != len(indexed) or _canonical(documents) != before:
        raise StudioQuestError("localized character coverage or source changed")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": character["project_id"],
        "source_digest": character["source_digest"],
        "session_digest": character["session_digest"],
        "target_ending": character["target_ending"],
        "locale": translated["locale"],
        "character_experience_digest": character["character_experience_digest"],
        "dialogue_localization_digest": translated["dialogue_localization_digest"],
        "events": events, "final_trust": character["final_trust"],
        "localized_display_rows": character["localized_display_rows"],
        "advisory_descriptors": character["advisory_descriptors"],
        "unlocked_achievements": character["unlocked_achievements"],
        "sandbox_points": character["sandbox_points"],
        "canonical_quest_replay_verified": True,
        "translation_provenance_verified": False,
        "native_gameplay_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("localized character handoff exceeds byte budget")
    result["handoff_digest"] = _digest(result)
    return result


def publish_quest_character_locale(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    dialogue_locale: object, localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object,
    directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    checked = compile_quest_character_locale_handoff(
        documents, branch, npc, dialogue, dialogue_locale, localization,
        achievements, pacing, advisories, accepted_topics, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("localized character publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".quest-character-locale-" + secrets.token_hex(16) + ".tmp"
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
                raise StudioQuestError("localized character output directory changed")
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
            "handoff_digest": checked["handoff_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_quest_character_locale(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    dialogue_locale: object, localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object,
    directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("localized character restore requires authorization")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    current = compile_quest_character_locale_handoff(
        documents, branch, npc, dialogue, dialogue_locale, localization,
        achievements, pacing, advisories, accepted_topics, authorized=True)
    if _canonical(current) != _canonical(stored):
        raise StudioQuestError("localized character restore differs from replay")
    return current


def render_quest_character_locale_html(
    documents: Mapping[str, Any], branch: object, npc: object, dialogue: object,
    dialogue_locale: object, localization: object, achievements: object,
    pacing: object, advisories: object, accepted_topics: object, *,
    authorized: bool,
) -> bytes:
    checked = compile_quest_character_locale_handoff(
        documents, branch, npc, dialogue, dialogue_locale, localization,
        achievements, pacing, advisories, accepted_topics, authorized=authorized)
    rows = "".join(
        '<section><h2>' + escape(event["stage_id"] + " / " + event["choice"]) +
        '</h2><ol>' + "".join(
            '<li><strong>' + escape(line["speaker"]) + '</strong>: ' +
            escape(line["display"]) + '</li>'
            for line in event["dialogue"]) + '</ol></section>'
        for event in checked["events"])
    html = (
        '<!doctype html><html lang="' + escape(checked["locale"], quote=True) +
        '"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; connect-src 'none'; base-uri 'none'; form-action 'none'; "
        'object-src \'none\'">'
        '<title>Original localized quest walkthrough</title></head><body><main>'
        '<h1>Localized original character replay</h1>' + rows +
        '<p>Canonical authored session only; no native gameplay claim.</p>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("localized character HTML exceeds byte budget")
    return html
