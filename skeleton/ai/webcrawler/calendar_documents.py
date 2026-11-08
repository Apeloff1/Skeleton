"""Inert iCalendar VEVENT projection without recurrence expansion or network IO.

Invitees, organizer identities, attachments, alarms, remote time zones and
calendar methods are never exported as evidence or interpreted as commands.
The actual source remains unreviewed and must pass canonical capture policy.
"""
from __future__ import annotations

import re

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

CALENDAR_MEDIA_TYPES = frozenset({"text/calendar", "application/ics"})
_PROPERTY = re.compile(r"^([A-Z][A-Z0-9-]{0,63})(?:;[^:]*)?:(.*)$")
_DATE = re.compile(r"^\d{8}(?:T\d{6}Z?)?$")
_ALLOWED = frozenset({
    "SUMMARY", "DESCRIPTION", "DTSTART", "DTEND", "LOCATION",
    "STATUS", "CATEGORIES", "RRULE",
})


def _unescape(value: str) -> str:
    result = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            token = value[i + 1]
            result.append({"n": "\n", "N": "\n", ",": ",",
                           ";": ";", "\\": "\\"}.get(token, "\\" + token))
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result).strip()


def _lines(raw: str) -> list[str]:
    rows = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(rows) > 8192:
        raise ResearchFormatError("unbounded calendar lines")
    unfolded = []
    for line in rows:
        if len(line) > 16384:
            raise ResearchFormatError("calendar line length exceeded")
        if line.startswith((" ", "\t")):
            if not unfolded:
                raise ResearchFormatError("orphaned calendar continuation")
            unfolded[-1] += line[1:]
            if len(unfolded[-1]) > 16384:
                raise ResearchFormatError("unbounded folded calendar property")
        elif line:
            unfolded.append(line)
    return unfolded


def extract_calendar(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    rows = _lines(raw)
    if not rows or rows[0] != "BEGIN:VCALENDAR" or rows[-1] != "END:VCALENDAR":
        raise ResearchFormatError("iCalendar envelope missing")
    stack = []
    events: list[dict[str, str]] = []
    event: dict[str, str] | None = None
    fields = 0
    for line in rows:
        if line.startswith("BEGIN:"):
            name = line[6:]
            if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,63}", name):
                raise ResearchFormatError("unrecognized calendar section")
            stack.append(name)
            if len(stack) > 8:
                raise ResearchFormatError("calendar nesting too deep")
            if name == "VEVENT":
                if event is not None or len(events) >= 256 or stack[-2:] != ["VCALENDAR", "VEVENT"]:
                    raise ResearchFormatError("invalid or excessive calendar events")
                event = {}
            continue
        if line.startswith("END:"):
            if not stack or stack[-1] != line[4:]:
                raise ResearchFormatError("unbalanced calendar sections")
            if stack[-1] == "VEVENT":
                if event is None:
                    raise ResearchFormatError("missing calendar event")
                if event.get("SUMMARY") or event.get("DESCRIPTION"):
                    events.append(event)
                event = None
            stack.pop()
            continue
        if not stack:
            raise ResearchFormatError("calendar property outside an envelope")
        fields += 1
        if fields > 4096:
            raise ResearchFormatError("calendar property count exceeded")
        if event is None or stack != ["VCALENDAR", "VEVENT"]:
            continue
        match = _PROPERTY.fullmatch(line)
        if match is None:
            raise ResearchFormatError("invalid VEVENT property syntax")
        key, value = match.groups()
        if key not in _ALLOWED:
            continue  # ATTENDEE, ORGANIZER, URL, ATTACH, UID, X-* are not retained.
        value = _unescape(value)
        if len(value) > 8192:
            raise ResearchFormatError("event property length exceeded")
        if key in ("DTSTART", "DTEND") and not _DATE.fullmatch(value):
            raise ResearchFormatError("unsupported calendar date representation")
        if key not in event:
            event[key] = value
    if stack or not events:
        raise ResearchFormatError("no complete calendar event evidence")
    lines: list[str] = []
    for ordinal, row in enumerate(events, 1):
        parts = [
            f"{label}: {row[key]}"
            for key, label in (
                ("SUMMARY", "title"), ("DTSTART", "starts"),
                ("DTEND", "ends"), ("LOCATION", "location"),
                ("STATUS", "status"), ("CATEGORIES", "categories"),
                ("DESCRIPTION", "description"),
            ) if row.get(key)
        ]
        if row.get("RRULE"):
            # Never project a guessed occurrence list from recurrence rules.
            parts.append("recurrence: declared (not expanded)")
        lines.append(f"Event {ordinal}: " + "; ".join(parts))
    title = next((row["SUMMARY"] for row in events if row.get("SUMMARY")), "Calendar events")
    return project_lines(lines, title=title, max_chars=max_chars)
