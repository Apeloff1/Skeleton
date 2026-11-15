"""Bounded robots matching and merged product-group pacing.

Only restrictions are interpreted here; this module never dispatches requests.
Matching uses normalized URI octets, not decoded reserved delimiters. A work
budget failure denies access rather than treating a rule as absent.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

MAX_POLICY_BYTES = 512 * 1024
MAX_RULES = 32768
MAX_TARGET_BYTES = 16384
MAX_MATCH_WORK = 8_000_000
_AGENT = re.compile(r"[A-Za-z_-]+\Z")
_DELAY = re.compile(r"[0-9]{1,9}(?:\.[0-9]{1,6})?\Z")
_RATE = re.compile(r"([0-9]{1,9})\s*/\s*([0-9]{1,9})\Z")
_HEX = frozenset(b"0123456789abcdefABCDEF")
_UNRESERVED = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


@dataclass(frozen=True)
class RequestRate:
    requests: int
    seconds: int


@dataclass(frozen=True)
class Rule:
    pattern: bytes
    allow: bool
    specificity: int


@dataclass(frozen=True)
class Group:
    agents: tuple[str, ...]
    rules: tuple[Rule, ...]
    delay: float | None
    rate: RequestRate | None
    pacing_invalid: bool


def _octets(value: str) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > MAX_POLICY_BYTES:
        raise ValueError("robots octet input exceeds bound")
    out = bytearray()
    i = 0
    while i < len(raw):
        item = raw[i]
        if item == 37 and i + 2 < len(raw) and raw[i + 1] in _HEX and raw[i + 2] in _HEX:
            decoded = int(raw[i + 1:i + 3], 16)
            if decoded in _UNRESERVED:
                out.append(decoded)
            else:
                out.extend(("%" + format(decoded, "02X")).encode("ascii"))
            i += 3
            continue
        if item >= 128 or item <= 32 or item == 127 or item == 37:
            out.extend(("%" + format(item, "02X")).encode("ascii"))
        else:
            out.append(item)
        i += 1
    return bytes(out)


def _make_rule(value: str, allow: bool) -> Rule | None:
    if not value or not value.startswith("/"):
        return None
    # Preserve literal encoded wildcard and end-marker as percent triplets.
    pattern = _octets(value)
    # Measure the normalized pattern in octets, retaining special tokens for
    # longest-rule selection; collapse consecutive stars only for matching.
    return Rule(pattern, allow, len(pattern))


def _matches(rule: Rule, target: bytes) -> bool:
    pattern = rule.pattern
    anchored = pattern.endswith(b"$")
    if anchored:
        pattern = pattern[:-1]
    if b"*" not in pattern:
        return target == pattern if anchored else target.startswith(pattern)
    parts = pattern.split(b"*")
    first, last = parts[0], parts[-1]
    if not target.startswith(first):
        return False
    pos, end = len(first), len(target)
    if anchored and last:
        if not target.endswith(last):
            return False
        end -= len(last)
        if end < pos:
            return False
    middle = parts[1:-1] if anchored else parts[1:]
    for part in middle:
        if not part:
            continue
        at = target.find(part, pos, end)
        if at < 0:
            return False
        pos = at + len(part)
    return pos <= end


def _strictest_rate(left: RequestRate | None, right: RequestRate | None) -> RequestRate | None:
    if left is None:
        return right
    if right is None:
        return left
    # Avoid floating-point comparison and preserve the exact original ratio.
    return right if right.seconds * left.requests > left.seconds * right.requests else left


class RobotsPolicy:
    def __init__(self, text: str):
        self.groups: tuple[Group, ...] = ()
        self.invalid = False
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_POLICY_BYTES:
            self.invalid = True
            return
        groups: list[Group] = []
        agents: list[str] = []
        rules: list[Rule] = []
        delay: float | None = None
        rate: RequestRate | None = None
        pacing_invalid = False
        saw_rule = False
        count = 0

        def flush():
            nonlocal agents, rules, delay, rate, pacing_invalid, saw_rule
            if agents:
                groups.append(Group(tuple(agents), tuple(rules), delay, rate, pacing_invalid))
            agents, rules = [], []
            delay, rate = None, None
            pacing_invalid, saw_rule = False, False

        for line in text.removeprefix("\ufeff").splitlines():
            key, sep, value = line.partition("#")[0].partition(":")
            if not sep:
                continue
            key, value = key.strip().casefold(), value.strip()
            if key == "user-agent":
                if saw_rule:
                    flush()
                if value == "*" or _AGENT.fullmatch(value):
                    agents.append(value.casefold())
                # Versioned/nonstandard labels are recognized only by the full
                # identification string, never loose substring matching.
                elif "/" in value and len(value) <= 128 and all(32 < ord(c) < 127 for c in value):
                    agents.append(value.casefold())
                continue
            if not agents:
                continue
            if key in {"allow", "disallow"}:
                saw_rule = True
                rule = _make_rule(value, key == "allow")
                if rule is not None:
                    count += 1
                    if count > MAX_RULES:
                        self.invalid = True
                        return
                    rules.append(rule)
            elif key == "crawl-delay":
                saw_rule = True
                if _DELAY.fullmatch(value):
                    parsed = float(value)
                    delay = parsed if delay is None else max(delay, parsed)
                else:
                    pacing_invalid = True
            elif key == "request-rate":
                saw_rule = True
                match = _RATE.fullmatch(value)
                if match:
                    requests, seconds = (int(v) for v in match.groups())
                    if 1 <= requests <= 100000 and 1 <= seconds <= 100000000:
                        rate = _strictest_rate(rate, RequestRate(requests, seconds))
                    else:
                        pacing_invalid = True
                else:
                    pacing_invalid = True
            # Unknown fields and sitemap hints do not end REP groups.
        flush()
        self.groups = tuple(groups)

    def _selected(self, user_agent: str) -> tuple[Group, ...]:
        token = user_agent.split("/", 1)[0].casefold()
        full = user_agent.casefold()
        exact = tuple(group for group in self.groups if token in group.agents or full in group.agents)
        return exact or tuple(group for group in self.groups if "*" in group.agents)

    def can_fetch(self, user_agent: str, url: str) -> bool:
        if self.invalid or not isinstance(url, str) or len(url) > MAX_TARGET_BYTES:
            return False
        parts = urlsplit(url)
        target = _octets((parts.path or "/") + ("?" + parts.query if parts.query else ""))
        if len(target) > MAX_TARGET_BYTES:
            return False
        if target == b"/robots.txt":
            return True
        groups = self._selected(user_agent)
        if any(group.pacing_invalid for group in groups):
            return False
        # Bound worst-case string searching even for repeated-star input.
        work = 0
        best: tuple[int, bool] | None = None
        for group in groups:
            for rule in group.rules:
                work += (len(target) + len(rule.pattern)) * (1 + rule.pattern.count(b"*"))
                if work > MAX_MATCH_WORK:
                    return False
                if _matches(rule, target):
                    candidate = (rule.specificity, rule.allow)
                    if best is None or candidate > best:
                        best = candidate
        return best is None or best[1]

    def crawl_delay(self, user_agent: str) -> float | None:
        values = [group.delay for group in self._selected(user_agent) if group.delay is not None]
        return max(values) if values else None

    def request_rate(self, user_agent: str) -> RequestRate | None:
        result = None
        for group in self._selected(user_agent):
            result = _strictest_rate(result, group.rate)
        return result
