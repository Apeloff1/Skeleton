"""Per-service-identity rate limits (GCRA) for the s2s gate.

Limits are keyed by the *verified* caller identity, never by IP or a
client-supplied header, so one noisy or compromised service cannot starve
the others. Each rule is a Generic Cell Rate Algorithm limiter
(equivalent to a token bucket with ``rate_per_s`` refill and ``burst``
capacity, but O(1) state: one theoretical-arrival-time per key).

Rules are matched most-specific first:

1. ``(service, policy)`` — e.g. ``("forge-worker", "swarm-write")``
2. ``(service, "*")``
3. ``("*", policy)``
4. ``default``

Requests can carry a ``cost`` (writes may cost more than reads). A denied
request reports ``retry_after_s`` (two-decimal rounding, same field as
``RateLimitError`` and the Pack H pressure snapshot) so the gate returns
``429`` + ``Retry-After``. Key state is LRU-bounded so a flood of distinct
identities cannot grow memory without bound. Anonymous traffic shares a
single ``anonymous`` identity.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from skeleton.gate_plane.s2s.clock import Clock, system_clock

ANONYMOUS = "anonymous"
WILDCARD = "*"
MAX_TRACKED_KEYS = 50_000
DEFAULT_WRITE_COST = 1.0
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class RateRule:
    rate_per_s: float
    burst: float
    write_cost: float = DEFAULT_WRITE_COST
    name: str = ""

    def __post_init__(self) -> None:
        if not (self.rate_per_s > 0 and math.isfinite(self.rate_per_s)):
            raise ValueError("rate_per_s must be finite and > 0")
        if not (self.burst >= 1 and math.isfinite(self.burst)):
            raise ValueError("burst must be finite and >= 1")
        if self.write_cost <= 0:
            raise ValueError("write_cost must be > 0")

    @property
    def emission_interval(self) -> float:
        return 1.0 / self.rate_per_s

    @property
    def tolerance(self) -> float:
        return (self.burst - 1.0) * self.emission_interval

    def cost_for(self, method: str) -> float:
        return self.write_cost if (method or "GET").upper() in WRITE_METHODS else 1.0

    def as_dict(self) -> Dict[str, Any]:
        return {"rate_per_s": self.rate_per_s, "burst": self.burst, "write_cost": self.write_cost, "name": self.name}


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    key: Tuple[str, str]
    rule: Optional[str]
    remaining: float
    retry_after_s: Optional[float] = None
    limit: Optional[float] = None

    def headers(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        if self.limit is not None:
            out.append(("ratelimit-limit", str(int(self.limit))))
            out.append(("ratelimit-remaining", str(max(0, int(self.remaining)))))
        if self.retry_after_s is not None:
            out.append(("retry-after", str(max(1, int(math.ceil(self.retry_after_s))))))
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "service": self.key[0],
            "policy": self.key[1],
            "rule": self.rule,
            "remaining": round(self.remaining, 3),
            "retry_after_s": self.retry_after_s,
        }


class ServiceRateLimiter:
    """GCRA limiter table keyed by ``(service, policy)``."""

    def __init__(
        self,
        rules: Optional[Mapping[Tuple[str, str], RateRule]] = None,
        *,
        default: Optional[RateRule] = None,
        clock: Optional[Clock] = None,
        max_keys: int = MAX_TRACKED_KEYS,
        exempt_services: Iterable[str] = (),
    ) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be >= 1")
        self._rules: Dict[Tuple[str, str], RateRule] = dict(rules or {})
        self.default = default
        self.clock: Clock = clock or system_clock()
        self.max_keys = int(max_keys)
        self.exempt_services = frozenset(exempt_services)
        self._tat: "OrderedDict[Tuple[str, str, str], float]" = OrderedDict()
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}

    def set_rule(self, service: str, policy: str, rule: RateRule) -> None:
        with self._lock:
            self._rules[(service, policy)] = rule

    def rule_for(self, service: str, policy: str) -> Tuple[Optional[RateRule], str]:
        for key in ((service, policy), (service, WILDCARD), (WILDCARD, policy)):
            rule = self._rules.get(key)
            if rule is not None:
                return rule, f"{key[0]}/{key[1]}"
        if self.default is not None:
            return self.default, "default"
        return None, ""

    def _count(self, key: str) -> None:
        self._counts[key] = self._counts.get(key, 0) + 1

    def check(self, service: Optional[str], policy: Optional[str], *, method: str = "GET") -> RateDecision:
        svc = service or ANONYMOUS
        pol = policy or WILDCARD
        key = (svc, pol)
        if svc in self.exempt_services:
            with self._lock:
                self._count("exempt")
            return RateDecision(True, key, "exempt", float("inf"))
        rule, rule_name = self.rule_for(svc, pol)
        if rule is None:
            with self._lock:
                self._count("unlimited")
            return RateDecision(True, key, None, float("inf"))
        cost = rule.cost_for(method)
        increment = rule.emission_interval * cost
        # Bucket identity is the *rule* scope: a (svc, "*") rule shares one
        # bucket across that service's policies.
        bucket_pol = pol if rule_name == f"{svc}/{pol}" or rule_name == f"{WILDCARD}/{pol}" else WILDCARD
        bkey = (svc, bucket_pol, rule_name)
        now = self.clock.monotonic()
        with self._lock:
            tat = self._tat.get(bkey, now)
            tat = max(tat, now)
            new_tat = tat + increment
            allow_at = new_tat - rule.tolerance - rule.emission_interval
            if allow_at > now + 1e-9:
                retry_after = round(max(0.01, allow_at - now), 2)
                remaining = max(0.0, (rule.tolerance + rule.emission_interval - (tat - now)) / rule.emission_interval)
                self._count("denied")
                self._touch(bkey, tat)
                return RateDecision(False, key, rule_name, remaining, retry_after_s=retry_after, limit=rule.burst)
            self._touch(bkey, new_tat)
            remaining = max(0.0, (rule.tolerance + rule.emission_interval - (new_tat - now)) / rule.emission_interval)
            self._count("allowed")
            return RateDecision(True, key, rule_name, remaining, limit=rule.burst)

    def _touch(self, bkey: Tuple[str, str, str], tat: float) -> None:
        self._tat[bkey] = tat
        self._tat.move_to_end(bkey)
        while len(self._tat) > self.max_keys:
            self._tat.popitem(last=False)
            self._count("evicted")

    def reset(self, service: Optional[str] = None) -> None:
        with self._lock:
            if service is None:
                self._tat.clear()
            else:
                for k in [k for k in self._tat if k[0] == service]:
                    del self._tat[k]

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._tat)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tracked_keys": len(self._tat),
                "rules": {f"{k[0]}/{k[1]}": r.as_dict() for k, r in sorted(self._rules.items())},
                "default": None if self.default is None else self.default.as_dict(),
                **dict(self._counts),
            }


def limiter_from_config(config: Mapping[str, Any], *, clock: Optional[Clock] = None) -> ServiceRateLimiter:
    """Build from a plain mapping (env/YAML friendly)::

        {"default": {"rate_per_s": 50, "burst": 100},
         "rules": [{"service": "forge-worker", "policy": "*", "rate_per_s": 10, "burst": 20}],
         "exempt": ["control-plane"]}
    """
    def rule(d: Mapping[str, Any], name: str = "") -> RateRule:
        return RateRule(
            rate_per_s=float(d["rate_per_s"]), burst=float(d.get("burst", d["rate_per_s"])),
            write_cost=float(d.get("write_cost", DEFAULT_WRITE_COST)), name=name,
        )

    rules: Dict[Tuple[str, str], RateRule] = {}
    for row in config.get("rules", []) or []:
        svc = str(row.get("service", WILDCARD))
        pol = str(row.get("policy", WILDCARD))
        if svc == WILDCARD and pol == WILDCARD:
            raise ValueError("use 'default' for the */* rule")
        rules[(svc, pol)] = rule(row, f"{svc}/{pol}")
    default = rule(config["default"], "default") if config.get("default") else None
    return ServiceRateLimiter(rules, default=default, clock=clock, exempt_services=config.get("exempt", ()) or ())


__all__ = [
    "ANONYMOUS",
    "RateDecision",
    "RateRule",
    "ServiceRateLimiter",
    "WILDCARD",
    "limiter_from_config",
]
