"""Deterministic IF / OR / AND / BUT rules for Dragon research automation.

Rules consume trusted, typed service facts, never an HTTP request body. Unknown
facts fail closed. BUT is a veto, not a lower-priority score adjustment.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

FACTS = frozenset({
    "task_relevant", "adjacent_relevant", "revision_changed", "novel",
    "reviewed", "rights_checked", "source_current", "independent_groups",
    "analysis_passed", "adversarial_passed", "human_approved",
    "usefulness_proven", "regression_free", "owner_authorized", "consented",
    "idle", "resource_admitted", "conflicting", "retracted", "stale",
    "privacy_risk", "license_blocked", "benchmark_leakage",
    "foreground_active", "budget_exhausted",
})
VETOES = (
    "conflicting", "retracted", "stale", "privacy_risk", "license_blocked",
    "benchmark_leakage", "foreground_active", "budget_exhausted",
)


@dataclass(frozen=True)
class ConditionalRule:
    if_any: tuple[str, ...]
    and_all: tuple[str, ...]
    or_any: tuple[str, ...] = ()
    but_none: tuple[str, ...] = VETOES

    def __post_init__(self) -> None:
        for group in (self.if_any, self.and_all, self.or_any, self.but_none):
            if (not isinstance(group, tuple) or len(group) > len(FACTS)
                    or len(set(group)) != len(group)
                    or any(not isinstance(x, str) or x not in FACTS for x in group)):
                raise ValueError("unknown, duplicated or excessive trigger conditions")
        if not self.if_any or not self.and_all or not self.but_none:
            raise ValueError("IF, AND and BUT gates must be present")
        if set(self.but_none) & (
            set(self.if_any) | set(self.and_all) | set(self.or_any)
        ):
            raise ValueError("veto cannot simultaneously be a required signal")


SHADOW_RULE = ConditionalRule(
    if_any=("task_relevant", "adjacent_relevant", "revision_changed"),
    and_all=("reviewed", "rights_checked", "source_current",
             "independent_groups", "analysis_passed", "adversarial_passed",
             "owner_authorized", "consented", "idle", "resource_admitted"),
    or_any=("novel", "revision_changed"),
)
PROMOTION_RULE = ConditionalRule(
    if_any=("task_relevant", "adjacent_relevant", "revision_changed"),
    and_all=("reviewed", "rights_checked", "source_current",
             "independent_groups", "analysis_passed", "adversarial_passed",
             "human_approved", "usefulness_proven", "regression_free",
             "owner_authorized"),
    or_any=("novel", "revision_changed"),
    but_none=tuple(x for x in VETOES if x not in ("foreground_active",)),
)


@dataclass(frozen=True)
class TriggerDecision:
    admitted: bool
    reasons: tuple[str, ...]
    trace_digest: str


def evaluate_trigger(
    rule: ConditionalRule, facts: dict[str, bool | None],
) -> TriggerDecision:
    """IF(any) AND(all) AND OR(any if supplied) BUT(none true or unknown)."""
    if not isinstance(rule, ConditionalRule) or not isinstance(facts, dict):
        raise ValueError("typed policy and facts required")
    if set(facts) - FACTS or any(type(v) is not bool and v is not None
                                for v in facts.values()):
        raise ValueError("unrecognized or untyped signal")
    reasons: list[str] = []
    if not any(facts.get(name) is True for name in rule.if_any):
        reasons.append("if_no_relevant_condition")
    for name in rule.and_all:
        if facts.get(name) is not True:
            reasons.append("and_missing:" + name)
    if rule.or_any and not any(facts.get(name) is True for name in rule.or_any):
        reasons.append("or_no_eligible_alternative")
    for name in rule.but_none:
        if facts.get(name) is not False:
            reasons.append("but_veto_or_unknown:" + name)
    # Include actual measured facts and policy identity in the digest: a caller
    # cannot turn a failed decision into a trusted permit by changing a label.
    body = {
        "rule": [rule.if_any, rule.and_all, rule.or_any, rule.but_none],
        "facts": sorted(facts.items()), "reasons": reasons,
    }
    digest = sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()
    return TriggerDecision(not reasons, tuple(reasons), digest)
