"""Robots request-rate compliance for the canonical host admission scheduler.

A publisher's Request-rate: requests/seconds is converted to a finite
minimum same-origin interval, combined conservatively with Crawl-delay and
the operator's original host delay. No directive grants a fetch or changes
destination/consent/byte limits; a delay outside consent horizon fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


MAX_ROBOTS_DELAY = 86400.0


class RobotsRateError(ValueError):
    """Robots constraints are malformed or exceed finite scheduling scope."""


@dataclass(frozen=True)
class RobotsPacing:
    minimum_seconds: float
    request_rate_seconds: float | None
    crawl_delay_seconds: float | None
    operator_delay_seconds: float
    denied: bool
    source_authority_not_expanded: bool = True


def combine_robots_pacing(
    *, operator_delay: float, crawl_delay: float | None,
    requests: int | None = None, seconds: int | None = None,
) -> RobotsPacing:
    if (
        isinstance(operator_delay, bool)
        or not isinstance(operator_delay, (int, float))
        or not math.isfinite(operator_delay)
        or not 0.25 <= operator_delay <= 30
    ):
        raise RobotsRateError("invalid operator-host pacing grant")
    if crawl_delay is not None and (
        isinstance(crawl_delay, bool)
        or not isinstance(crawl_delay, (int, float))
        or not math.isfinite(crawl_delay)
        or crawl_delay < 0
    ):
        raise RobotsRateError("invalid robots crawl delay")
    if (requests is None) != (seconds is None):
        raise RobotsRateError("incomplete robots request-rate")
    interval = None
    if requests is not None:
        if (type(requests) is not int or type(seconds) is not int
                or not 1 <= requests <= 100000
                or not 1 <= seconds <= 100000000):
            raise RobotsRateError("invalid robots request-rate bound")
        interval = seconds / requests
    minimum = max(float(operator_delay), float(crawl_delay or 0), interval or 0.0)
    denied = minimum > MAX_ROBOTS_DELAY
    return RobotsPacing(
        minimum_seconds=min(minimum, MAX_ROBOTS_DELAY),
        request_rate_seconds=interval,
        crawl_delay_seconds=crawl_delay,
        operator_delay_seconds=float(operator_delay),
        denied=denied,
    )
