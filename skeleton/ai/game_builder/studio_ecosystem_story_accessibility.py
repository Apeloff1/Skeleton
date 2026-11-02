"""Deterministic original story accessibility script and WebVTT compiler.

Compiles only source-authored story, stage, scene and ending text. Timings are
synthetic reading estimates, not generated audio or verified media sync.
All outputs are source-bound and have conservative release/evidence flags.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import re
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_story_html import story_source

SCHEMA = "skeleton.game_builder.story_accessibility_script.v1"
MAX_OUTPUT_BYTES = 65536
MAX_CUES = 256
MAX_TEXT = 8192


def _safe(value: object, label: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= MAX_TEXT
            or value.strip() != value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise StudioQuestError("invalid accessibility " + label)
    return value


def _md(value: str) -> str:
    """Escape Markdown syntax as well as raw HTML in authored prose."""
    special = "\\\`*_{}[]()#+-.!|>"
    return "".join("\\" + char if char in special else char
                   for char in escape(value))

def _stamp(milliseconds: int) -> str:
    if type(milliseconds) is not int or not 0 <= milliseconds <= 35999999:
        raise StudioQuestError("accessibility timeline exceeded duration bound")
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{sec:02d}.{ms:03d}"


def _duration(text: str) -> int:
    words = len(re.findall(r"\S+", text))
    return min(20000, max(3000, words * 350))


def compile_story_accessibility(
    documents: Mapping[str, Any], *, authorized: bool,
) -> dict[str, object]:
    """Return replayable authored text and deterministic synthetic caption cues."""
    if authorized is not True:
        raise PermissionError("story accessibility compilation requires operator authorization")
    canon = audit_canon_source(documents, authorized=True)
    if not canon["canon_consistent"]:
        raise StudioQuestError("accessibility compilation refuses contradictory canon")
    program = compile_quest_program(documents)
    story = story_source(documents)
    if (story["project_id"] != program.project_id
            or story["source_digest"] != program.source_digest):
        raise StudioQuestError("accessibility story source lease mismatch")
    premise = _safe(story["premise"], "premise")
    protagonist = _safe(story["protagonist_name"], "protagonist")
    lines = [
        "# Original interactive story — accessible reading edition",
        "",
        "Project: " + _md(program.project_id),
        "Source digest: " + program.source_digest,
        "Authored premise: " + _md(premise),
        "Protagonist: " + _md(protagonist),
        "",
        "This is a sandbox reading edition, not generated audio, native gameplay, "
        "external evidence, rights verification, or release certification.",
        "",
    ]
    captions: list[tuple[str, str]] = [
        ("Story premise", premise + ". Protagonist: " + protagonist),
    ]
    for stage in story["stages"]:
        stage_id = _safe(stage["id"], "stage ID")
        scene_id = _safe(stage["scene_id"], "scene ID")
        goal = _safe(stage["authored_goal"], "authored goal")
        decision = _safe(stage["authored_decision"], "authored decision")
        choices = stage["alternatives"]
        if (type(choices) is not list or not 1 <= len(choices) <= 8
                or any(type(choice) is not str for choice in choices)):
            raise StudioQuestError("invalid accessibility authored alternatives")
        choices = [_safe(choice, "alternative") for choice in choices]
        lines.extend([
            "## " + _md(stage_id) + " — " + _md(scene_id),
            "",
            "Goal: " + _md(goal),
            "Decision: " + _md(decision),
            "Available authored choices:",
        ])
        lines.extend(f"{index}. {_md(choice)}"
                     for index, choice in enumerate(choices, 1))
        lines.extend([
            "Prerequisites: " + (", ".join(_md(_safe(dep, "prerequisite"))
                                          for dep in stage["prerequisites"]) or "none"),
            "Sandbox reward: " + _md(_safe(stage["reward"], "reward")),
            "",
        ])
        captions.append(("Stage " + stage_id, goal))
        captions.append(("Decision " + stage_id,
                         decision + ". Choices: " + "; ".join(choices)))
    lines.extend(["## Authored ending requirements", ""])
    for ending in story["endings"]:
        ident = _safe(ending["id"], "ending ID")
        required = [_safe(value, "ending predicate") for value in ending["requires"]]
        text = ident + ": " + (", ".join(required) or "none")
        lines.append("- " + _md(text))
        captions.append(("Ending " + ident, text))
    if not 1 <= len(captions) <= MAX_CUES:
        raise StudioQuestError("accessibility caption count exceeds budget")
    cursor = 0
    cues = ["WEBVTT", "", "NOTE Authored sandbox reading estimates only.",
            "NOTE Source digest: " + program.source_digest, ""]
    for index, (label, content) in enumerate(captions, 1):
        safe_label = _safe(label, "caption label")
        safe_content = _safe(content, "caption text")
        duration = _duration(safe_content)
        end = cursor + duration
        cues.extend([
            str(index),
            _stamp(cursor) + " --> " + _stamp(end),
            escape(safe_label) + ": " + escape(safe_content),
            "",
        ])
        cursor = end
    markdown = "\n".join(lines).rstrip() + "\n"
    vtt = "\n".join(cues)
    for name, content in (("markdown", markdown), ("vtt", vtt)):
        if not 1 <= len(content.encode("utf-8")) <= MAX_OUTPUT_BYTES:
            raise StudioQuestError("accessibility " + name + " exceeds output byte budget")
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "canon_source_digest": canon["source_digest"],
        "stage_count": len(story["stages"]),
        "caption_count": len(captions),
        "synthetic_duration_ms": cursor,
        "markdown": markdown,
        "webvtt": vtt,
        "markdown_sha256": sha256(markdown.encode("utf-8")).hexdigest(),
        "webvtt_sha256": sha256(vtt.encode("utf-8")).hexdigest(),
        "text_from_authoritative_original_source": True,
        "audio_rendered": False,
        "audio_sync_verified": False,
        "originality_rights_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["manifest_digest"] = sha256(json.dumps(
        {key: value for key, value in payload.items()
         if key not in ("markdown", "webvtt")},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()
    return payload
