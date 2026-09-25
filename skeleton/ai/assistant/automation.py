"""Automation intent construction and schedule safety checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Mapping

from .contracts import AutomationIntent, TimingMode


_RRULE = re.compile(r"(?:^|\n)RRULE:([^\n]+)", re.IGNORECASE)
_FREQ = re.compile(r"(?:^|;)FREQ=([A-Z]+)(?:;|$)", re.IGNORECASE)
_INTERVAL = re.compile(r"(?:^|;)INTERVAL=(\d+)(?:;|$)", re.IGNORECASE)


class AutomationPolicyError(ValueError):
    """An automation would violate bounded scheduling rules."""


@dataclass(frozen=True, slots=True)
class AutomationAdmission:
    allowed: bool
    reason_code: str


class AutomationPolicy:
    """Validate assistant automations without interpreting arbitrary cron code."""

    def __init__(self, *, minimum_recurring_seconds: int = 3600) -> None:
        if minimum_recurring_seconds < 3600:
            raise ValueError("minimum recurring interval cannot be below one hour")
        self.minimum_recurring_seconds = minimum_recurring_seconds

    @staticmethod
    def _estimated_interval_seconds(schedule: str) -> int | None:
        match = _RRULE.search(schedule)
        if match is None:
            return None
        body = match.group(1).upper()
        freq_match = _FREQ.search(";" + body)
        if freq_match is None:
            return None
        interval_match = _INTERVAL.search(";" + body)
        interval = int(interval_match.group(1)) if interval_match else 1
        unit = {
            "SECONDLY": 1,
            "MINUTELY": 60,
            "HOURLY": 3600,
            "DAILY": 86_400,
            "WEEKLY": 604_800,
            "MONTHLY": 2_419_200,
            "YEARLY": 31_536_000,
        }.get(freq_match.group(1))
        if unit is None:
            return None
        return unit * interval

    def admit(self, intent: AutomationIntent) -> AutomationAdmission:
        if intent.timing_mode is TimingMode.CONDITION:
            if intent.schedule is None:
                return AutomationAdmission(False, "condition-watch-requires-recurrence")
            interval = self._estimated_interval_seconds(intent.schedule)
            if interval is not None and interval < self.minimum_recurring_seconds:
                return AutomationAdmission(False, "condition-watch-too-frequent")
            return AutomationAdmission(True, "condition-watch-admitted")

        if intent.schedule is not None:
            interval = self._estimated_interval_seconds(intent.schedule)
            if interval is not None and interval < self.minimum_recurring_seconds:
                return AutomationAdmission(False, "recurrence-too-frequent")
        return AutomationAdmission(True, "time-automation-admitted")

    def require(self, intent: AutomationIntent) -> None:
        decision = self.admit(intent)
        if not decision.allowed:
            raise AutomationPolicyError(decision.reason_code)


class AutomationBuilder:
    """Create normalized automation intents from already-resolved timing."""

    @staticmethod
    def relative(
        *,
        title: str,
        instruction: str,
        offset: Mapping[str, int],
    ) -> AutomationIntent:
        return AutomationIntent(
            title=title,
            instruction=instruction,
            timing_mode=TimingMode.EXACT,
            relative_offset=dict(offset),
        )

    @staticmethod
    def scheduled(
        *,
        title: str,
        instruction: str,
        vevent: str,
        exact: bool,
    ) -> AutomationIntent:
        return AutomationIntent(
            title=title,
            instruction=instruction,
            timing_mode=TimingMode.EXACT if exact else TimingMode.FLEXIBLE,
            schedule=vevent,
        )

    @staticmethod
    def condition(
        *,
        title: str,
        instruction: str,
        condition_description: str,
        recurrence_vevent: str,
    ) -> AutomationIntent:
        return AutomationIntent(
            title=title,
            instruction=instruction,
            timing_mode=TimingMode.CONDITION,
            schedule=recurrence_vevent,
            condition_description=condition_description,
        )


__all__ = [
    "AutomationAdmission",
    "AutomationBuilder",
    "AutomationPolicy",
    "AutomationPolicyError",
]
