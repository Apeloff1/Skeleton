"""Weekly deploy windows and change freezes, evaluated in UTC seconds."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
import re
from datetime import datetime, timezone
from typing import Iterable

from skeleton.build.delivery._util import DeliveryError

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MAX_WINDOWS = 256
MAX_FREEZES = 4096
MAX_UNIX_TIMESTAMP = 253402300799


@dataclass(frozen=True)
class Window:
    day: str
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if self.day not in DAYS:
            raise DeliveryError(f"unknown day {self.day!r}")
        if (type(self.start_minute) is not int or type(self.end_minute) is not int
                or not 0 <= self.start_minute < self.end_minute <= 1440):
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
    if type(ts) is not int or not 0 <= ts <= MAX_UNIX_TIMESTAMP:
        raise DeliveryError("invalid deployment timestamp")
    moment = datetime.fromtimestamp(ts, tz=timezone.utc)
    day = DAYS[moment.weekday()]
    minute = moment.hour * 60 + moment.minute
    matched = False
    for count, window in enumerate(windows, 1):
        if count > MAX_WINDOWS:
            raise DeliveryError("deployment window count exceeds bound")
        if type(window) is not Window:
            raise DeliveryError("invalid deployment window")
        matched |= window.day == day and window.start_minute <= minute < window.end_minute
    return matched


def active_freeze(ts: int, freezes: Iterable[Freeze]) -> Freeze | None:
    active = None
    for count, freeze in enumerate(freezes, 1):
        if count > MAX_FREEZES:
            raise DeliveryError("deployment freeze count exceeds bound")
        if type(freeze) is not Freeze:
            raise DeliveryError("invalid deployment freeze")
        if freeze.start <= ts < freeze.end:
            active = freeze
    return active


def may_deploy(ts: int, *, tier: str, windows: Iterable[Window], freezes: Iterable[Freeze] = ()) -> tuple[bool, str]:
    if type(ts) is not int or not 0 <= ts <= MAX_UNIX_TIMESTAMP:
        return False, "invalid-timestamp"
    if tier not in ("dev", "staging", "production"):
        return False, "unknown-tier"
    if tier == "dev":
        return True, "dev-unrestricted"
    freeze = active_freeze(ts, freezes)
    if freeze is not None:
        return False, f"freeze:{freeze.reason}"
    window_list = list(islice(windows, MAX_WINDOWS + 1))
    if len(window_list) > MAX_WINDOWS:
        return False, "too-many-windows"
    if not window_list:
        return False, "no-windows-configured"
    if not in_window(ts, window_list):
        return False, "outside-window"
    return True, "in-window"
