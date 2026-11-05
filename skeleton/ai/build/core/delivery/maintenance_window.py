"""Weekly deploy windows and change freezes, evaluated in UTC seconds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from skeleton.build.delivery._util import DeliveryError

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class Window:
    day: str
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if self.day not in DAYS:
            raise DeliveryError(f"unknown day {self.day!r}")
        if not 0 <= self.start_minute < self.end_minute <= 1440:
            raise DeliveryError("window minutes must satisfy 0 <= start < end <= 1440")

    @classmethod
    def parse(cls, text: str) -> "Window":
        try:
            day, span = text.strip().lower().split(" ", 1)
            start, end = span.split("-")
            sh, sm = (int(x) for x in start.split(":"))
            eh, em = (int(x) for x in end.split(":"))
        except ValueError as exc:
            raise DeliveryError(f"window must look like 'tue 09:00-17:00': {text!r}") from exc
        return cls(day, sh * 60 + sm, eh * 60 + em)


@dataclass(frozen=True)
class Freeze:
    start: int
    end: int
    reason: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise DeliveryError("freeze end must follow start")


def in_window(ts: int, windows: Iterable[Window]) -> bool:
    moment = datetime.fromtimestamp(ts, tz=timezone.utc)
    day = DAYS[moment.weekday()]
    minute = moment.hour * 60 + moment.minute
    return any(w.day == day and w.start_minute <= minute < w.end_minute for w in windows)


def active_freeze(ts: int, freezes: Iterable[Freeze]) -> Freeze | None:
    for freeze in freezes:
        if freeze.start <= ts < freeze.end:
            return freeze
    return None


def may_deploy(ts: int, *, tier: str, windows: Iterable[Window], freezes: Iterable[Freeze] = ()) -> tuple[bool, str]:
    if tier == "dev":
        return True, "dev-unrestricted"
    freeze = active_freeze(ts, freezes)
    if freeze is not None:
        return False, f"freeze:{freeze.reason}"
    window_list = list(windows)
    if not window_list:
        return False, "no-windows-configured"
    if not in_window(ts, window_list):
        return False, "outside-window"
    return True, "in-window"
