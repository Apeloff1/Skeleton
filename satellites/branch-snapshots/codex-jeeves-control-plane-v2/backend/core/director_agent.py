"""
core/director_agent.py — The Director Agent (2026 SOTA Manifest, Segment 2 / Items 11-20).

The missing brain: instead of calling forges in a fixed linear sequence, the
DirectorAgent maintains persistent per-build world state, PLANS each stage
(ordered sub-forges + dependencies), and REFLECTS on quality reports to decide
which downstream stages must be re-forged and with what delta instruction.

Design constraints:
  * Pure logic — this module NEVER imports routes.game_kb (avoids circular
    imports). Wiring lives in game_kb.py (facade) and routes/director.py.
  * Non-blocking — all methods are cheap/sync except async ledger writes; safe
    to call from inside an asyncio background task.
  * Decisions are logged to build_ledger for later analysis (Item 15).
"""
from __future__ import annotations

import time
from typing import Any

from core import build_ledger

# ── Exhaustive directive integration (Item 19) ───────────────────────────────
# Mirror of routes.game_kb._EXHAUSTIVE_DIRECTIVE intent, referenced in every
# Director-issued delta so re-forges stay exhaustive (options[] + edge cases).
EXHAUSTIVE_HINT = (
    "Remain EXHAUSTIVE: regenerate the full 'options' array (5+ areas, 2-4 "
    "alternatives each, one recommended=true) and cover edge cases / failure modes."
)

# ── Stage dependency graph ────────────────────────────────────────────────────
# Downstream = stages made STALE when this stage (re)generates. Kept in sync
# with game_kb._DOWNSTREAM (artifact-level) but expressed at STAGE level so the
# Director can cascade design choices. Item 18: physics → tileset + cinematics.
STAGE_DOWNSTREAM: dict[str, list[str]] = {
    "questionnaire": ["spec"],
    "spec":          ["world", "mechanics", "narrative", "physics", "procedural",
                      "tileset", "assets", "qa", "build", "cinematics", "launch"],
    "world":         ["narrative", "procedural", "assets", "qa", "build"],
    "narrative":     ["qa", "build"],
    "mechanics":     ["physics", "procedural", "qa", "build"],
    "physics":       ["procedural", "tileset", "cinematics", "qa", "build"],
    "procedural":    ["tileset", "assets", "qa", "build"],
    "tileset":       ["assets", "qa", "build"],
    "assets":        ["build"],
    "qa":            [],
    "build":         ["cinematics", "launch"],
    "cinematics":    ["launch"],
    "launch":        [],
}

# Upstream prerequisites (inverse of downstream), used to order sub-forges.
STAGE_UPSTREAM: dict[str, list[str]] = {}
for _s, _downs in STAGE_DOWNSTREAM.items():
    for _d in _downs:
        STAGE_UPSTREAM.setdefault(_d, []).append(_s)

MIN_QUALITY = 95


class DirectorAgent:
    """Persistent orchestrator. Owns build_id → world state (Item 11-12)."""

    def __init__(self) -> None:
        # In-memory fast cache; the durable record lives in build_ledger.
        self._state: dict[str, dict[str, Any]] = {}

    # ── state helpers ─────────────────────────────────────────────────────────
    def _st(self, build_id: str) -> dict[str, Any]:
        return self._state.setdefault(build_id, {
            "build_id": build_id,
            "current_stage": None,
            "artifact_history": [],   # [{stage, artifact, score, at}]
            "quality_scores": {},     # {stage: score}
            "revisit_queue": [],      # stages the Director wants re-forged
            "plans": 0,
            "reflections": 0,
        })

    # ── Item 12: plan_stage ────────────────────────────────────────────────────
    def plan_stage(self, build_id: str, stage: str) -> dict[str, Any]:
        """Return an ordered plan for a stage: its prerequisite sub-forges (that
        are not yet satisfied), the stage itself, and the downstream cascade."""
        st = self._st(build_id)
        st["current_stage"] = stage
        st["plans"] += 1

        done = set(st["quality_scores"].keys())
        upstream = [u for u in STAGE_UPSTREAM.get(stage, []) if u not in done]
        sub_forges = [*upstream, stage]  # prerequisites first, then the target
        downstream = STAGE_DOWNSTREAM.get(stage, [])

        plan = {
            "stage": stage,
            "sub_forges": sub_forges,
            "depends_on": STAGE_UPSTREAM.get(stage, []),
            "downstream": downstream,
            "cascade_on_change": downstream,
        }
        try:
            build_ledger.log(build_id, "director.plan", plan)
        except Exception:
            pass
        return plan

    # ── record a completed forge (Item 14 facade calls this) ────────────────────
    def record_forge(self, build_id: str, stage: str, artifact: str | None,
                     score: int | None) -> None:
        st = self._st(build_id)
        entry = {"stage": stage, "artifact": artifact, "score": score, "at": time.time()}
        st["artifact_history"].append(entry)
        if score is not None:
            st["quality_scores"][stage] = score
        # drop from revisit queue if it now passes
        if score is not None and score >= MIN_QUALITY and stage in st["revisit_queue"]:
            st["revisit_queue"].remove(stage)
        try:
            build_ledger.log(build_id, "director.forge", entry)
        except Exception:
            pass

    # ── Item 13: reflect_on_quality ─────────────────────────────────────────────
    def reflect_on_quality(self, build_id: str, quality_report: dict[str, Any]) -> dict[str, Any]:
        """Given a stage's quality report, decide the delta instruction and which
        downstream stages must be revisited. Returns {delta_instruction,
        stages_to_revisit, passed}."""
        st = self._st(build_id)
        st["reflections"] += 1

        stage = quality_report.get("stage") or st.get("current_stage") or ""
        score = int(quality_report.get("score", 0) or 0)
        feedback = (quality_report.get("feedback") or "").strip()
        passed = score >= MIN_QUALITY

        if passed:
            result = {"passed": True, "delta_instruction": "", "stages_to_revisit": []}
        else:
            # Only the affected stage + its downstream cascade need attention.
            revisit = [stage, *STAGE_DOWNSTREAM.get(stage, [])] if stage else []
            delta = (
                f"Stage '{stage}' scored {score}/100 (need >= {MIN_QUALITY}). "
                f"Auditor feedback: {feedback or 'raise every quality factor'}. "
                f"Regenerate ONLY the weak subsystems and re-satisfy downstream "
                f"dependencies ({', '.join(STAGE_DOWNSTREAM.get(stage, [])) or 'none'}). "
                f"{EXHAUSTIVE_HINT}"
            )
            st["revisit_queue"] = sorted(set(st["revisit_queue"]) | set(revisit))
            result = {"passed": False, "delta_instruction": delta, "stages_to_revisit": revisit}

        try:
            build_ledger.log(build_id, "director.reflect",
                             {"stage": stage, "score": score, **result})
        except Exception:
            pass
        return result

    # ── Item 16: state for debugging ────────────────────────────────────────────
    def get_state(self, build_id: str) -> dict[str, Any]:
        st = dict(self._st(build_id))
        try:
            st["ledger_context"] = build_ledger.get_context(build_id)
        except Exception:
            st["ledger_context"] = {}
        return st


# Module-level singleton (Item 11 — persistent across requests within a process).
director = DirectorAgent()
