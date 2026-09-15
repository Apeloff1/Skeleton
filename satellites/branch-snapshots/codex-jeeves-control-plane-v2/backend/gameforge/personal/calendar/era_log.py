from __future__ import annotations
"""
Era Log — distills a filled schedule/calendar span into multi-decade memory.

When a year (or defined era window) is sufficiently filled, compress into an
Era record that chains across decades.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import os
import uuid


@dataclass
class EraRecord:
    era_id: str
    user_id: str
    label: str
    start: str
    end: str
    year: int
    country: str
    city: str
    summary: str
    highlights: List[str] = field(default_factory=list)
    project_milestones: List[str] = field(default_factory=list)
    catch_count: int = 0
    guest_count: int = 0
    building_count: int = 0
    schedule_items: int = 0
    avg_progress: Optional[float] = None
    weather_motif: Optional[str] = None
    distilled_from_days: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class EraLog:
    """
    Multi-decade era chain. One JSONL per decade bucket (e.g. 2020s).
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.root = base / "era_log" / user_id
        self.root.mkdir(parents=True, exist_ok=True)

    def _decade_path(self, year: int) -> Path:
        decade = (year // 10) * 10
        return self.root / f"{decade}s.jsonl"

    def distill_year(
        self,
        year_calendar,
        decade_hub,
        *,
        year: Optional[int] = None,
        min_filled_ratio: float = 0.15,
        label: Optional[str] = None,
    ) -> Optional[EraRecord]:
        """
        Distill a YearCalendar + decade logs into one EraRecord if enough signal.
        """
        year = year or year_calendar.year
        # ensure days loaded
        filled = 0
        schedule_items = 0
        progress_vals: List[float] = []
        highlights: List[str] = []
        milestones: List[str] = []
        wx_counts: Dict[str, int] = {}

        start = date(year, 1, 1)
        end = date(year, 12, 31)
        d = start
        day_count = 0
        while d <= end:
            day_count += 1
            key = d.isoformat()
            daylog = year_calendar.days.get(key)
            if daylog:
                has = bool(daylog.schedule or daylog.project_progress or daylog.personal_notes)
                if has:
                    filled += 1
                schedule_items += len(daylog.schedule or [])
                for p in daylog.project_progress or []:
                    try:
                        progress_vals.append(float(p.get("percent") or 0))
                    except Exception:
                        pass
                    if (p.get("percent") or 0) >= 100:
                        milestones.append(f"{p.get('name')}: complete")
                    elif (p.get("percent") or 0) >= 50:
                        milestones.append(f"{p.get('name')}: {p.get('percent')}%")
                for n in (daylog.personal_notes or [])[:2]:
                    highlights.append(n[:160])
                for s in (daylog.schedule or [])[:1]:
                    if s.get("kind") == "project_milestone":
                        milestones.append(s.get("title") or "milestone")
            # weather motif sample
            try:
                w = year_calendar.weather_log.get_or_simulate(
                    d,
                    country=year_calendar.country,
                    city=year_calendar.city,
                    latitude=year_calendar.latitude,
                )
                wx_counts[w.condition] = wx_counts.get(w.condition, 0) + 1
            except Exception:
                pass
            d = d.fromordinal(d.toordinal() + 1)

        ratio = filled / max(1, day_count)
        if ratio < min_filled_ratio and schedule_items < 20:
            return None  # not enough to seal era yet

        # decade hub counts for year
        catch_count = len(decade_hub.fisherman.range_entries(start, end))
        guest_count = len(decade_hub.guest.range_entries(start, end))
        building_count = len(decade_hub.building.range_entries(start, end))

        # top catches as highlights
        for e in decade_hub.fisherman.range_entries(start, end)[:5]:
            highlights.append(f"Catch: {e.get('title')}: {(e.get('body') or '')[:120]}")

        weather_motif = None
        if wx_counts:
            weather_motif = max(wx_counts.items(), key=lambda kv: kv[1])[0]

        avg_progress = sum(progress_vals) / len(progress_vals) if progress_vals else None
        summary = (
            f"Era {year} in {year_calendar.city}, {year_calendar.country}: "
            f"{filled} active days, {schedule_items} schedule items, "
            f"{catch_count} catches, {guest_count} guest notes, {building_count} building notes."
        )
        if weather_motif:
            summary += f" Dominant weather motif: {weather_motif}."

        record = EraRecord(
            era_id=str(uuid.uuid4())[:12],
            user_id=year_calendar.user_id,
            label=label or f"Year {year}",
            start=start.isoformat(),
            end=end.isoformat(),
            year=year,
            country=year_calendar.country,
            city=year_calendar.city,
            summary=summary,
            highlights=highlights[:20],
            project_milestones=list(dict.fromkeys(milestones))[:20],
            catch_count=catch_count,
            guest_count=guest_count,
            building_count=building_count,
            schedule_items=schedule_items,
            avg_progress=round(avg_progress, 1) if avg_progress is not None else None,
            weather_motif=weather_motif,
            distilled_from_days=filled,
        )
        path = self._decade_path(year)
        with path.open("a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
        return record

    def list_eras(self, decade: Optional[int] = None) -> List[Dict[str, Any]]:
        if decade is not None:
            paths = [self._decade_path(decade)]
        else:
            paths = sorted(self.root.glob("*s.jsonl"))
        rows: List[Dict[str, Any]] = []
        for path in paths:
            if not path.exists():
                continue
            with path.open() as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
        return rows

    def chain_summary(self) -> str:
        eras = self.list_eras()
        if not eras:
            return "[ERA LOG] No eras distilled yet."
        lines = ["[ERA LOG — multi-decade chain]"]
        for e in eras[-8:]:
            lines.append(
                f"- {e.get('label')} ({e.get('start')} → {e.get('end')}): {e.get('summary', '')[:160]}"
            )
        return "\n".join(lines)
