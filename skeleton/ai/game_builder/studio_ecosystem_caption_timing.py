"""Source-leased, deterministic human timing edits for authored story captions.

A timing edit changes only synthetic reading durations. The canonical
accessibility compiler remains the sole owner of caption words and order.
Neither a preview nor a saved VTT proves audio sync, dubbing or release.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import re
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_scene_schedule import _canonical, _digest, _lease
from .studio_ecosystem_story_accessibility import (
    MAX_OUTPUT_BYTES, compile_story_accessibility,
)

SCHEMA = "skeleton.game_builder.caption_timing_edit.v1"
MAX_EDITS = 64
MAX_REQUEST_BYTES = 4096
MIN_DURATION_MS = 1000
MAX_DURATION_MS = 30000
MAX_TIMELINE_MS = 35999999
_STAMP = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})$")
_CUE = re.compile(r"^([0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}) --> ([0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3})$")
_CSS = (
    ":root{color-scheme:dark;background:#14202c;color:#f6f8fb;"
    "font:16px system-ui}body{max-width:65rem;margin:auto;padding:2rem}"
    "li{padding:1rem;margin:1rem 0;border:1px solid #93bad1;border-radius:.5rem}"
    "time{font-variant-numeric:tabular-nums}strong{color:#ffe4a6}"
    "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
)


def _stamp(milliseconds: int) -> str:
    if type(milliseconds) is not int or not 0 <= milliseconds <= MAX_TIMELINE_MS:
        raise StudioQuestError("caption timeline exceeded bounded duration")
    seconds, fraction = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{fraction:03d}"


def _millis(stamp: str) -> int:
    match = _STAMP.fullmatch(stamp)
    if match is None:
        raise StudioQuestError("malformed canonical caption timestamp")
    hours, minutes, seconds, fraction = map(int, match.groups())
    if hours > 9 or minutes > 59 or seconds > 59:
        raise StudioQuestError("canonical caption timestamp exceeds range")
    return (((hours * 60 + minutes) * 60 + seconds) * 1000 + fraction)


def _canonical_cues(webvtt: str, expected: int) -> list[tuple[str, int]]:
    """Reject unexpected WebVTT shape rather than silently dropping captions."""
    if type(webvtt) is not str or not webvtt.startswith("WEBVTT\n\n"):
        raise StudioQuestError("invalid canonical WebVTT header")
    parts = webvtt.split("\n\n")
    if (len(parts) != expected + 2 or parts[0] != "WEBVTT"
            or not parts[1].startswith("NOTE Authored sandbox reading estimates only.\n"
                                       "NOTE Source digest: ")):
        raise StudioQuestError("canonical caption block count differs from manifest")
    cues: list[tuple[str, int]] = []
    previous_end = 0
    for index, block in enumerate(parts[2:], 1):
        lines = block.splitlines()
        if len(lines) != 3 or lines[0] != str(index) or not lines[2]:
            raise StudioQuestError("malformed canonical caption block")
        match = _CUE.fullmatch(lines[1])
        if match is None:
            raise StudioQuestError("malformed canonical caption timing")
        start, end = (_millis(stamp) for stamp in match.groups())
        if start != previous_end or end <= start:
            raise StudioQuestError("canonical caption order or duration mismatch")
        cues.append((lines[2], end - start))
        previous_end = end
    return cues


def _validated_edits(edits: object, cue_count: int) -> dict[str, int]:
    if (type(edits) is not dict or not 1 <= len(edits) <= MAX_EDITS
            or len(_canonical(edits)) > MAX_REQUEST_BYTES):
        raise StudioQuestError("caption timing requires bounded exact edits")
    checked: dict[str, int] = {}
    for key, duration in edits.items():
        if (type(key) is not str or not key.isascii() or not key.isdecimal()
                or key.startswith("0") or str(int(key)) != key
                or not 1 <= int(key) <= cue_count):
            raise StudioQuestError("caption edit references an invalid cue index")
        if (type(duration) is not int
                or not MIN_DURATION_MS <= duration <= MAX_DURATION_MS):
            raise StudioQuestError("caption duration must be a bounded integer")
        checked[key] = duration
    return checked


def compile_caption_timing_edit(
    documents: Mapping[str, Any], edits: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    """Rebuild a caption track from canonical words plus operator timing edits.

    No user-provided text is accepted. Every output is reproducible against
    the same canonical source digest and exact timing edit mapping.
    """
    if authorized is not True:
        raise PermissionError("caption timing edit requires operator authorization")
    _lease(expected_source_digest, "caption timing source")
    program = compile_quest_program(documents)
    if program.source_digest != expected_source_digest:
        raise StudioQuestError("stale caption timing source lease")
    original = compile_story_accessibility(documents, authorized=True)
    if (original["source_digest"] != expected_source_digest
            or original["project_id"] != program.project_id):
        raise StudioQuestError("caption accessibility source lease diverged")
    cues = _canonical_cues(original["webvtt"], original["caption_count"])
    timings = _validated_edits(edits, len(cues))
    cursor = 0
    rows: list[dict[str, object]] = []
    blocks = [
        "WEBVTT", "",
        "NOTE Authored sandbox reading estimates only.",
        "NOTE Source digest: " + expected_source_digest,
        "NOTE Canonical text retained; timing estimates operator-edited.", "",
    ]
    changed = 0
    for index, (content, old_duration) in enumerate(cues, 1):
        duration = timings.get(str(index), old_duration)
        start, end = cursor, cursor + duration
        if end > MAX_TIMELINE_MS:
            raise StudioQuestError("caption timing edit exceeds timeline budget")
        was_changed = duration != old_duration
        changed += int(was_changed)
        rows.append({
            "cue_index": index, "start_ms": start, "end_ms": end,
            "duration_ms": duration, "original_duration_ms": old_duration,
            "operator_changed": was_changed, "canonical_text": content,
        })
        blocks.extend([
            str(index), _stamp(start) + " --> " + _stamp(end), content, "",
        ])
        cursor = end
    webvtt = "\n".join(blocks)
    if len(webvtt.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise StudioQuestError("edited caption WebVTT exceeds byte budget")
    payload: dict[str, object] = {
        "schema": SCHEMA, "project_id": program.project_id,
        "source_digest": expected_source_digest,
        "canonical_manifest_digest": original["manifest_digest"],
        "canonical_webvtt_sha256": original["webvtt_sha256"],
        "edits_ms": timings, "operator_changed_count": changed,
        "caption_count": len(cues), "synthetic_duration_ms": cursor,
        "timeline": rows, "webvtt": webvtt,
        "webvtt_sha256": sha256(webvtt.encode("utf-8")).hexdigest(),
        "canonical_words_preserved": True,
        "audio_rendered": False, "audio_sync_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    payload["edit_digest"] = _digest(payload)
    if len(_canonical(payload)) > 256 * 1024:
        raise StudioQuestError("caption timing receipt exceeds budget")
    return payload


def replay_caption_timing_edit(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> dict[str, object]:
    """Never trust a receipt digest without replaying the canonical compiler."""
    if authorized is not True:
        raise PermissionError("caption timing replay requires operator authorization")
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise StudioQuestError("invalid caption timing receipt")
    expected = compile_caption_timing_edit(
        documents, receipt.get("edits_ms"), authorized=True,
        expected_source_digest=expected_source_digest)
    if receipt != expected:
        raise StudioQuestError("caption timing receipt differs from canonical replay")
    return expected


def render_caption_timing_review_html(
    documents: Mapping[str, Any], receipt: object, *, authorized: bool,
    expected_source_digest: str,
) -> bytes:
    """Static CSP-hashed accessible review. No script, network, or file access."""
    verified = replay_caption_timing_edit(
        documents, receipt, authorized=authorized,
        expected_source_digest=expected_source_digest)
    digest = b64encode(sha256(_CSS.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; "
           "style-src 'sha256-" + digest + "'")
    items = []
    for row in verified["timeline"]:
        start, end = _stamp(row["start_ms"]), _stamp(row["end_ms"])
        change = ("Operator-adjusted synthetic timing"
                  if row["operator_changed"] else "Canonical synthetic timing")
        items.append(
            "<li><h2>Cue " + str(row["cue_index"]) + "</h2>"
            "<p><time>" + start + " → " + end + "</time> — "
            "<strong>" + change + "</strong></p><pre>"
            + escape(row["canonical_text"], quote=True) + "</pre></li>")
    markup = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\""
        + escape(csp, quote=True) + "\"><title>Original story caption review</title>"
        "<style>" + _CSS + "</style></head><body><main>"
        "<h1>Source-bound caption timing review</h1><p>Project: "
        + escape(verified["project_id"], quote=True) + "</p>"
        "<p>Canonical text is unchanged. Durations are synthetic estimates, "
        "not rendered audio or verified sync. No release certification.</p>"
        "<p>Source digest: <code>" + verified["source_digest"] + "</code></p>"
        "<ol>" + "".join(items) + "</ol></main></body></html>"
    )
    result = markup.encode("utf-8")
    if len(result) > MAX_OUTPUT_BYTES:
        raise StudioQuestError("caption timing HTML review exceeds byte budget")
    return result
