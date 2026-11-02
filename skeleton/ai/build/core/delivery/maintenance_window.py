"""Weekly deploy windows and change freezes, evaluated in UTC seconds."""

from __future__ import annotations

from dataclasses import dataclass
import re
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
        # Arithmetic normalization must not turn 08:60 or 24:01 into a
        # different, valid deploy window. Parse the clock fields strictly.
        match = re.fullmatch(
            r"([a-z]{3}) ([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2})",
            text.strip().lower() if isinstance(text, str) else "",
        )
        if match is None:
            raise DeliveryError("window must look like 'tue 09:00-17:00'")
        day, sh, sm, eh, em = match.groups()
        start_hour, start_minute = int(sh), int(sm)
        end_hour, end_minute = int(eh), int(em)
        if (start_hour > 23 or start_minute > 59 or end_minute > 59
                or end_hour > 24 or (end_hour == 24 and end_minute != 0)):
            raise DeliveryError("window clock fields out of range")
        return cls(day, start_hour * 60 + start_minute,
                   end_hour * 60 + end_minute)


@dataclass(frozen=True)
class Freeze:
    start: int
    end: int
    reason: str

    def __post_init__(self) -> None:
        if (type(self.start) is not int or type(self.end) is not int
                or self.start < 0 or self.end <= self.start):
            raise DeliveryError("freeze timestamps must be increasing nonnegative integers")
        if (type(self.reason) is not str or not self.reason.strip()
                or len(self.reason) > 256
                or any(ord(char) < 32 or ord(char) == 127 for char in self.reason)):
            raise DeliveryError("freeze reason must be bounded printable text")


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
