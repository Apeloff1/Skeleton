from __future__ import annotations
"""
Geo-aware holiday tables.
Country code switches with user location (ISO 3166-1 alpha-2).
"""

from datetime import date
from typing import Dict, List, Optional, Tuple


# Fixed-date holidays by country (month, day) -> name
FIXED_HOLIDAYS: Dict[str, Dict[Tuple[int, int], str]] = {
    "NO": {
        (1, 1): "Nyttårsdag",
        (5, 1): "Arbeidernes dag",
        (5, 17): "Grunnlovsdag",
        (12, 25): "Første juledag",
        (12, 26): "Andre juledag",
    },
    "US": {
        (1, 1): "New Year's Day",
        (7, 4): "Independence Day",
        (11, 11): "Veterans Day",
        (12, 25): "Christmas Day",
    },
    "GB": {
        (1, 1): "New Year's Day",
        (12, 25): "Christmas Day",
        (12, 26): "Boxing Day",
    },
    "SE": {
        (1, 1): "Nyårsdagen",
        (6, 6): "Sveriges nationaldag",
        (12, 25): "Juldagen",
        (12, 26): "Annandag jul",
    },
    "DE": {
        (1, 1): "Neujahr",
        (10, 3): "Tag der Deutschen Einheit",
        (12, 25): "Erster Weihnachtstag",
        (12, 26): "Zweiter Weihnachtstag",
    },
    "DEFAULT": {
        (1, 1): "New Year's Day",
        (12, 25): "Christmas Day",
    },
}


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def movable_holidays(country: str, year: int) -> Dict[date, str]:
    """Easter-relative and a few common movable observances."""
    out: Dict[date, str] = {}
    e = easter_sunday(year)
    from datetime import timedelta

    if country in ("NO", "SE", "DE", "GB", "DEFAULT"):
        out[e - timedelta(days=3)] = "Maundy Thursday" if country == "GB" else "Skjærtorsdag" if country == "NO" else "Gründonnerstag" if country == "DE" else "Skärtorsdag"
        out[e - timedelta(days=2)] = "Good Friday"
        out[e] = "Easter Sunday"
        out[e + timedelta(days=1)] = "Easter Monday"
        out[e + timedelta(days=39)] = "Ascension Day"
        out[e + timedelta(days=49)] = "Whit Sunday"
        out[e + timedelta(days=50)] = "Whit Monday"
    if country == "US":
        # rough placeholders: 3rd Monday Jan, last Monday May, 1st Monday Sep, 4th Thu Nov
        out[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
        out[_last_weekday(year, 5, 0)] = "Memorial Day"
        out[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
        out[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving"
    return out


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """weekday: Mon=0 .. Sun=6"""
    d = date(year, month, 1)
    from datetime import timedelta

    while d.weekday() != weekday:
        d += timedelta(days=1)
    d += timedelta(weeks=n - 1)
    return d


def _last_weekday(year: int, month: int, weekday: int) -> date:
    from datetime import timedelta

    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def holidays_for(country: str, year: int) -> Dict[date, str]:
    cc = (country or "DEFAULT").upper()
    table = FIXED_HOLIDAYS.get(cc) or FIXED_HOLIDAYS["DEFAULT"]
    out: Dict[date, str] = {}
    for (m, d), name in table.items():
        try:
            out[date(year, m, d)] = name
        except ValueError:
            continue
    out.update(movable_holidays(cc, year))
    return out


def occasions_on(country: str, d: date) -> List[str]:
    h = holidays_for(country, d.year)
    name = h.get(d)
    return [name] if name else []
