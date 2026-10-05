from __future__ import annotations
"""
Decade-spanning weather logbook (farm-log style).
Parsed as 'memories of yesteryear' for humanizing Jeeves over time.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import hashlib
import math
import json
from pathlib import Path
import os


@dataclass
class WeatherDay:
    day: str  # ISO date
    country: str
    city: str
    temp_c: float
    feels_like_c: float
    humidity: float
    wind_ms: float
    precip_mm: float
    noise_db: float  # ambient / city noise proxy
    condition: str  # clear, clouds, rain, snow, storm, fog
    notes: str = ""
    source: str = "simulated"  # simulated | sensor | api

    def to_dict(self) -> dict:
        return asdict(self)


def _seed_float(key: str, lo: float, hi: float) -> float:
    h = hashlib.sha256(key.encode()).digest()
    x = int.from_bytes(h[:4], "big") / 2**32
    return lo + (hi - lo) * x


def simulate_weather_day(
    d: date,
    *,
    country: str = "NO",
    city: str = "Lillestrøm",
    latitude: float = 59.95,
) -> WeatherDay:
    """
    Deterministic climate-ish simulation from date + location seed.
    Not a forecast product — stable synthetic history for memory.
    """
    doy = d.timetuple().tm_yday
    # seasonal baseline by latitude (simple sinusoid)
    seasonal = 10.0 - abs(latitude) / 9.0 + 12.0 * math.sin(2 * math.pi * (doy - 80) / 365.0)
    key = f"{country}:{city}:{d.isoformat()}"
    temp = seasonal + _seed_float(key + ":t", -6, 6)
    humid = _seed_float(key + ":h", 0.35, 0.9)
    wind = _seed_float(key + ":w", 0.5, 12.0)
    precip = max(0.0, _seed_float(key + ":p", -2, 18))
    noise = _seed_float(key + ":n", 35, 78)  # dB proxy
    # condition buckets
    r = _seed_float(key + ":c", 0, 1)
    if precip > 10 and temp < 0:
        cond = "snow"
    elif precip > 12:
        cond = "storm"
    elif precip > 3:
        cond = "rain"
    elif r > 0.75:
        cond = "clouds"
    elif humid > 0.85 and wind < 2:
        cond = "fog"
    else:
        cond = "clear"
    feels = temp - 0.2 * wind + (0.5 if humid > 0.7 else 0)
    return WeatherDay(
        day=d.isoformat(),
        country=country,
        city=city,
        temp_c=round(temp, 1),
        feels_like_c=round(feels, 1),
        humidity=round(humid, 2),
        wind_ms=round(wind, 1),
        precip_mm=round(precip, 1),
        noise_db=round(noise, 1),
        condition=cond,
        notes="",
        source="simulated",
    )


class DecadeWeatherLog:
    """
    Farm-style weather log spanning up to 10 years.
    """

    def __init__(self, user_id: str, root: Optional[Path] = None):
        self.user_id = user_id
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.root = root or (base / "weather_decade" / user_id)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, WeatherDay] = {}

    def _path(self, year: int) -> Path:
        return self.root / f"{year}.jsonl"

    def get_or_simulate(
        self,
        d: date,
        *,
        country: str = "NO",
        city: str = "Lillestrøm",
        latitude: float = 59.95,
    ) -> WeatherDay:
        key = d.isoformat()
        if key in self._cache:
            return self._cache[key]
        # try disk
        path = self._path(d.year)
        if path.exists():
            with path.open() as f:
                for line in f:
                    try:
                        row = json.loads(line)
                        if row.get("day") == key:
                            w = WeatherDay(**row)
                            self._cache[key] = w
                            return w
                    except Exception:
                        continue
        w = simulate_weather_day(d, country=country, city=city, latitude=latitude)
        self._append(w)
        self._cache[key] = w
        return w

    def _append(self, w: WeatherDay):
        path = self._path(int(w.day[:4]))
        with path.open("a") as f:
            f.write(json.dumps(w.to_dict()) + "\n")

    def record_observed(self, w: WeatherDay):
        w.source = w.source or "sensor"
        self._append(w)
        self._cache[w.day] = w

    def range_days(self, start: date, end: date, **loc) -> List[WeatherDay]:
        out = []
        d = start
        while d <= end:
            out.append(self.get_or_simulate(d, **loc))
            d += timedelta(days=1)
        return out

    def memories_of_yesteryear(self, on: date, years_back: int = 10, **loc) -> List[Dict[str, Any]]:
        """
        Same calendar day across prior years — humanizing continuity.
        """
        mems = []
        for y in range(1, years_back + 1):
            try:
                past = date(on.year - y, on.month, on.day)
            except ValueError:
                continue  # Feb 29
            w = self.get_or_simulate(past, **loc)
            mems.append(
                {
                    "years_ago": y,
                    "date": past.isoformat(),
                    "condition": w.condition,
                    "temp_c": w.temp_c,
                    "precip_mm": w.precip_mm,
                    "noise_db": w.noise_db,
                    "blurb": self._memory_blurb(y, w),
                }
            )
        return mems

    def _memory_blurb(self, years_ago: int, w: WeatherDay) -> str:
        when = f"{years_ago} year{'s' if years_ago != 1 else ''} ago"
        return (
            f"{when} on this day it was {w.condition}, about {w.temp_c:.0f}°C "
            f"in {w.city}, with noise around {w.noise_db:.0f} dB."
        )
