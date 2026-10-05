"""Learned repair policy — adapts repair strategy based on historical outcomes.

This module learns which repair actions work best for each surface
and failure pattern, then suggests the most effective repair
strategy for new failures.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.organism.quality_state import load_quality


def _learned_policy_path(root=None) -> Path:
    from skeleton.organism.paths import organism_dir
    return organism_dir(root) / "learned_repair_policy.json"


def _default_learned_policy() -> Dict[str, Any]:
    return {
        "version": 1,
        "surface_strategies": {},
        "action_effectiveness": {},
        "failure_patterns": {},
    }


def load_learned_policy(root=None) -> Dict[str, Any]:
    path = _learned_policy_path(root)
    if not path.exists():
        return _default_learned_policy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_learned_policy()
    base = _default_learned_policy()
    base.update(data)
    return base


def save_learned_policy(policy: Dict[str, Any], root=None) -> None:
    path = _learned_policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2, sort_keys=True), encoding="utf-8")


def _extract_action_key(action: Dict[str, Any]) -> str:
    """Create a stable key for an action type."""
    if "field" in action:
        return f"fill:{action['field']}"
    if "path" in action:
        return f"patch:{action['path']}"
    return "unknown"


def learn_from_repair(result: Dict[str, Any], *, root=None) -> Dict[str, Any]:
    """Update the learned policy from a single repair result."""
    policy = load_learned_policy(root)
    surface = str(result.get("surface") or "unknown")
    reason = str(result.get("reason") or "unknown")
    accepted = bool(result.get("ok") or result.get("accepted"))
    actions = list(result.get("actions") or [])

    # Track surface strategy outcomes
    strategies = policy.setdefault("surface_strategies", {})
    surface_key = f"{surface}:{reason}"
    if surface_key not in strategies:
        strategies[surface_key] = {"attempts": 0, "successes": 0, "actions": {}}
    strat = strategies[surface_key]
    strat["attempts"] = strat.get("attempts", 0) + 1
    if accepted:
        strat["successes"] = strat.get("successes", 0) + 1

    # Track action effectiveness
    action_eff = policy.setdefault("action_effectiveness", {})
    for action in actions:
        key = _extract_action_key(action)
        if key not in action_eff:
            action_eff[key] = {"attempts": 0, "successes": 0, "surfaces": []}
        eff = action_eff[key]
        eff["attempts"] = eff.get("attempts", 0) + 1
        if accepted:
            eff["successes"] = eff.get("successes", 0) + 1
        if surface not in eff.get("surfaces", []):
            eff.setdefault("surfaces", []).append(surface)

    # Track failure patterns
    if not accepted:
        patterns = policy.setdefault("failure_patterns", {})
        pattern_key = f"{surface}:{reason}"
        patterns[pattern_key] = patterns.get(pattern_key, 0) + 1

    save_learned_policy(policy, root=root)
    return policy


def suggest_repair_strategy(surface: str, reason: str, *, root=None) -> Dict[str, Any]:
    """Suggest the best repair strategy for a given surface and reason."""
    policy = load_learned_policy(root)
    strategies = policy.get("surface_strategies", {})
    surface_key = f"{surface}:{reason}"
    strat = strategies.get(surface_key, {})

    if strat:
        success_rate = strat.get("successes", 0) / max(1, strat.get("attempts", 1))
        best_actions = sorted(
            strat.get("actions", {}).items(),
            key=lambda kv: kv[1].get("successes", 0) / max(1, kv[1].get("attempts", 1)),
            reverse=True,
        )
    else:
        success_rate = 0.0
        best_actions = []

    # Also look at action effectiveness across all surfaces
    action_eff = policy.get("action_effectiveness", {})
    global_best = sorted(
        [(k, v) for k, v in action_eff.items() if surface in v.get("surfaces", [])],
        key=lambda kv: kv[1].get("successes", 0) / max(1, kv[1].get("attempts", 1)),
        reverse=True,
    )[:3]

    return {
        "kind": "repair-strategy-suggestion",
        "surface": surface,
        "reason": reason,
        "known": bool(strat),
        "historical_success_rate": round(success_rate, 4),
        "suggested_actions": [k for k, _ in best_actions[:3]],
        "global_best_actions": [k for k, _ in global_best],
        "stored_prose": 0,
    }


def learned_policy_card(*, root=None) -> Dict[str, Any]:
    """Operator card showing what the system has learned."""
    policy = load_learned_policy(root)
    strategies = policy.get("surface_strategies", {})
    action_eff = policy.get("action_effectiveness", {})
    patterns = policy.get("failure_patterns", {})

    total_attempts = sum(s.get("attempts", 0) for s in strategies.values())
    total_successes = sum(s.get("successes", 0) for s in strategies.values())

    top_actions = sorted(
        action_eff.items(),
        key=lambda kv: kv[1].get("successes", 0) / max(1, kv[1].get("attempts", 1)),
        reverse=True,
    )[:5]

    top_failures = sorted(patterns.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "kind": "learned-policy-card",
        "total_attempts": total_attempts,
        "total_successes": total_successes,
        "overall_success_rate": round(total_successes / max(1, total_attempts), 4),
        "strategies_learned": len(strategies),
        "actions_tracked": len(action_eff),
        "top_actions": [{"action": k, "rate": round(v.get("successes", 0) / max(1, v.get("attempts", 1)), 4)} for k, v in top_actions],
        "top_failure_patterns": [{"pattern": k, "count": v} for k, v in top_failures],
        "stored_prose": 0,
    }
