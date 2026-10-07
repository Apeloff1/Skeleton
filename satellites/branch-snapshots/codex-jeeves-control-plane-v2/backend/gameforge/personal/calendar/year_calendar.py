from __future__ import annotations
"""
Full-year calendar with per-day logs, scheduling, project progress,
geo holidays, weather, and daily affect — 365 day slots.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import os
from pathlib import Path

from gameforge.personal.calendar.holidays import occasions_on, holidays_for
from gameforge.personal.calendar.weather_decade import DecadeWeatherLog, WeatherDay
from gameforge.personal.calendar.affect import simulate_daily_affect, DailyAffect


def _safe_segment(value: str, *, what: str = "path") -> str:
    """Reject path traversal / absolute segments in user-supplied ids."""
    s = str(value or "").strip()
    if (
        not s
        or s in {".", ".."}
        or ".." in s
        or "/" in s
        or "\\" in s
        or s.startswith(("~", "/", "\\"))
    ):
        raise ValueError(f"invalid {what}: {value!r}")
    return s


def _resolve_under(root: Path, *parts: str) -> Path:
    """Join parts under root; raise if the result escapes root."""
    root_r = root.resolve()
    candidate = root_r.joinpath(*parts).resolve()
    if candidate != root_r and root_r not in candidate.parents:
        raise ValueError(f"path escapes sandbox: {parts!r}")
    return candidate


@dataclass
class ScheduleItem:
    item_id: str
    title: str
    when: str  # ISO datetime or date
    kind: str = "task"  # task | reminder | event | project_milestone
    done: bool = False
    notes: str = ""
    project_id: Optional[str] = None


@dataclass
class ProjectProgress:
    project_id: str
    name: str
    percent: float = 0.0
    note: str = ""


@dataclass
class DayLog:
    day: str  # ISO date
    country: str
    city: str
    occasions: List[str] = field(default_factory=list)
    schedule: List[Dict[str, Any]] = field(default_factory=list)
    project_progress: List[Dict[str, Any]] = field(default_factory=list)
    personal_notes: List[str] = field(default_factory=list)
    weather: Optional[Dict[str, Any]] = None
    affect: Optional[Dict[str, Any]] = None
    yesteryear: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class YearCalendar:
    """
    Holds 365/366 day logs for a year; persists JSONL per year.
    """

    def __init__(
        self,
        user_id: str,
        year: Optional[int] = None,
        country: str = "NO",
        city: str = "Lillestrøm",
        latitude: float = 59.95,
    ):
        self.user_id = _safe_segment(user_id, what="user_id")
        self.year = year or date.today().year
        self.country = country
        self.city = city
        self.latitude = latitude
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.root = _resolve_under(base / "year_calendar", self.user_id)
        self.root.mkdir(parents=True, exist_ok=True)
        self.weather_log = DecadeWeatherLog(user_id)
        self.days: Dict[str, DayLog] = {}
        self._load()

    def _path(self) -> Path:
        return _resolve_under(self.root, f"{int(self.year)}.json")

    def _load(self):
        path = self._path()
        if not path.exists():
            self._ensure_year()
            self._save()
            return
        data = json.loads(path.read_text())
        self.country = data.get("country", self.country)
        self.city = data.get("city", self.city)
        for k, v in (data.get("days") or {}).items():
            self.days[k] = DayLog(**v)

    def _save(self):
        payload = {
            "user_id": self.user_id,
            "year": self.year,
            "country": self.country,
            "city": self.city,
            "days": {k: v.to_dict() for k, v in self.days.items()},
        }
        self._path().write_text(json.dumps(payload, indent=2, default=str))

    def set_location(self, country: str, city: str, latitude: float = 59.95):
        self.country = country.upper()
        self.city = city
        self.latitude = latitude
        # refresh occasions for remaining year
        for key, daylog in self.days.items():
            d = date.fromisoformat(key)
            daylog.country = self.country
            daylog.city = self.city
            daylog.occasions = occasions_on(self.country, d)
        self._save()

    def _ensure_year(self):
        d = date(self.year, 1, 1)
        end = date(self.year, 12, 31)
        while d <= end:
            key = d.isoformat()
            if key not in self.days:
                self.days[key] = DayLog(
                    day=key,
                    country=self.country,
                    city=self.city,
                    occasions=occasions_on(self.country, d),
                )
            d += timedelta(days=1)

    def get_day(self, d: Optional[date] = None, *, enrich: bool = True) -> DayLog:
        d = d or date.today()
        if d.year != self.year:
            # lightweight cross-year: open that year calendar would be caller's job
            cal = YearCalendar(
                self.user_id, year=d.year, country=self.country, city=self.city, latitude=self.latitude
            )
            return cal.get_day(d, enrich=enrich)
        key = d.isoformat()
        if key not in self.days:
            self._ensure_year()
        daylog = self.days[key]
        if enrich:
            w = self.weather_log.get_or_simulate(
                d, country=self.country, city=self.city, latitude=self.latitude
            )
            daylog.weather = w.to_dict()
            affect = simulate_daily_affect(w)
            daylog.affect = affect.to_dict()
            daylog.yesteryear = self.weather_log.memories_of_yesteryear(
                d, years_back=10, country=self.country, city=self.city, latitude=self.latitude
            )
            daylog.occasions = occasions_on(self.country, d)
            self._save()
        return daylog

    def add_schedule(
        self,
        d: date,
        title: str,
        *,
        when: Optional[str] = None,
        kind: str = "task",
        project_id: Optional[str] = None,
        notes: str = "",
    ) -> DayLog:
        import uuid

        daylog = self.get_day(d, enrich=False)
        item = ScheduleItem(
            item_id=str(uuid.uuid4())[:10],
            title=title,
            when=when or d.isoformat(),
            kind=kind,
            project_id=project_id,
            notes=notes,
        )
        daylog.schedule.append(asdict(item))
        self._save()
        return daylog

    def set_project_progress(
        self, d: date, project_id: str, name: str, percent: float, note: str = ""
    ) -> DayLog:
        daylog = self.get_day(d, enrich=False)
        # replace same project_id for the day
        daylog.project_progress = [
            p for p in daylog.project_progress if p.get("project_id") != project_id
        ]
        daylog.project_progress.append(
            asdict(ProjectProgress(project_id, name, max(0.0, min(100.0, percent)), note))
        )
        self._save()
        return daylog

    def add_day_note(self, d: date, note: str) -> DayLog:
        daylog = self.get_day(d, enrich=False)
        daylog.personal_notes.append(note)
        self._save()
        return daylog

    def today_briefing(self) -> Dict[str, Any]:
        d = date.today()
        daylog = self.get_day(d, enrich=True)
        return {
            "date": d.isoformat(),
            "country": self.country,
            "city": self.city,
            "occasions": daylog.occasions,
            "schedule": daylog.schedule,
            "project_progress": daylog.project_progress,
            "weather": daylog.weather,
            "affect": daylog.affect,
            "yesteryear": daylog.yesteryear[:3],
            "reminders": self._reminder_lines(daylog),
        }

    def _reminder_lines(self, daylog: DayLog) -> List[str]:
        lines = []
        for o in daylog.occasions:
            lines.append(f"Today is {o}.")
        for s in daylog.schedule:
            if not s.get("done"):
                lines.append(f"Scheduled: {s.get('title')} ({s.get('kind')})")
        for p in daylog.project_progress:
            lines.append(f"Project {p.get('name')}: {p.get('percent'):.0f}%")
        return lines

    def jeeves_context_block(self) -> str:
        b = self.today_briefing()
        lines = [f"[CALENDAR — {b['date']} · {b['city']}, {b['country']}]"]
        if b["occasions"]:
            lines.append("Occasions: " + ", ".join(b["occasions"]))
        if b["reminders"]:
            lines.append("Reminders:")
            for r in b["reminders"][:8]:
                lines.append(f"- {r}")
        aff = b.get("affect") or {}
        if aff:
            lines.append(
                f"Daily affect: energy={aff.get('energy')} calm={aff.get('calm')} "
                f"focus={aff.get('focus')} valence={aff.get('valence')}"
            )
            lines.append(f"Jeeves guidance: {aff.get('jeeves_guidance')}")
        w = b.get("weather") or {}
        if w:
            lines.append(
                f"Weather: {w.get('condition')} {w.get('temp_c')}°C, "
                f"noise~{w.get('noise_db')}dB, precip {w.get('precip_mm')}mm"
            )
        yy = b.get("yesteryear") or []
        if yy:
            lines.append("Memories of yesteryear:")
            for m in yy[:3]:
                lines.append(f"- {m.get('blurb')}")
        lines.append("Tone: always empathetic and positively reinforcing.")
        return "\n".join(lines)
