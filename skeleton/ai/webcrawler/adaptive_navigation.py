"""Deterministic outcome-driven navigation under existing Dragon authority.

Only committed local outcome events inform these advisory estimates. This
module never creates a frontier URL, accesses a socket, removes a hold,
changes robots policy, or consumes a grant. Times and scores are not rights.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from urllib.parse import urlsplit

MAX_EVENTS = 64
MAX_ORIGIN_SAMPLES = 16
MAX_ADAPTIVE_WAIT = 120.0
_SUCCESS = frozenset({"captured", "discovered", "duplicate"})
_FAILURE = frozenset({"error", "retry", "interrupted_dispatch"})
_REJECTED = frozenset({"rejected", "source_rights_restricted"})


@dataclass(frozen=True)
class OriginHealth:
    successes: int
    failures: int
    rejections: int
    failure_streak: int
    posterior_success: float
    uncertainty: float
    evidence_count: int

    @property
    def quality(self) -> float:
        # A prior prevents a single result from dominating. Exploration
        # rewards sparse observations; rejections are a separate cost signal.
        penalty = min(.30, .06 * self.failure_streak + .04 * self.rejections)
        return min(1., max(0., self.posterior_success + .12 * self.uncertainty - penalty))


def _outcomes(events, host):
    if not isinstance(events, (list, tuple)) or len(events) > MAX_EVENTS:
        raise ValueError("invalid adaptive outcome history")
    if not isinstance(host, str) or not host or len(host) > 253:
        raise ValueError("invalid adaptive destination")
    result = []
    for event in reversed(events):
        if not isinstance(event, dict):
            raise ValueError("invalid adaptive outcome event")
        kind, url = event.get("kind"), event.get("url")
        if kind not in _SUCCESS | _FAILURE | _REJECTED or not isinstance(url, str):
            continue
        if urlsplit(url).hostname != host:
            continue
        result.append(kind)
        if len(result) == MAX_ORIGIN_SAMPLES:
            break
    return result


def origin_health(events, host: str) -> OriginHealth:
    outcomes = _outcomes(events, host)
    successes = sum(x in _SUCCESS for x in outcomes)
    failures = sum(x in _FAILURE for x in outcomes)
    rejections = sum(x in _REJECTED for x in outcomes)
    streak = 0
    for kind in outcomes:
        if kind in _SUCCESS:
            break
        if kind in _FAILURE:
            streak += 1
    n = len(outcomes)
    # Beta(2,2) posterior, bounded diversity incentive, deterministic replay.
    posterior = (2 + successes) / (4 + successes + failures + rejections)
    uncertainty = 1 / math.sqrt(1 + n)
    return OriginHealth(successes, failures, rejections, streak,
                        round(posterior, 8), round(uncertainty, 8), n)


def restorative_wait(events, host: str, *, now: float, expires_at: float) -> float | None:
    """A current failed dispatch may only extend, never relax, a host hold.

    A single transient error retains ordinary per-item retry. Repeated failures
    increase host-wide delay, capped at 120s and the current consent horizon.
    Existing robots/server cooldowns are merged with max() by the owner.
    """
    if any(isinstance(v, bool) or not isinstance(v, (float, int))
           or not math.isfinite(v) or not 0 <= v <= 1e12 for v in (now, expires_at)):
        raise ValueError("invalid restorative clock")
    streak = 1 + origin_health(events, host).failure_streak
    if streak < 2:
        return None
    return min(expires_at, now + min(MAX_ADAPTIVE_WAIT, 2.0 ** min(streak, 7)))


def access_denied_hold(status: int, *, now: float, expires_at: float) -> float | None:
    """Stop further automatic host acquisition under a denied current grant."""
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError("invalid HTTP status")
    if any(isinstance(v, bool) or not isinstance(v, (float, int))
           or not math.isfinite(v) or not 0 <= v <= 1e12 for v in (now, expires_at)):
        raise ValueError("invalid access hold clock")
    return max(now, expires_at) if status in {401, 403, 451} else None


def adaptive_priority(base_score: float, health: OriginHealth, *, coverage_cost: bool) -> float:
    """Compose retrieval utility with observed transport reliability.

    A score changes order only. It never makes a blocked candidate eligible.
    Coverage sorts lower cost first; balanced sorts larger utility first.
    """
    if isinstance(base_score, bool) or not isinstance(base_score, (int, float)) \
            or not math.isfinite(base_score) or not 0 <= base_score <= 1:
        raise ValueError("invalid adaptive priority")
    if not isinstance(health, OriginHealth) or type(coverage_cost) is not bool:
        raise ValueError("invalid adaptive health")
    value = 1 - health.quality if coverage_cost else health.quality
    return round(.80 * base_score + .20 * value, 8)
