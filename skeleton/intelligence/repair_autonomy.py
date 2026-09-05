"""Multi-pass repair autonomy engine.

This module provides the orchestration layer that can attempt multiple
repair passes on a surface, learn from prior attempts, and decide when
to stop. It works with all existing repair scaffolds.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from skeleton.organism.policy_enforcement import repair_enabled_for, threshold_for
from skeleton.organism.quality_state import append_repair, load_quality


@dataclass
class RepairAttempt:
    """One repair pass record."""
    pass_n: int
    surface: str
    before_score: float
    after_score: float
    actions: List[Dict[str, Any]]
    accepted: bool
    reason: str
    at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_n": self.pass_n,
            "surface": self.surface,
            "before_score": round(self.before_score, 4),
            "after_score": round(self.after_score, 4),
            "delta": round(self.after_score - self.before_score, 4),
            "actions": self.actions,
            "accepted": self.accepted,
            "reason": self.reason,
            "at": self.at,
        }


@dataclass
class RepairSession:
    """A full multi-pass repair session for one surface."""
    surface: str
    target_id: str
    attempts: List[RepairAttempt] = field(default_factory=list)
    status: str = "open"
    final_accepted: bool = False
    final_score: float = 0.0
    at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "target_id": self.target_id,
            "attempts": [a.to_dict() for a in self.attempts],
            "status": self.status,
            "final_accepted": self.final_accepted,
            "final_score": round(self.final_score, 4),
            "pass_count": len(self.attempts),
            "at": self.at,
        }


def _repair_ledger_path(root=None) -> Path:
    from skeleton.organism.paths import organism_dir
    return organism_dir(root) / "repair_sessions.jsonl"


def _load_sessions(root=None, limit: int = 64) -> List[Dict[str, Any]]:
    path = _repair_ledger_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _append_session(session: RepairSession, root=None) -> None:
    path = _repair_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(session.to_dict(), sort_keys=True, default=str) + "\n")
    # Trim if needed
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 256:
            path.write_text("\n".join(lines[-256:]) + "\n", encoding="utf-8")


def _learned_max_passes(surface: str, root=None, default: int = 3) -> int:
    """Learn from history: if prior sessions on this surface never
    improved after pass N, cap future sessions at N+1."""
    sessions = _load_sessions(root=root, limit=64)
    surface_sessions = [s for s in sessions if s.get("surface") == surface and s.get("attempts")]
    if not surface_sessions:
        return default
    # Find the pass where most improvement happened
    best_pass_for_improvement = 1
    for sess in surface_sessions[-8:]:
        attempts = sess.get("attempts", [])
        best_delta = 0.0
        best_n = 1
        for i, a in enumerate(attempts):
            delta = float(a.get("delta") or 0)
            if delta > best_delta:
                best_delta = delta
                best_n = i + 1
        if best_n > best_pass_for_improvement:
            best_pass_for_improvement = best_n
    # Cap: if we never improved after pass 2, don't go beyond 3
    cap = best_pass_for_improvement + 1
    return min(cap, default)


def _should_stop(session: RepairSession, max_passes: int) -> bool:
    """Stop conditions for multi-pass repair."""
    if len(session.attempts) >= max_passes:
        return True
    if not session.attempts:
        return False
    last = session.attempts[-1]
    if last.accepted:
        return True
    # If last pass made no improvement, stop
    if len(session.attempts) >= 2:
        prev = session.attempts[-2]
        if last.after_score <= prev.after_score:
            return True
    # If score is stuck below threshold with diminishing returns
    if len(session.attempts) >= 2:
        deltas = [a.after_score - a.before_score for a in session.attempts[-2:]]
        if all(d <= 0.01 for d in deltas):
            return True
    return False


def run_multi_pass(
    surface: str,
    target_id: str,
    repair_fn: Callable[..., Dict[str, Any]],
    *fn_args,
    root=None,
    max_passes: int = 3,
    **fn_kwargs,
) -> RepairSession:
    """Run a repair function up to max_passes times, stopping early
    if accepted or if no improvement is being made.

    Args:
        surface: the surface being repaired (forge, plan, npc, etc.)
        target_id: an identifier for the target (file path, spec id, etc.)
        repair_fn: the repair function to call (e.g. attempt_repair)
        *fn_args, **fn_kwargs: passed through to repair_fn

    Returns:
        A RepairSession with all attempts recorded.
    """
    if not repair_enabled_for(surface, root=root):
        session = RepairSession(surface=surface, target_id=target_id, status="blocked", final_accepted=False)
        _append_session(session, root=root)
        return session

    learned_cap = _learned_max_passes(surface, root=root, default=max_passes)
    max_passes = min(max_passes, learned_cap)

    session = RepairSession(surface=surface, target_id=target_id)
    current_input = fn_kwargs.copy()

    for pass_n in range(1, max_passes + 1):
        result = repair_fn(*fn_args, **current_input, root=root)
        before_score = float((result.get("before") or {}).get("score") or 0.0)
        after_score = float((result.get("after") or {}).get("score") or before_score)
        attempt = RepairAttempt(
            pass_n=pass_n,
            surface=surface,
            before_score=before_score,
            after_score=after_score,
            actions=list(result.get("actions") or []),
            accepted=bool(result.get("ok") or result.get("accepted")),
            reason=str(result.get("reason") or "unknown"),
        )
        session.attempts.append(attempt)
        session.final_accepted = attempt.accepted
        session.final_score = attempt.after_score

        # Persist each attempt as a repair record too
        append_repair({
            **result,
            "surface": surface,
            "pass_n": pass_n,
            "multi_pass": True,
        }, root=root)

        if _should_stop(session, max_passes):
            break

        # Feed forward: if repair returned modified output, use it next pass
        if "files" in result:
            current_input["files"] = result["files"]
        if "plan" in result:
            current_input["plan"] = result["plan"]
        if "spec" in result:
            current_input["spec"] = result["spec"]
        if "tree" in result:
            current_input["tree"] = result["tree"]

    session.status = "accepted" if session.final_accepted else "exhausted"
    _append_session(session, root=root)
    return session


def repair_session_card(surface: str = "", *, root=None, limit: int = 8) -> Dict[str, Any]:
    """Operator card showing recent repair sessions."""
    sessions = _load_sessions(root=root, limit=limit * 2)
    if surface:
        sessions = [s for s in sessions if s.get("surface") == surface]
    sessions = sessions[-limit:]
    total = len(sessions)
    accepted = sum(1 for s in sessions if s.get("final_accepted"))
    avg_passes = sum(s.get("pass_count", 0) for s in sessions) / max(1, total)
    return {
        "kind": "repair-session-card",
        "surface": surface or "all",
        "total_sessions": total,
        "accepted_sessions": accepted,
        "exhausted_sessions": total - accepted,
        "avg_passes": round(avg_passes, 2),
        "sessions": sessions,
        "stored_prose": 0,
    }


def repair_effectiveness(surface: str = "", *, root=None) -> Dict[str, Any]:
    """Compute repair effectiveness metrics from session history."""
    sessions = _load_sessions(root=root, limit=128)
    if surface:
        sessions = [s for s in sessions if s.get("surface") == surface]
    if not sessions:
        return {"kind": "repair-effectiveness", "surface": surface or "all", "n": 0, "success_rate": 0.0, "avg_improvement": 0.0, "best_pass": 0, "stored_prose": 0}
    success_rate = sum(1 for s in sessions if s.get("final_accepted")) / len(sessions)
    improvements = []
    best_pass_counts: Dict[int, int] = {}
    for sess in sessions:
        attempts = sess.get("attempts", [])
        if attempts:
            first = attempts[0]
            last = attempts[-1]
            improvement = float(last.get("after_score") or 0) - float(first.get("before_score") or 0)
            improvements.append(improvement)
            best = max(range(len(attempts)), key=lambda i: float(attempts[i].get("after_score") or 0))
            best_pass_counts[best + 1] = best_pass_counts.get(best + 1, 0) + 1
    avg_improvement = sum(improvements) / max(1, len(improvements))
    best_pass = max(best_pass_counts, key=best_pass_counts.get) if best_pass_counts else 1
    return {
        "kind": "repair-effectiveness",
        "surface": surface or "all",
        "n": len(sessions),
        "success_rate": round(success_rate, 4),
        "avg_improvement": round(avg_improvement, 4),
        "best_pass": best_pass,
        "pass_distribution": best_pass_counts,
        "stored_prose": 0,
    }
