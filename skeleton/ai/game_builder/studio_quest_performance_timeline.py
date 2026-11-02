"""Source-replayed quest dialogue/chronology performance budget handoff.

This is a deterministic authored preview: character count estimates are not
speech synthesis, observed playback, native audio timing or device evidence.
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
from .studio_quest_character_locale import compile_quest_character_locale_handoff
from .studio_quest_voice_direction import replay_voice_direction
from .studio_quest_chronology import replay_quest_chronology

PLAN_SCHEMA = "skeleton.game_builder.quest_performance_timeline_plan.v1"
SCHEMA = "skeleton.game_builder.quest_performance_timeline.v1"
PROMPT = "align reviewed original quest dialogue cues with causal scene windows"
FILENAME = "studio_quest_performance_timeline.json"
MAX_PLAN = 128 * 1024
MAX_RECEIPT = 384 * 1024
MAX_HTML = 256 * 1024
MAX_EVENTS = 64
MAX_CUES = 128


def _components(
    documents: Mapping[str, Any], parts: tuple[object, ...],
    voice_receipt: object, chronology_receipt: object,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if len(parts) != 9:
        raise StudioQuestError("performance timeline requires canonical quest inputs")
    base = compile_quest_character_locale_handoff(
        documents, *parts, authorized=True)
    voice = replay_voice_direction(
        documents, *parts, receipt=voice_receipt, authorized=True)
    chrono = replay_quest_chronology(
        documents, chronology_receipt, authorized=True)
    if (base["source_digest"] != voice["source_digest"]
            or base["source_digest"] != chrono["source_digest"]
            or base["session_digest"] != voice["session_digest"]
            or base["session_digest"] != chrono["session_digest"]
            or base["handoff_digest"] != voice["handoff_digest"]):
        raise StudioQuestError("performance timeline source/session leases diverged")
    played = [(x["stage_id"], x["choice"]) for x in base["events"]]
    timed = [(x["stage_id"], x["choice"]) for x in chrono["timeline"]]
    if not played or played != timed or len(played) > MAX_EVENTS:
        raise StudioQuestError("performance timeline played events differ")
    cues = [(x["stage_id"], x["choice"]) for x in voice["authoring"]["rows"]]
    if not cues or len(cues) > MAX_CUES or set(cues) != set(played):
        raise StudioQuestError("performance timeline voice coverage differs")
    return base, voice, chrono


def propose_performance_timeline(
    documents: Mapping[str, Any], *parts: object,
    voice_receipt: object, chronology_receipt: object,
    prompt: str, expected_voice_digest: str,
    expected_chronology_digest: str, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("performance timeline proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported performance timeline prompt")
    base, voice, chrono = _components(
        documents, parts, voice_receipt, chronology_receipt)
    if (voice["voice_direction_digest"] != expected_voice_digest
            or chrono["chronology_digest"] != expected_chronology_digest):
        raise StudioQuestError("stale performance timeline lease")
    plan = {
        "schema": PLAN_SCHEMA, "source_digest": base["source_digest"],
        "session_digest": base["session_digest"],
        "voice_direction_digest": voice["voice_direction_digest"],
        "chronology_digest": chrono["chronology_digest"],
        "rows": [{
            "stage_id": event["stage_id"], "choice": event["choice"],
            "buffer_ms": 1000, "reviewed": False,
        } for event in base["events"]],
    }
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("performance timeline proposal exceeds budget")
    return plan


def compile_performance_timeline(
    documents: Mapping[str, Any], *parts: object,
    voice_receipt: object, chronology_receipt: object, plan: object,
    expected_voice_digest: str, expected_chronology_digest: str,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("performance timeline compile requires authorization")
    before = _canonical(documents)
    base, voice, chrono = _components(
        documents, parts, voice_receipt, chronology_receipt)
    if (voice["voice_direction_digest"] != expected_voice_digest
            or chrono["chronology_digest"] != expected_chronology_digest):
        raise StudioQuestError("stale performance timeline compile lease")
    if (type(plan) is not dict or set(plan) != {
            "schema", "source_digest", "session_digest",
            "voice_direction_digest", "chronology_digest", "rows"}
            or plan["schema"] != PLAN_SCHEMA
            or len(_canonical(plan)) > MAX_PLAN
            or plan["source_digest"] != base["source_digest"]
            or plan["session_digest"] != base["session_digest"]
            or plan["voice_direction_digest"] != expected_voice_digest
            or plan["chronology_digest"] != expected_chronology_digest
            or type(plan["rows"]) is not list
            or len(plan["rows"]) != len(base["events"])):
        raise StudioQuestError("invalid typed performance timeline plan")
    timeline = []
    checked_rows = []
    for event, window, authored in zip(
            base["events"], chrono["timeline"], plan["rows"]):
        if (type(authored) is not dict or set(authored) != {
                "stage_id", "choice", "buffer_ms", "reviewed"}
                or authored["stage_id"] != event["stage_id"]
                or authored["choice"] != event["choice"]):
            raise StudioQuestError("performance timeline changed canonical event identity")
        buffer_ms = authored["buffer_ms"]
        if (type(buffer_ms) is not int or not 0 <= buffer_ms <= 30000
                or authored["reviewed"] is not True):
            raise StudioQuestError("performance timeline needs reviewed bounded buffer")
        lines = [x for x in voice["authoring"]["rows"]
                 if x["stage_id"] == event["stage_id"]
                 and x["choice"] == event["choice"]]
        if not lines:
            raise StudioQuestError("performance timeline missing original dialogue")
        # 70ms/Unicode codepoint is an explicit conservative planning estimate.
        estimated_ms = sum(
            max(300, len(line["display"]) * 70) + line["pause_after_ms"]
            for line in lines)
        allocated_ms = window["duration_minutes"] * 60000
        if estimated_ms + buffer_ms > allocated_ms:
            raise StudioQuestError("reviewed dialogue exceeds authored time window")
        checked_rows.append({
            "stage_id": event["stage_id"], "choice": event["choice"],
            "buffer_ms": buffer_ms, "reviewed": True,
        })
        timeline.append({
            "stage_id": event["stage_id"], "choice": event["choice"],
            "start_minute": window["start_minute"],
            "end_minute": window["end_minute"],
            "cue_count": len(lines),
            "estimated_dialogue_ms": estimated_ms,
            "reviewed_buffer_ms": buffer_ms,
            "available_window_ms": allocated_ms,
            "remaining_ms": allocated_ms - estimated_ms - buffer_ms,
        })
    if _canonical(documents) != before:
        raise StudioQuestError("performance timeline source changed during compile")
    checked_plan = {**{k: plan[k] for k in (
        "schema", "source_digest", "session_digest",
        "voice_direction_digest", "chronology_digest")}, "rows": checked_rows}
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": base["project_id"],
        "source_digest": base["source_digest"],
        "session_digest": base["session_digest"],
        "target_ending": base["target_ending"],
        "locale": base["locale"],
        "voice_direction_digest": expected_voice_digest,
        "chronology_digest": expected_chronology_digest,
        "authoring": checked_plan, "timeline": timeline,
        "canonical_quest_replay_verified": True,
        "authored_window_fit_verified": True,
        "estimated_not_observed": True,
        "audio_generated": False,
        "native_gameplay_verified": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT - 128:
        raise StudioQuestError("performance timeline receipt exceeds budget")
    result["performance_timeline_digest"] = _digest(result)
    return result


def replay_performance_timeline(
    documents: Mapping[str, Any], *parts: object,
    voice_receipt: object, chronology_receipt: object,
    receipt: object, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("performance timeline replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid performance timeline receipt")
    checked = compile_performance_timeline(
        documents, *parts, voice_receipt=voice_receipt,
        chronology_receipt=chronology_receipt,
        plan=receipt.get("authoring"),
        expected_voice_digest=receipt.get("voice_direction_digest"),
        expected_chronology_digest=receipt.get("chronology_digest"),
        authorized=True)
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("performance timeline differs from replay")
    return checked


def publish_performance_timeline(
    documents: Mapping[str, Any], *parts: object,
    voice_receipt: object, chronology_receipt: object,
    receipt: object, directory: Path, authorized: bool,
) -> dict[str, Any]:
    checked = replay_performance_timeline(
        documents, *parts, voice_receipt=voice_receipt,
        chronology_receipt=chronology_receipt,
        receipt=receipt, authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("performance timeline publication exceeds budget")
    fd = _open_directory(directory)
    temp = ".quest-performance-" + secrets.token_hex(16) + ".tmp"
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
                raise StudioQuestError("performance timeline directory changed")
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
            "performance_timeline_digest": checked["performance_timeline_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_performance_timeline(
    documents: Mapping[str, Any], *parts: object,
    voice_receipt: object, chronology_receipt: object,
    directory: Path, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("performance timeline restore requires authorization")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    return replay_performance_timeline(
        documents, *parts, voice_receipt=voice_receipt,
        chronology_receipt=chronology_receipt,
        receipt=stored, authorized=True)


def render_performance_timeline_html(
    documents: Mapping[str, Any], *parts: object,
    voice_receipt: object, chronology_receipt: object,
    receipt: object, authorized: bool,
) -> bytes:
    checked = replay_performance_timeline(
        documents, *parts, voice_receipt=voice_receipt,
        chronology_receipt=chronology_receipt,
        receipt=receipt, authorized=authorized)
    rows = "".join(
        '<li>' + escape(x["stage_id"] + " / " + x["choice"]) +
        ": " + str(x["estimated_dialogue_ms"]) +
        " ms estimated dialogue; " + str(x["remaining_ms"]) +
        " ms remaining.</li>" for x in checked["timeline"])
    html = ('<!doctype html><html lang="' + escape(checked["locale"], quote=True) +
            '"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
            'content="default-src \'none\'; connect-src \'none\'; base-uri \'none\'; '
            'object-src \'none\'"><title>Quest performance timeline</title></head>'
            '<body><main><h1>Original quest performance window proof</h1><ol>' +
            rows + '</ol><p>Planning estimate only; no observed speech or engine playback.'
            '</p></main></body></html>').encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("performance timeline HTML exceeds budget")
    return html
