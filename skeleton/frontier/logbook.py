"""Captain's Log policy adapted onto canonical frontier memory and events.

Lorebuffa and Openworld share ``backend/captains_log.py`` blob
``5ed7efd452e7f2bb4ef7024185d66d65f1bd89d8``. This module deliberately does
not create another persistence subsystem. It normalizes and renders log entries,
projects them for UI/query use, and adapts entries to ``MemoryContract`` items
and ``DomainEvent`` payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from string import Formatter
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from skeleton.frontier.events import DomainEvent


MILESTONE_IMPORTANCE = frozenset({"milestone", "legendary", "achievement"})


@dataclass(frozen=True, slots=True)
class CaptainLogEntry:
    entry_id: str
    user_id: str
    title: str
    content: str
    log_type: str
    importance: str = "normal"
    location: str | None = None
    related_entities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    in_game_date: str | None = None
    is_auto_generated: bool = False
    is_pinned: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "user_id": self.user_id,
            "title": self.title,
            "content": self.content,
            "log_type": self.log_type,
            "importance": self.importance,
            "location": self.location,
            "related_entities": list(self.related_entities),
            "tags": list(self.tags),
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "in_game_date": self.in_game_date,
            "is_auto_generated": self.is_auto_generated,
            "is_pinned": self.is_pinned,
        }


def _strings(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(text for item in value if (text := str(item).strip()))


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("log entry created_at must not be empty")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("log entry created_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("log entry created_at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def log_entry_from_record(record: Mapping[str, Any]) -> CaptainLogEntry:
    required = {
        key: str(record.get(key) or "").strip()
        for key in ("entry_id", "user_id", "title", "content", "log_type")
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"log entry requires non-empty fields: {', '.join(missing)}")

    importance = str(record.get("importance") or "normal").strip().lower()
    location = str(record.get("location") or "").strip() or None
    in_game_date = str(record.get("in_game_date") or "").strip() or None
    return CaptainLogEntry(
        entry_id=required["entry_id"],
        user_id=required["user_id"],
        title=required["title"],
        content=required["content"],
        log_type=required["log_type"].lower(),
        importance=importance,
        location=location,
        related_entities=_strings(
            record.get("related_entities"),
            field_name="related_entities",
        ),
        tags=_strings(record.get("tags"), field_name="tags"),
        created_at=_parse_datetime(record.get("created_at")),
        in_game_date=in_game_date,
        is_auto_generated=bool(record.get("is_auto_generated", False)),
        is_pinned=bool(record.get("is_pinned", False)),
    )


def _format_fields(template: str) -> frozenset[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name is None:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        if root:
            fields.add(root)
    return frozenset(fields)


def render_log_template(
    template: Mapping[str, Any],
    *,
    user_id: str,
    variables: Mapping[str, Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> CaptainLogEntry:
    """Render a source-shaped auto-log template with explicit dependencies."""

    user_id = user_id.strip()
    if not user_id:
        raise ValueError("user_id must not be empty")
    title_template = str(template.get("title") or "").strip()
    content_template = str(template.get("template") or "").strip()
    log_type = str(template.get("type") or "").strip().lower()
    if not title_template or not content_template or not log_type:
        raise ValueError("log template requires title, template and type")

    needed = _format_fields(title_template) | _format_fields(content_template)
    missing = sorted(needed.difference(variables))
    if missing:
        raise KeyError(f"missing log template variables: {', '.join(missing)}")

    entry_id = str(id_factory()).strip()
    if not entry_id:
        raise ValueError("id_factory must return a non-empty identifier")
    created_at = now()
    if created_at.tzinfo is None:
        raise ValueError("now must return a timezone-aware datetime")

    try:
        title = title_template.format(**variables)
        content = content_template.format(**variables)
    except (KeyError, IndexError, AttributeError, ValueError) as exc:
        raise ValueError("invalid log template formatting") from exc

    importance = str(template.get("importance") or "normal").strip().lower()
    return CaptainLogEntry(
        entry_id=entry_id,
        user_id=user_id,
        title=title,
        content=content,
        log_type=log_type,
        importance=importance,
        related_entities=tuple(str(key) for key in variables),
        created_at=created_at.astimezone(timezone.utc),
        is_auto_generated=True,
    )


def toggle_pin(entry: CaptainLogEntry) -> CaptainLogEntry:
    return replace(entry, is_pinned=not entry.is_pinned)


def can_delete(entry: CaptainLogEntry) -> bool:
    """Preserve the source rule that automatic entries cannot be deleted."""

    return not entry.is_auto_generated


def search_entries(
    entries: Sequence[CaptainLogEntry],
    query: str,
    *,
    limit: int = 20,
) -> tuple[CaptainLogEntry, ...]:
    if limit < 1:
        return ()
    needle = query.casefold().strip()
    if not needle:
        return tuple(entries[:limit])
    matches: list[CaptainLogEntry] = []
    for entry in entries:
        haystacks = (entry.title, entry.content, *entry.tags)
        if any(needle in value.casefold() for value in haystacks):
            matches.append(entry)
            if len(matches) >= limit:
                break
    return tuple(matches)


def milestone_entries(entries: Sequence[CaptainLogEntry]) -> tuple[CaptainLogEntry, ...]:
    return tuple(entry for entry in entries if entry.importance in MILESTONE_IMPORTANCE)


def log_statistics(
    entries: Sequence[CaptainLogEntry],
    *,
    known_types: Sequence[str] = (),
) -> dict[str, Any]:
    by_type = {str(log_type).strip().lower(): 0 for log_type in known_types if str(log_type).strip()}
    milestones = 0
    legendary = 0
    for entry in entries:
        by_type[entry.log_type] = by_type.get(entry.log_type, 0) + 1
        if entry.importance == "milestone":
            milestones += 1
        if entry.importance == "legendary":
            legendary += 1
    return {
        "total_entries": len(entries),
        "by_type": by_type,
        "milestones": milestones,
        "legendary_moments": legendary,
    }


def timeline(
    entries: Sequence[CaptainLogEntry],
    *,
    year: int | None = None,
    month: int | None = None,
) -> Mapping[str, tuple[CaptainLogEntry, ...]]:
    if month is not None and year is None:
        raise ValueError("timeline month requires year")
    if month is not None and not 1 <= month <= 12:
        raise ValueError("timeline month must be between 1 and 12")

    grouped: dict[str, list[CaptainLogEntry]] = {}
    for entry in sorted(entries, key=lambda item: item.created_at):
        if year is not None and entry.created_at.year != year:
            continue
        if month is not None and entry.created_at.month != month:
            continue
        key = entry.created_at.date().isoformat()
        grouped.setdefault(key, []).append(entry)
    return {key: tuple(values) for key, values in grouped.items()}


def log_entry_to_memory_item(entry: CaptainLogEntry) -> dict[str, Any]:
    """Adapt a log entry to the existing ``MemoryContract`` portable shape."""

    return {
        "id": entry.entry_id,
        "content": f"{entry.title}\n{entry.content}",
        "user_id": entry.user_id,
        "domain": "captains_log",
        "log_type": entry.log_type,
        "importance": entry.importance,
        "metadata": {
            "location": entry.location,
            "related_entities": list(entry.related_entities),
            "tags": list(entry.tags),
            "created_at": entry.created_at.astimezone(timezone.utc).isoformat(),
            "in_game_date": entry.in_game_date,
            "is_auto_generated": entry.is_auto_generated,
            "is_pinned": entry.is_pinned,
        },
    }


def log_entry_event(entry: CaptainLogEntry, *, action: str = "created") -> DomainEvent:
    """Adapt a log entry to the canonical frontier event bus."""

    normalized_action = action.strip().lower()
    if not normalized_action:
        raise ValueError("log action must not be empty")
    return DomainEvent(
        topic=f"captains_log.{normalized_action}",
        payload={
            "entry_id": entry.entry_id,
            "user_id": entry.user_id,
            "log_type": entry.log_type,
            "importance": entry.importance,
            "is_auto_generated": entry.is_auto_generated,
        },
        occurred_at=entry.created_at,
    )
