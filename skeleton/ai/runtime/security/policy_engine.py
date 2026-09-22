"""Policy engine — declarative guardrail evaluation for operator actions.

Evaluates named policies (rules with conditions) before sensitive
operations execute: deploys, secret access, threshold changes,
rollbacks. Rules compose with AND/OR/NOT, support context attributes
(actor, time, subsystem, payload), and produce allow/deny/audit
verdicts with full decision traces.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Rule:
    name: str
    condition: Callable[[Dict[str, Any]], bool]
    effect: str = "deny"
    reason: str = ""

    def evaluate(self, context: Dict[str, Any]) -> bool:
        try:
            return bool(self.condition(context))
        except Exception:  # noqa: BLE001
            return False


@dataclass
class Policy:
    name: str
    rules: List[Rule] = field(default_factory=list)
    combinator: str = "any"
    default: str = "allow"


@dataclass
class Decision:
    allowed: bool
    effect: str
    matched_rule: Optional[str]
    policy: str
    reason: str
    timestamp_ns: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "effect": self.effect,
            "matched_rule": self.matched_rule,
            "policy": self.policy,
            "reason": self.reason,
        }


class PolicyEngine:
    """Declarative guardrail evaluation with decision traces."""

    def __init__(self):
        self._policies: Dict[str, Policy] = {}
        self._decisions: List[Decision] = []

    def define(self, name: str, combinator: str = "any", default: str = "allow") -> Policy:
        p = Policy(name=name, combinator=combinator, default=default)
        self._policies[name] = p
        return p

    def add_rule(self, policy: str, name: str,
                 condition: Callable[[Dict[str, Any]], bool],
                 effect: str = "deny", reason: str = "") -> Rule:
        rule = Rule(name=name, condition=condition, effect=effect, reason=reason)
        self._policies[policy].rules.append(rule)
        return rule

    def evaluate(self, policy: str, context: Dict[str, Any]) -> Decision:
        p = self._policies.get(policy)
        if not p:
            decision = Decision(True, "allow", None, policy, "unknown policy — default allow", time.time_ns())
            self._decisions.append(decision)
            return decision
        if p.combinator == "any":
            for rule in p.rules:
                if rule.evaluate(context):
                    decision = Decision(
                        allowed=rule.effect != "deny",
                        effect=rule.effect,
                        matched_rule=rule.name,
                        policy=policy,
                        reason=rule.reason or f"rule {rule.name} matched",
                        timestamp_ns=time.time_ns(),
                    )
                    self._decisions.append(decision)
                    return decision
        else:
            matches = [r for r in p.rules if r.evaluate(context)]
            if len(matches) == len(p.rules) and p.rules:
                effect = p.rules[0].effect
                decision = Decision(effect != "deny", effect, p.rules[0].name, policy,
                                    "all rules matched", time.time_ns())
                self._decisions.append(decision)
                return decision
        decision = Decision(p.default == "allow", p.default, None, policy, "no rules matched — default", time.time_ns())
        self._decisions.append(decision)
        return decision

    def deny_rate(self, policy: Optional[str] = None) -> float:
        decisions = [d for d in self._decisions if policy is None or d.policy == policy]
        if not decisions:
            return 0.0
        return len([d for d in decisions if not d.allowed]) / len(decisions)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "policy-engine-card",
            "policies": {n: {"rules": len(p.rules), "combinator": p.combinator, "default": p.default}
                         for n, p in self._policies.items()},
            "decisions": len(self._decisions),
            "deny_rate": round(self.deny_rate(), 3),
            "recent": [d.to_dict() for d in self._decisions[-5:]],
        }
