"""Human-reviewed voice direction for original localized quest dialogue.

Produces deterministic performance descriptors, never audio or voice likenesses.
All authored cues are bound to canonical quest, locale, choice and speaker IDs.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _digest, _open_directory, _write_all
from .studio_quest_private_io import read_studio_private_json
from .studio_quest_character_locale import compile_quest_character_locale_handoff

PLAN_SCHEMA = "skeleton.game_builder.quest_voice_direction_plan.v1"
SCHEMA = "skeleton.game_builder.quest_voice_direction.v1"
PROMPT = "direct performances for my original localized quest dialogue"
FILENAME = "studio_quest_voice_direction.json"
MAX_ROWS = 128
MAX_PLAN = 256 * 1024
MAX_RECEIPT = 384 * 1024
MAX_HTML = 512 * 1024
STYLES = frozenset(("neutral", "gentle", "urgent", "solemn", "hopeful", "wary"))
RATES = frozenset(("slow", "measured", "natural", "brisk"))


def _base(documents: Mapping[str, Any], parts: tuple[object, ...]) -> dict[str, Any]:
    if len(parts) != 9:
        raise StudioQuestError("voice direction requires nine canonical quest inputs")
    return compile_quest_character_locale_handoff(documents, *parts, authorized=True)


def _rows(base: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for event in base["events"]:
        for line in event["dialogue"]:
            rows.append({
                "stage_id": line["stage_id"], "choice": line["choice"],
                "beat_index": line["beat_index"], "speaker": line["speaker"],
                "display": line["display"],
            })
    if not rows or len(rows) > MAX_ROWS:
        raise StudioQuestError("voice direction dialogue count exceeds budget")
    return rows


def _clean_note(value: object) -> str:
    if (type(value) is not str or len(value) > 240 or value.strip() != value
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in
                   "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
                   for c in value)):
        raise StudioQuestError("invalid bounded voice director note")
    return value


def _plan(plan: object, base: Mapping[str, Any]) -> dict[str, Any]:
    if (type(plan) is not dict or set(plan) != {
            "schema", "source_digest", "handoff_digest", "locale", "rows"}
            or plan["schema"] != PLAN_SCHEMA
            or len(_canonical(plan)) > MAX_PLAN
            or plan["source_digest"] != base["source_digest"]
            or plan["handoff_digest"] != base["handoff_digest"]
            or plan["locale"] != base["locale"]):
        raise StudioQuestError("stale or invalid typed voice direction plan")
    expected = _rows(base)
    authored = plan["rows"]
    if type(authored) is not list or len(authored) != len(expected):
        raise StudioQuestError("voice direction requires complete canonical coverage")
    clean = []
    for original, row in zip(expected, authored):
        if (type(row) is not dict or set(row) != {
                "stage_id", "choice", "beat_index", "speaker", "display",
                "style", "rate", "pause_after_ms", "director_note", "reviewed"}):
            raise StudioQuestError("invalid typed voice direction row")
        if any(row[k] != original[k] for k in original):
            raise StudioQuestError("voice direction changed canonical dialogue identity")
        if (type(row["style"]) is not str or row["style"] not in STYLES
                or type(row["rate"]) is not str or row["rate"] not in RATES
                or type(row["pause_after_ms"]) is not int
                or not 0 <= row["pause_after_ms"] <= 4000
                or type(row["reviewed"]) is not bool):
            raise StudioQuestError("invalid bounded voice performance")
        clean.append({**original, "style": row["style"], "rate": row["rate"],
                      "pause_after_ms": row["pause_after_ms"],
                      "director_note": _clean_note(row["director_note"]),
                      "reviewed": row["reviewed"]})
    return {**{k: plan[k] for k in ("schema", "source_digest",
                                    "handoff_digest", "locale")}, "rows": clean}


def propose_voice_direction(
    documents: Mapping[str, Any], *parts: object, prompt: str,
    expected_handoff_digest: str, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("voice direction proposal requires authorization")
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported original voice direction prompt")
    base = _base(documents, parts)
    if base["handoff_digest"] != expected_handoff_digest:
        raise StudioQuestError("stale voice direction handoff lease")
    plan = {
        "schema": PLAN_SCHEMA, "source_digest": base["source_digest"],
        "handoff_digest": base["handoff_digest"], "locale": base["locale"],
        "rows": [{**row, "style": "neutral", "rate": "natural",
                  "pause_after_ms": 0, "director_note": "", "reviewed": False}
                 for row in _rows(base)],
    }
    if len(_canonical(plan)) > MAX_PLAN:
        raise StudioQuestError("voice direction proposal exceeds byte budget")
    return plan


def compile_voice_direction(
    documents: Mapping[str, Any], *parts: object, plan: object,
    expected_handoff_digest: str, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("voice direction compile requires authorization")
    before = _canonical(documents)
    base = _base(documents, parts)
    if base["handoff_digest"] != expected_handoff_digest:
        raise StudioQuestError("stale voice direction source lease")
    checked = _plan(plan, base)
    if not all(row["reviewed"] for row in checked["rows"]):
        raise StudioQuestError("voice direction requires human review of every cue")
    if _canonical(documents) != before:
        raise StudioQuestError("canonical quest changed during voice compilation")
    receipt: dict[str, Any] = {
        "schema": SCHEMA, "project_id": base["project_id"],
        "source_digest": base["source_digest"],
        "session_digest": base["session_digest"],
        "handoff_digest": base["handoff_digest"],
        "target_ending": base["target_ending"], "locale": base["locale"],
        "authoring": checked, "cue_count": len(checked["rows"]),
        "canonical_quest_replay_verified": True,
        "human_reviewed": True, "audio_generated": False,
        "voice_identity_verified": False, "native_gameplay_verified": False,
        "release_certified": False,
    }
    if len(_canonical(receipt)) > MAX_RECEIPT - 128:
        raise StudioQuestError("voice direction receipt exceeds byte budget")
    receipt["voice_direction_digest"] = _digest(receipt)
    return receipt


def replay_voice_direction(
    documents: Mapping[str, Any], *parts: object, receipt: object,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("voice direction replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid voice direction replay receipt")
    checked = compile_voice_direction(
        documents, *parts, plan=receipt.get("authoring"),
        expected_handoff_digest=receipt.get("handoff_digest"), authorized=True)
    if _canonical(checked) != _canonical(receipt):
        raise StudioQuestError("voice direction receipt differs from canonical replay")
    return checked


def publish_voice_direction(
    documents: Mapping[str, Any], *parts: object, receipt: object,
    directory: Path, authorized: bool,
) -> dict[str, Any]:
    checked = replay_voice_direction(documents, *parts, receipt=receipt,
                                     authorized=authorized)
    raw = _canonical(checked) + b"\n"
    if len(raw) > MAX_RECEIPT:
        raise StudioQuestError("voice direction publication exceeds byte budget")
    fd = _open_directory(directory)
    temp = ".quest-voice-" + secrets.token_hex(16) + ".tmp"
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
                raise StudioQuestError("voice direction output directory changed")
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
            "voice_direction_digest": checked["voice_direction_digest"],
            "bytes": len(raw), "file_write_performed": True,
            "release_certified": False}


def restore_voice_direction(
    documents: Mapping[str, Any], *parts: object, directory: Path,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("voice direction restore requires authorization")
    stored = read_studio_private_json(Path(directory) / FILENAME, MAX_RECEIPT)
    return replay_voice_direction(documents, *parts, receipt=stored,
                                  authorized=True)


_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const plan = JSON.parse(byId('plan').textContent);
      plan.rows = plan.rows.map((row, i) => ({
        ...row,
        style: byId('style-' + i).value,
        rate: byId('rate-' + i).value,
        pause_after_ms: Number(byId('pause-' + i).value),
        director_note: byId('note-' + i).value,
        reviewed: byId('review-' + i).checked
      }));
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 262144) throw Error('oversize');
      const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'original-quest-voice-direction.json';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical CLI compile and review required.';
    } catch (_) { byId('status').textContent = 'Invalid edit; no export.'; }
  });
})();"""


