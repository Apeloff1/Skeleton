from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class EpistemicExecutionGate:
    """Deterministically admit only execution-ready council-reviewed tasks.

    The model supplies structured reasoning evidence; this gate does not call a
    model. It verifies that the proposal is falsifiable, has an explicit output,
    includes failure analysis, and clears a configurable confidence floor.
    Unreviewed overflow tasks are left unchanged so the council budget remains a
    reasoning-depth control rather than an accidental workload-deletion switch.
    """

    enabled_env: str = "SHIFT_EPISTEMIC_GATE"
    min_confidence_env: str = "SHIFT_EPISTEMIC_MIN_CONFIDENCE"
    max_evidence_gaps_env: str = "SHIFT_EPISTEMIC_MAX_GAPS"
    default_min_confidence: int = 60
    default_max_evidence_gaps: int = 4

    def enabled(self) -> bool:
        raw = os.getenv(self.enabled_env, "1").strip().casefold()
        return raw not in {"0", "false", "no", "off"}

    def min_confidence(self) -> int:
        return self._env_int(self.min_confidence_env, self.default_min_confidence, 0, 100)

    def max_evidence_gaps(self) -> int:
        return self._env_int(self.max_evidence_gaps_env, self.default_max_evidence_gaps, 0, 16)

    def filter_tasks(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not tasks or not self.enabled():
            return [dict(task) for task in tasks]

        accepted: list[dict[str, Any]] = []
        for raw in tasks:
            task = dict(raw)
            council = task.get("_planning_council")
            if not isinstance(council, Mapping):
                accepted.append(task)
                continue
            ready, evidence = self._evaluate(task, council)
            if not ready:
                continue
            task["_epistemic_gate"] = evidence
            accepted.append(task)
        return accepted

    def _evaluate(
        self,
        task: Mapping[str, Any],
        council: Mapping[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        confidence = self._int(council.get("confidence"), 0)
        assumptions = self._strings(council.get("assumptions"), limit=12)
        failure_modes = self._strings(council.get("failure_modes"), limit=12)
        success_metrics = self._strings(council.get("success_metrics"), limit=12)
        evidence_gaps = self._strings(council.get("evidence_gaps"), limit=12)
        validation = self._strings(task.get("validation"), limit=24)
        expected_output = str(task.get("expected_output", "")).strip()

        checks = {
            "confidence": confidence >= self.min_confidence(),
            "expected_output": bool(expected_output),
            "validation": bool(validation),
            "failure_analysis": bool(failure_modes),
            "falsifiable_success": bool(success_metrics),
            "evidence_gap_budget": len(evidence_gaps) <= self.max_evidence_gaps(),
        }
        ready = all(checks.values())
        evidence = {
            "version": 1,
            "status": "ready" if ready else "blocked",
            "confidence": confidence,
            "confidence_floor": self.min_confidence(),
            "checks": checks,
            "assumption_count": len(assumptions),
            "failure_mode_count": len(failure_modes),
            "success_metric_count": len(success_metrics),
            "evidence_gap_count": len(evidence_gaps),
        }
        return ready, evidence

    @staticmethod
    def _strings(value: Any, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:1200] for item in value[:limit] if str(item).strip()]

    @staticmethod
    def _int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _env_int(cls, name: str, default: int, low: int, high: int) -> int:
        raw = os.getenv(name, "").strip()
        value = cls._int(raw, default) if raw else default
        return max(low, min(high, value))
