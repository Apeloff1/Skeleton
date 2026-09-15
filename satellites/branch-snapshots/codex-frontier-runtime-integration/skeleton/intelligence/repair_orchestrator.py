"""Repair orchestrator — unified entry point for all repair operations.

Provides a single surface for operators and automation to request
repairs, with multi-pass support, telemetry, learned policies,
and policy enforcement all wired together.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Mapping, Optional

from skeleton.intelligence.learned_repair import learn_from_repair, suggest_repair_strategy
from skeleton.intelligence.repair_autonomy import RepairSession, run_multi_pass
from skeleton.intelligence.repair_telemetry import capture_telemetry
from skeleton.organism.policy_enforcement import repair_enabled_for, repair_gate


REPAIR_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {}


def register_repair(surface: str, fn: Callable[..., Dict[str, Any]]) -> None:
    """Register a repair function for a surface."""
    REPAIR_REGISTRY[surface] = fn


def _get_repair_fn(surface: str) -> Optional[Callable[..., Dict[str, Any]]]:
    return REPAIR_REGISTRY.get(surface)


def orchestrated_repair(
    surface: str,
    target_id: str,
    *fn_args,
    root=None,
    max_passes: int = 3,
    use_telemetry: bool = True,
    use_learned: bool = True,
    **fn_kwargs,
) -> Dict[str, Any]:
    """Run a repair with full orchestration: multi-pass, telemetry,
    learned policy, and policy gating.

    Args:
        surface: the surface to repair
        target_id: identifier for the repair target
        *fn_args, **fn_kwargs: passed to the repair function
        max_passes: maximum repair passes
        use_telemetry: whether to capture telemetry
        use_learned: whether to update/learn from results

    Returns:
        A dict with the session, telemetry, and strategy info.
    """
    gate = repair_gate(surface, root=root)
    if not gate["repair_allowed"]:
        return {
            "kind": "repair-orchestrator-result",
            "surface": surface,
            "target_id": target_id,
            "status": "blocked",
            "reason": gate["reason"],
            "session": None,
            "telemetry": [],
            "strategy": None,
            "stored_prose": 0,
        }

    repair_fn = _get_repair_fn(surface)
    if repair_fn is None:
        return {
            "kind": "repair-orchestrator-result",
            "surface": surface,
            "target_id": target_id,
            "status": "unknown-surface",
            "reason": f"no repair function registered for {surface}",
            "session": None,
            "telemetry": [],
            "strategy": None,
            "stored_prose": 0,
        }

    # Get strategy suggestion before repair
    strategy = None
    if use_learned:
        # We need the reason — try to get it from the first verification
        strategy = suggest_repair_strategy(surface, "unknown", root=root)

    # Run multi-pass repair
    session = run_multi_pass(
        surface=surface,
        target_id=target_id,
        repair_fn=repair_fn,
        *fn_args,
        root=root,
        max_passes=max_passes,
        **fn_kwargs,
    )

    # Capture telemetry for each attempt
    telemetry_records = []
    if use_telemetry:
        for attempt in session.attempts:
            # Reconstruct a result-like dict for telemetry
            result = {
                "before": {"score": attempt.before_score},
                "after": {"score": attempt.after_score},
                "actions": attempt.actions,
                "ok": attempt.accepted,
                "reason": attempt.reason,
            }
            telem = capture_telemetry(
                surface=surface,
                pass_n=attempt.pass_n,
                start_at=attempt.at - 1,  # approximate
                result=result,
                root=root,
            )
            telemetry_records.append(telem.to_dict())

    # Learn from the final result
    if use_learned and session.attempts:
        final = session.attempts[-1]
        final_result = {
            "surface": surface,
            "ok": final.accepted,
            "reason": final.reason,
            "actions": final.actions,
            "before": {"score": final.before_score},
            "after": {"score": final.after_score},
        }
        learn_from_repair(final_result, root=root)

    return {
        "kind": "repair-orchestrator-result",
        "surface": surface,
        "target_id": target_id,
        "status": session.status,
        "final_accepted": session.final_accepted,
        "final_score": round(session.final_score, 4),
        "pass_count": len(session.attempts),
        "session": session.to_dict(),
        "telemetry": telemetry_records,
        "strategy": strategy,
        "stored_prose": 0,
    }


def repair_orchestrator_card(*, root=None) -> Dict[str, Any]:
    """Operator card showing orchestrator status."""
    from skeleton.intelligence.learned_repair import learned_policy_card
    from skeleton.intelligence.repair_autonomy import repair_effectiveness, repair_session_card
    from skeleton.intelligence.repair_telemetry import telemetry_card

    return {
        "kind": "repair-orchestrator-card",
        "registered_surfaces": list(REPAIR_REGISTRY.keys()),
        "sessions": repair_session_card(root=root),
        "effectiveness": repair_effectiveness(root=root),
        "telemetry": telemetry_card(root=root),
        "learned": learned_policy_card(root=root),
        "stored_prose": 0,
    }
