"""Bounded WebVTT and SubRip transcript extraction for the canonical crawler.

Timed captions are inert external source evidence. Cue styling, notes, voice
tags, links, chapters, JavaScript and remote resources have no execution or
discovery authority. Timing is checked, not treated as a synchronized clock.
"""
from __future__ import annotations

import html
import re

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

TIMED_MEDIA_TYPES = frozenset({
    "text/vtt", "application/x-subrip", "text/srt",
})
_TIME = re.compile(r"^(?:(\d{1,3}):)?(\d{2}):(\d{2})[.,](\d{3})$")
_TAG = re.compile(r"<[^<>]{1,256}>")
_MAX_CUES = 1024


def _timestamp(raw: str) -> tuple[int, str]:
    match = _TIME.fullmatch(raw.strip())
    if match is None:
        raise ResearchFormatError("invalid subtitle timestamp")
    hours, minutes, seconds, milli = match.groups()
    if int(minutes) > 59 or int(seconds) > 59:
        raise ResearchFormatError("invalid subtitle clock component")
    h = int(hours or 0)
    ms = ((h * 3600 + int(minutes) * 60 + int(seconds)) * 1000
          + int(milli))
    return ms, f"{h:02d}:{minutes}:{seconds}.{milli}"


def _cue_contents(lines: list[str]) -> str:
    parts = []
    for line in lines:
        if len(line) > 8192:
            raise ResearchFormatError("oversized timed media cue")
        # Content is retained as inert text, not a browser media element.
        parts.append(html.unescape(_TAG.sub("", line)).strip())
    text = " ".join(piece for piece in parts if piece)
    if len(text) > 8192:
        raise ResearchFormatError("excessive timed media cue text")
    return text


def extract_timed_media(
    raw: str, media_type: str, *, max_chars: int = 524288,
    max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    if media_type not in TIMED_MEDIA_TYPES:
        raise ResearchFormatError("unsupported timed media encoding")
    normalized = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    rows = normalized.split("\n")
    if media_type == "text/vtt":
        if not rows or not (rows[0] == "WEBVTT" or rows[0].startswith("WEBVTT ")):
            raise ResearchFormatError("WebVTT signature missing")
        try:
            start = rows.index("", 1) + 1
        except ValueError as exc:
            raise ResearchFormatError("WebVTT header not terminated") from exc
        rows = rows[start:]
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in rows:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
            if len(current) > 32:
                raise ResearchFormatError("subtitle cue has excessive rows")
    if current:
        blocks.append(current)
    if len(blocks) > _MAX_CUES * 2:
        raise ResearchFormatError("subtitle cue capacity exceeded")
    lines: list[str] = []
    last_start = -1
    for block in blocks:
        label = block[0].lstrip()
        if media_type == "text/vtt" and (
            label == "NOTE" or label.startswith("NOTE ")
            or label == "STYLE" or label == "REGION"
        ):
            continue
        idx = 0
        if "-->" not in block[0]:
            idx = 1
            if media_type != "text/vtt" and not block[0].isdigit():
                raise ResearchFormatError("SubRip cue number missing")
        if idx >= len(block) or "-->" not in block[idx]:
            raise ResearchFormatError("subtitle cue has no timeline")
        a, b = block[idx].split("-->", 1)
        end_token = b.strip().split(maxsplit=1)[0] if b.strip() else ""
        begin_ms, begin_label = _timestamp(a)
        end_ms, end_label = _timestamp(end_token)
        if end_ms <= begin_ms or begin_ms < last_start:
            raise ResearchFormatError("non-monotone or negative subtitle interval")
        last_start = begin_ms
        content = _cue_contents(block[idx + 1:])
        if content:
            lines.append(f"[{begin_label} - {end_label}] {content}")
        if len(lines) > _MAX_CUES:
            raise ResearchFormatError("too many retained subtitle cues")
    return project_lines(lines, title="Timed media transcript", max_chars=max_chars)