def render_voice_direction_editor(
    documents: Mapping[str, Any], *parts: object, plan: object,
    authorized: bool,
) -> bytes:
    if authorized is not True:
        raise PermissionError("voice direction editor requires authorization")
    base = _base(documents, parts)
    checked = _plan(plan, base)
    rows = []
    for i, row in enumerate(checked["rows"]):
        def select(field: str, choices: frozenset[str]) -> str:
            return ('<select id="' + field + '-' + str(i) + '">' +
                    ''.join('<option value="' + escape(value, quote=True) + '"' +
                            (' selected' if value == row[field] else '') +
                            '>' + escape(value) + '</option>'
                            for value in sorted(choices)) + '</select>')
        rows.append(
            '<fieldset><legend>' + escape(row["speaker"] + " / " +
                row["stage_id"] + " / " + row["choice"]) + '</legend><p>' +
            escape(row["display"]) + '</p><label>Style' +
            select("style", STYLES) + '</label><label>Rate' +
            select("rate", RATES) + '</label><label>Pause milliseconds'
            '<input type="number" min="0" max="4000" step="1" id="pause-' +
            str(i) + '" value="' + str(row["pause_after_ms"]) +
            '"></label><label>Director note<textarea maxlength="240" id="note-' +
            str(i) + '">' + escape(row["director_note"]) +
            '</textarea></label><label>Reviewed<input type="checkbox" id="review-' +
            str(i) + '"' + (' checked' if row["reviewed"] else '') +
            '></label></fieldset>')
    plan_json = _canonical(checked).decode("ascii").replace("<", "\\u003c")
    hash_value = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hash_value +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = ('<!doctype html><html lang="' + escape(base["locale"], quote=True) +
            '"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
            'content="' + csp + '"><title>Original quest voice direction</title>'
            '</head><body><main><h1>Review original voice performance cues</h1>'
            '<p>Descriptor only. No audio, identity imitation or native gameplay.</p>' +
            ''.join(rows) + '<script type="application/json" id="plan">' +
            plan_json + '</script><button type="button" id="export">Export reviewed plan'
            '</button><p id="status" role="status" aria-live="polite"></p></main>'
            '<script>' + _SCRIPT + '</script></body></html>').encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("voice direction HTML exceeds byte budget")
    return html


def render_voice_direction_preview(
    documents: Mapping[str, Any], *parts: object, receipt: object,
    authorized: bool,
) -> bytes:
    checked = replay_voice_direction(documents, *parts, receipt=receipt,
                                     authorized=authorized)
    rows = ''.join(
        '<li><strong>' + escape(row["speaker"]) + '</strong> — ' +
        escape(row["display"]) + ' (' + escape(row["style"]) + ', ' +
        escape(row["rate"]) + ', ' + str(row["pause_after_ms"]) + 'ms)' +
        (' — ' + escape(row["director_note"]) if row["director_note"] else '') +
        '</li>' for row in checked["authoring"]["rows"])
    html = ('<!doctype html><html lang="' + escape(checked["locale"], quote=True) +
            '"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
            'content="default-src \'none\'; connect-src \'none\'; base-uri \'none\'; '
            'form-action \'none\'; object-src \'none\'">'
            '<title>Quest voice direction preview</title></head><body><main>'
            '<h1>Reviewed original quest performance cues</h1><ol>' + rows +
            '</ol><p>No audio synthesized or release certification.</p>'
            '</main></body></html>').encode("utf-8")
    if len(html) > MAX_HTML:
        raise StudioQuestError("voice direction preview exceeds byte budget")
    return html
