"""Deterministic fail-closed policy precedence and conflict resolution.

G131 authority: one total order for layered policy, with invariants above every
mutable policy layer.  Decisions are content-bound so replay under changed
policy cannot silently inherit an obsolete authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable, Literal

Effect = Literal["allow", "deny"]
Layer = Literal["tenant", "operator", "developer", "system", "invariant"]

_LAYER_RANK: dict[str, int] = {
    "tenant": 10,
    "operator": 20,
    "developer": 30,
    "system": 40,
    "invariant": 50,
}

@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    layer: Layer
    effect: Effect
    action: str
    condition_digest: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id or self.layer not in _LAYER_RANK:
            raise ValueError("invalid policy rule")
        if self.effect not in ("allow", "deny") or not self.action:
            raise ValueError("invalid policy rule")

@dataclass(frozen=True)
class PolicyDecision:
    action: str
    effect: Effect
    authority_layer: Layer
    rule_ids: tuple[str, ...]
    policy_digest: str

class PolicyConflictError(RuntimeError):
    pass

def _digest(rules: Iterable[PolicyRule]) -> str:
    payload = [
        {
            "action": r.action,
            "condition_digest": r.condition_digest,
            "effect": r.effect,
            "layer": r.layer,
            "rule_id": r.rule_id,
        }
        for r in sorted(rules, key=lambda x: (x.layer, x.action, x.rule_id, x.effect, x.condition_digest))
    ]
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def resolve_policy(action: str, rules: Iterable[PolicyRule]) -> PolicyDecision:
    """Resolve exact-action rules using the repository-wide G131 contract.

    Highest authority wins across layers. Contradictory rules at the same
    highest layer fail closed instead of depending on input order. Multiple
    equivalent rules are permitted and retained as evidence.
    """
    if not action:
        raise ValueError("action is required")
    matched = tuple(r for r in rules if r.action == action)
    if not matched:
        raise PolicyConflictError("no authoritative policy rule")
    top_rank = max(_LAYER_RANK[r.layer] for r in matched)
    top = tuple(r for r in matched if _LAYER_RANK[r.layer] == top_rank)
    effects = {r.effect for r in top}
    if len(effects) != 1:
        raise PolicyConflictError("conflicting rules at equal authority")
    effect = next(iter(effects))
    layer = top[0].layer
    return PolicyDecision(
        action=action,
        effect=effect,
        authority_layer=layer,
        rule_ids=tuple(sorted(r.rule_id for r in top)),
        policy_digest=_digest(matched),
    )

def verify_replay(decision: PolicyDecision, rules: Iterable[PolicyRule]) -> bool:
    """Require replay to resolve to the exact original content-bound decision."""
    current = resolve_policy(decision.action, tuple(rules))
    return current == decision
