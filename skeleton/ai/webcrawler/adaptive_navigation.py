"""Deterministic outcome-driven navigation under existing Dragon authority.

Only committed local outcome events inform these advisory estimates. This
module never creates a frontier URL, accesses a socket, removes a hold,
changes robots policy, or consumes a grant. Times and scores are not rights.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping
from html.parser import HTMLParser
import unicodedata
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

# Access interstitials are not source evidence, even if served with HTTP 200.
# This is deliberately a conservative denial classifier, not a solver.
_MAX_INTERSTITIAL_PREFIX = 32768
_INTERSTITIAL_TITLES = frozenset({
    "access denied", "request blocked", "verify you are human",
    "human verification required", "security verification required",
    "authentication required", "sign in required", "captcha required",
    "checking your browser before accessing", "permission denied",
})


class _InterstitialTitle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.finished = False
        self.invalid = False
        self.parts = []
        self.chars = 0

    def handle_starttag(self, tag, attrs):
        if tag == "body" and not self.in_title:
            self.finished = True
        if tag == "title" and not self.finished:
            if self.in_title:
                self.invalid = True
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title" and self.in_title:
            self.in_title = False
            self.finished = True

    def handle_data(self, data):
        if self.in_title and not self.finished:
            self.chars += len(data)
            if self.chars > 256:
                self.invalid = True
            else:
                self.parts.append(data)

    def matched(self):
        if self.invalid or not self.finished or self.in_title:
            return False
        title = " ".join(unicodedata.normalize("NFKC", "".join(self.parts)).casefold().split())
        return title.rstrip(".!…") in _INTERSTITIAL_TITLES


def access_interstitial_reason(status: int, headers: Mapping[str, str], body: bytes) -> str | None:
    """Return only fixed local reason codes; never retain challenge bytes.

    The caller must charge the original transport before classification and
    stop automatic requests to the host for the remainder of current consent.
    Missing or ambiguous signals do not prove permission. No credentials,
    challenge execution, extra network probes or request changes occur here.
    """
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError("invalid HTTP status")
    if not isinstance(headers, Mapping) or not isinstance(body, bytes):
        raise ValueError("invalid access observation")
    if status == 407:
        return "proxy_authentication_required"
    if status == 402:
        return "payment_required"
    if any(
        isinstance(key, str) and key.casefold() == "cf-mitigated"
        and isinstance(value, str) and value.strip().casefold() == "challenge"
        for key, value in headers.items()
    ):
        return "explicit_access_challenge"
    if 200 <= status < 400 and any(
        isinstance(key, str) and key.casefold() == "www-authenticate"
        and isinstance(value, str) and bool(value.strip())
        for key, value in headers.items()
    ):
        return "authentication_interstitial"
    if not 200 <= status < 300:
        return None
    prefix = body[:_MAX_INTERSTITIAL_PREFIX]
    mime = next((value.split(";", 1)[0].strip().casefold()
                 for key, value in headers.items()
                 if isinstance(key, str) and key.casefold() == "content-type"
                 and isinstance(value, str)), "")
    sniff = prefix[:256].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if mime not in {"text/html", "application/xhtml+xml"} and not sniff.startswith(
        (b"<!doctype html", b"<html", b"<head")
    ):
        return None
    parser = _InterstitialTitle()
    try:
        parser.feed(prefix.decode("utf-8-sig", errors="replace"))
        parser.close()
    except (ValueError, AssertionError, UnicodeError):
        return None
    return "access_interstitial_title" if parser.matched() else None


def acquisition_readiness(*, measurements, host_ready, allowed_hosts, frontier, now, expires_at):
    """Metadata-only view over the canonical checkpoint; never emits fetch targets.

    A deadline spanning the grant is a hold, not evidence of why it occurred.
    Ordinary HTTP status counts survive event-tail eviction, but do not
    identify all challenges (a 200 may be an interstitial). No second state,
    credentials, retries, source substitution or network authority is created.
    """
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
           for v in (now, expires_at)):
        raise ValueError("invalid acquisition readiness clock")
    hosts = tuple(sorted(set(allowed_hosts)))
    if len(hosts) > 16 or len(measurements) > 128 or len(frontier) > 512:
        raise ValueError("acquisition readiness bounds exceeded")
    counts = {host: {"settled": 0, "denial_statuses": 0, "throttle_statuses": 0,
                     "rejected_success_statuses": 0, "queued": 0}
              for host in hosts}
    for row in measurements:
        data = counts[row["host"]]
        status = row["status"]
        data["settled"] += 1
        data["denial_statuses"] += int(status in {401, 402, 403, 407, 451})
        data["throttle_statuses"] += int(status in {429, 503})
        data["rejected_success_statuses"] += int(
            status is not None and 200 <= status < 300 and row["kind"] == "rejected"
        )
    for row in frontier:
        counts[urlsplit(row["url"]).hostname]["queued"] += 1
    rows = []
    for host in hosts:
        ready = host_ready.get(host, 0)
        if now >= expires_at:
            state = "consent_expired"
        elif ready >= expires_at:
            state = "held_for_grant"
        elif ready > now:
            state = "cooldown"
        else:
            state = "no_host_hold"
        rows.append({"host": host, "state": state, "host_ready_at": ready, **counts[host]})
    return {
        "schema": "skeleton.dragon.acquisition-readiness.v1",
        "hosts": rows,
        "settled_requests": len(measurements),
        "queued": len(frontier),
        "network_authority_expanded": False,
        "reason_inferred": False,
        "independent_intake_requires_new_authorization": True,
    }
