from __future__ import annotations
"""
Decade-long 365-day log families linked to calendar/schedule:

- Fisherman's Log  — "catch of the day" (salient keeps)
- Guest Log        — ambient non-user persons
- Building Log     — construction / environment / place changes

Each year has up to 366 day slots; retained across a decade on disk.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import os
import uuid


class DecadeLogKind(str, Enum):
    FISHERMAN = "fisherman"  # catch of the day
    GUEST = "guest"
    BUILDING = "building"


@dataclass
class DecadeDayEntry:
    entry_id: str
    kind: str
    day: str
    title: str
    body: str
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    calendar_ref: Optional[str] = None  # ISO day link
    schedule_item_id: Optional[str] = None
    importance: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DayBucket:
    day: str
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"day": self.day, "entries": self.entries}


class DecadeLogBook:
    """
    One book per kind per user — decade of year files with 365 day buckets.
    """

    def __init__(self, user_id: str, kind: DecadeLogKind):
        self.user_id = user_id
        self.kind = kind
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.root = base / "decade_logs" / user_id / kind.value
        self.root.mkdir(parents=True, exist_ok=True)

    def _year_path(self, year: int) -> Path:
        return self.root / f"{year}.json"

    def _load_year(self, year: int) -> Dict[str, DayBucket]:
        path = self._year_path(year)
        if not path.exists():
            return self._empty_year(year)
        data = json.loads(path.read_text())
        out: Dict[str, DayBucket] = {}
        for k, v in (data.get("days") or {}).items():
            out[k] = DayBucket(day=k, entries=list(v.get("entries") or []))
        return out

    def _empty_year(self, year: int) -> Dict[str, DayBucket]:
        days: Dict[str, DayBucket] = {}
        d = date(year, 1, 1)
        end = date(year, 12, 31)
        while d <= end:
            days[d.isoformat()] = DayBucket(day=d.isoformat())
            d += timedelta(days=1)
        return days

    def _save_year(self, year: int, days: Dict[str, DayBucket]):
        payload = {
            "user_id": self.user_id,
            "kind": self.kind.value,
            "year": year,
            "days": {k: v.to_dict() for k, v in days.items()},
        }
        self._year_path(year).write_text(json.dumps(payload, indent=2))

    def add(
        self,
        d: date,
        title: str,
        body: str,
        *,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        schedule_item_id: Optional[str] = None,
        importance: float = 0.5,
    ) -> DecadeDayEntry:
        days = self._load_year(d.year)
        key = d.isoformat()
        if key not in days:
            days[key] = DayBucket(day=key)
        entry = DecadeDayEntry(
            entry_id=str(uuid.uuid4())[:12],
            kind=self.kind.value,
            day=key,
            title=title,
            body=body,
            tags=tags or [],
            metadata=metadata or {},
            calendar_ref=key,
            schedule_item_id=schedule_item_id,
            importance=max(0.0, min(1.0, importance)),
        )
        days[key].entries.append(entry.to_dict())
        self._save_year(d.year, days)
        return entry

    def get_day(self, d: date) -> DayBucket:
        days = self._load_year(d.year)
        return days.get(d.isoformat()) or DayBucket(day=d.isoformat())

    def range_entries(self, start: date, end: date) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        d = start
        while d <= end:
            bucket = self.get_day(d)
            out.extend(bucket.entries)
            d += timedelta(days=1)
        return out

    def decade_summary(self, end_year: Optional[int] = None) -> Dict[str, Any]:
        end_year = end_year or date.today().year
        years = list(range(end_year - 9, end_year + 1))
        counts = {}
        total = 0
        for y in years:
            days = self._load_year(y)
            n = sum(len(b.entries) for b in days.values())
            counts[str(y)] = n
            total += n
        return {"kind": self.kind.value, "years": counts, "total_entries": total}


class FishermanLog(DecadeLogBook):
    """Catch of the day — important information worth keeping."""

    def __init__(self, user_id: str):
        super().__init__(user_id, DecadeLogKind.FISHERMAN)

    def catch(
        self,
        d: date,
        body: str,
        *,
        title: str = "Catch of the day",
        importance: float = 0.8,
        **kw,
    ) -> DecadeDayEntry:
        tags = list(kw.pop("tags", None) or [])
        if "catch" not in tags:
            tags.append("catch")
        return self.add(d, title, body, tags=tags, importance=importance, **kw)


class GuestLog(DecadeLogBook):
    """Information gleaned on non-user ambient persons."""

    def __init__(self, user_id: str):
        super().__init__(user_id, DecadeLogKind.GUEST)

    def note_guest(
        self,
        d: date,
        person_label: str,
        body: str,
        *,
        relationship: Optional[str] = None,
        **kw,
    ) -> DecadeDayEntry:
        meta = dict(kw.pop("metadata", None) or {})
        meta["person_label"] = person_label
        if relationship:
            meta["relationship"] = relationship
        tags = list(kw.pop("tags", None) or [])
        tags.extend(["guest", person_label.lower().replace(" ", "_")[:32]])
        return self.add(
            d,
            title=f"Guest: {person_label}",
            body=body,
            tags=tags,
            metadata=meta,
            importance=kw.pop("importance", 0.55),
            **kw,
        )


class BuildingLog(DecadeLogBook):
    """Place / building / environment changes over years."""

    def __init__(self, user_id: str):
        super().__init__(user_id, DecadeLogKind.BUILDING)

    def note_building(
        self,
        d: date,
        place: str,
        body: str,
        *,
        change_type: str = "observe",  # observe | repair | move | build
        **kw,
    ) -> DecadeDayEntry:
        meta = dict(kw.pop("metadata", None) or {})
        meta["place"] = place
        meta["change_type"] = change_type
        tags = list(kw.pop("tags", None) or [])
        tags.extend(["building", change_type])
        return self.add(
            d,
            title=f"Building: {place}",
            body=body,
            tags=tags,
            metadata=meta,
            importance=kw.pop("importance", 0.5),
            **kw,
        )


class DecadeLogHub:
    """Facade over fisherman / guest / building books."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.fisherman = FishermanLog(user_id)
        self.guest = GuestLog(user_id)
        self.building = BuildingLog(user_id)

    def linked_day(self, d: date) -> Dict[str, Any]:
        return {
            "day": d.isoformat(),
            "fisherman": self.fisherman.get_day(d).to_dict(),
            "guest": self.guest.get_day(d).to_dict(),
            "building": self.building.get_day(d).to_dict(),
        }

    def decade_overview(self) -> Dict[str, Any]:
        return {
            "fisherman": self.fisherman.decade_summary(),
            "guest": self.guest.decade_summary(),
            "building": self.building.decade_summary(),
        }
