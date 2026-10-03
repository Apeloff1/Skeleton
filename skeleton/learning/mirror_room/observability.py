"""Evidence-only live projection for Mirror Room campaigns.

The Observatory is downstream of learning. It receives immutable attempt and
campaign receipts and converts them into a compact user-facing read model.
Nothing in this module can generate candidates, change evaluation evidence,
promote a candidate, or mutate production behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import time
from typing import Any, Mapping

from .contracts import MirrorCandidate, MirrorRoomError, _digest


ATTEMPTS_REQUIRED = 100
_DETAIL_HINTS = (
    "detail",
    "specificity",
    "completeness",
    "information_density",
    "structure",
    "depth",
)


def _mean(values: tuple[float, ...]) -> float:
    return 0.0 if not values else sum(values) / len(values)


@dataclass(frozen=True, slots=True)
class MirrorMetricView:
    metric_id: str
    baseline_score: float
    candidate_score: float
    delta: float

    def payload(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "baseline_score": self.baseline_score,
            "candidate_score": self.candidate_score,
            "delta": self.delta,
        }


def _metric_views(receipt: Any) -> tuple[MirrorMetricView, ...]:
    rows = tuple(receipt.validation_report.metric_comparisons)
    content_rows = tuple(
        row for row in rows
        if str(row.metric_id).startswith("content.")
    )
    selected = content_rows or rows
    return tuple(
        MirrorMetricView(
            metric_id=str(row.metric_id),
            baseline_score=float(row.baseline_mean),
            candidate_score=float(row.candidate_mean),
            delta=float(row.candidate_mean) - float(row.baseline_mean),
        )
        for row in selected
    )


def _quality_pair(
    metrics: tuple[MirrorMetricView, ...],
) -> tuple[float, float]:
    return (
        _mean(tuple(item.baseline_score for item in metrics)),
        _mean(tuple(item.candidate_score for item in metrics)),
    )


def _detail_pair(
    metrics: tuple[MirrorMetricView, ...],
) -> tuple[float, float]:
    detail = tuple(
        item for item in metrics
        if any(hint in item.metric_id.lower() for hint in _DETAIL_HINTS)
    )
    chosen = detail or metrics
    return (
        _mean(tuple(item.baseline_score for item in chosen)),
        _mean(tuple(item.candidate_score for item in chosen)),
    )


@dataclass(frozen=True, slots=True)
class MirrorAttemptView:
    attempt: int
    accepted: bool
    baseline_before_id: str
    candidate_id: str
    baseline_after_id: str
    baseline_quality_score: float
    candidate_quality_score: float
    effective_quality_score: float
    baseline_detail_score: float
    candidate_detail_score: float
    effective_detail_score: float
    weighted_gain: float
    required_weighted_gain: float
    required_strict_metric_gain: float
    retained_scenarios: int
    rejection_reasons: tuple[str, ...]
    dimensions: tuple[MirrorMetricView, ...]

    @classmethod
    def from_receipt(cls, receipt: Any) -> "MirrorAttemptView":
        metrics = _metric_views(receipt)
        base_quality, candidate_quality = _quality_pair(metrics)
        base_detail, candidate_detail = _detail_pair(metrics)
        accepted = bool(receipt.accepted)
        return cls(
            attempt=int(receipt.attempt),
            accepted=accepted,
            baseline_before_id=receipt.baseline_before.candidate_id,
            candidate_id=receipt.candidate.candidate_id,
            baseline_after_id=receipt.baseline_after.candidate_id,
            baseline_quality_score=base_quality,
            candidate_quality_score=candidate_quality,
            effective_quality_score=(
                candidate_quality if accepted else base_quality
            ),
            baseline_detail_score=base_detail,
            candidate_detail_score=candidate_detail,
            effective_detail_score=(
                candidate_detail if accepted else base_detail
            ),
            weighted_gain=float(
                receipt.validation_report.weighted_utility_delta
            ),
            required_weighted_gain=float(receipt.required_weighted_gain),
            required_strict_metric_gain=float(
                receipt.required_strict_metric_gain
            ),
            retained_scenarios=len(receipt.retention_scenario_digests),
            rejection_reasons=tuple(receipt.rejection_reasons),
            dimensions=metrics,
        )

    def payload(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "accepted": self.accepted,
            "baseline_before_id": self.baseline_before_id,
            "candidate_id": self.candidate_id,
            "baseline_after_id": self.baseline_after_id,
            "baseline_quality_score": self.baseline_quality_score,
            "candidate_quality_score": self.candidate_quality_score,
            "effective_quality_score": self.effective_quality_score,
            "baseline_detail_score": self.baseline_detail_score,
            "candidate_detail_score": self.candidate_detail_score,
            "effective_detail_score": self.effective_detail_score,
            "quality_delta": (
                self.candidate_quality_score
                - self.baseline_quality_score
            ),
            "detail_delta": (
                self.candidate_detail_score
                - self.baseline_detail_score
            ),
            "weighted_gain": self.weighted_gain,
            "required_weighted_gain": self.required_weighted_gain,
            "required_strict_metric_gain": self.required_strict_metric_gain,
            "retained_scenarios": self.retained_scenarios,
            "rejection_reasons": list(self.rejection_reasons),
            "dimensions": [
                item.payload() for item in self.dimensions
            ],
        }


class MirrorRoomObservatory:
    """Thread-safe read model for the live adversarial quality ratchet."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._version = 0
        self._run_id: str | None = None
        self._status = "idle"
        self._original_baseline: MirrorCandidate | None = None
        self._current_baseline: MirrorCandidate | None = None
        self._attempts: list[MirrorAttemptView] = []
        self._delivery_ready = False
        self._gauntlet_passed = False
        self._holdout_passed = False
        self._updated_at = time()

    def begin(self, *, run_id: str, baseline: MirrorCandidate) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise MirrorRoomError("observatory run_id must be non-empty")
        if not isinstance(baseline, MirrorCandidate):
            raise TypeError("baseline must be MirrorCandidate")
        with self._lock:
            self._version += 1
            self._run_id = run_id
            self._status = "running"
            self._original_baseline = baseline
            self._current_baseline = baseline
            self._attempts = []
            self._delivery_ready = False
            self._gauntlet_passed = False
            self._holdout_passed = False
            self._updated_at = time()

    def record_attempt(self, receipt: Any) -> None:
        view = MirrorAttemptView.from_receipt(receipt)
        with self._lock:
            if view.attempt != len(self._attempts) + 1:
                raise MirrorRoomError(
                    "observatory attempts must be contiguous"
                )
            self._attempts.append(view)
            self._current_baseline = receipt.baseline_after
            self._version += 1
            self._updated_at = time()

    def finish(self, campaign: Any) -> None:
        with self._lock:
            if self._run_id != campaign.run_id:
                raise MirrorRoomError("observatory campaign run mismatch")
            if len(self._attempts) != campaign.completed_attempts:
                raise MirrorRoomError(
                    "observatory attempt count does not match campaign"
                )
            self._current_baseline = campaign.final_baseline
            self._delivery_ready = bool(campaign.delivery_ready)
            self._gauntlet_passed = bool(
                campaign.gauntlet_report
                and campaign.gauntlet_report.passed
            )
            self._holdout_passed = bool(
                campaign.holdout_report
                and campaign.holdout_report.passed
            )
            if campaign.delivery_ready:
                self._status = "delivery-ready"
            elif campaign.completed_attempts == ATTEMPTS_REQUIRED:
                self._status = "complete-blocked"
            else:
                self._status = "partial"
            self._version += 1
            self._updated_at = time()

    def fail(self, *, run_id: str) -> None:
        with self._lock:
            if self._run_id == run_id:
                self._status = "failed"
                self._version += 1
                self._updated_at = time()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            attempts = tuple(self._attempts)
            last = attempts[-1] if attempts else None
            first = attempts[0] if attempts else None
            accepted = sum(int(item.accepted) for item in attempts)
            completed = len(attempts)
            original = self._original_baseline
            current = self._current_baseline
            start_quality = (
                None if first is None
                else first.baseline_quality_score
            )
            start_detail = (
                None if first is None
                else first.baseline_detail_score
            )
            current_quality = (
                None if last is None
                else last.effective_quality_score
            )
            current_detail = (
                None if last is None
                else last.effective_detail_score
            )
            payload: dict[str, object] = {
                "schema_version": 1,
                "version": self._version,
                "run_id": self._run_id,
                "status": self._status,
                "attempts_completed": completed,
                "attempts_required": ATTEMPTS_REQUIRED,
                "progress": completed / ATTEMPTS_REQUIRED,
                "accepted_upgrades": accepted,
                "original_baseline_id": (
                    None if original is None else original.candidate_id
                ),
                "current_baseline_id": (
                    None if current is None else current.candidate_id
                ),
                "start_quality_score": start_quality,
                "quality_score": current_quality,
                "quality_lift": (
                    None
                    if start_quality is None or current_quality is None
                    else current_quality - start_quality
                ),
                "start_detail_score": start_detail,
                "detail_score": current_detail,
                "detail_lift": (
                    None
                    if start_detail is None or current_detail is None
                    else current_detail - start_detail
                ),
                "current_weighted_gain": (
                    None if last is None else last.weighted_gain
                ),
                "required_weighted_gain": (
                    None if last is None else last.required_weighted_gain
                ),
                "required_strict_metric_gain": (
                    None
                    if last is None
                    else last.required_strict_metric_gain
                ),
                "retained_scenarios": (
                    0 if last is None else last.retained_scenarios
                ),
                "gauntlet_passed": self._gauntlet_passed,
                "holdout_passed": self._holdout_passed,
                "delivery_ready": self._delivery_ready,
                "accepted_baselines": [
                    item.baseline_after_id
                    for item in attempts
                    if item.accepted
                ],
                "attempts": [item.payload() for item in attempts],
                "updated_at": self._updated_at,
                "production_authority": False,
            }
            payload["digest"] = _digest(payload)
            return payload


_DEFAULT_OBSERVATORY = MirrorRoomObservatory()


def get_default_observatory() -> MirrorRoomObservatory:
    return _DEFAULT_OBSERVATORY


def mirror_room_file_tree() -> Mapping[str, object]:
    """Governed logical file tree for the landed Mirror Room product surface."""

    return {
        "name": "Mirror Room",
        "path": "mirror-room",
        "kind": "root",
        "children": [
            {
                "name": "Learning Engine",
                "path": "skeleton/learning/mirror_room",
                "kind": "engine",
                "children": [
                    {"name": "adversarial.py", "kind": "ratchet"},
                    {"name": "content_quality.py", "kind": "quality"},
                    {"name": "observability.py", "kind": "telemetry"},
                    {"name": "adaptation.py", "kind": "adaptation"},
                    {"name": "engine.py", "kind": "learning"},
                    {"name": "evaluation.py", "kind": "evaluation"},
                    {"name": "memory.py", "kind": "memory"},
                    {"name": "replay.py", "kind": "replay"},
                    {"name": "sandbox.py", "kind": "sandbox"},
                    {"name": "promotion.py", "kind": "promotion"},
                ],
            },
            {
                "name": "Governed AI Mirror",
                "path": "skeleton/ai/learning/mirror_room",
                "kind": "mirror",
            },
            {
                "name": "Read-only Observatory API",
                "path": "backend/routes/mirror_room.py",
                "kind": "api",
            },
            {
                "name": "Observatory UI",
                "path": "frontend/features/MirrorRoom",
                "kind": "ui",
                "children": [
                    {
                        "name": "MirrorRoomObservatory.tsx",
                        "kind": "screen",
                    },
                    {
                        "name": "types.ts",
                        "kind": "contracts",
                    },
                ],
            },
            {
                "name": "Observatory Route",
                "path": "frontend/app/mirror-room.tsx",
                "kind": "route",
            },
            {
                "name": "Focused Tests",
                "path": "skeleton/testing",
                "kind": "tests",
                "children": [
                    {
                        "name": "test_mirror_room_adversarial.py",
                        "kind": "ratchet-tests",
                    },
                    {
                        "name": "test_mirror_room_content_delivery.py",
                        "kind": "delivery-tests",
                    },
                    {
                        "name": "test_mirror_room_observability.py",
                        "kind": "observability-tests",
                    },
                ],
            },
            {
                "name": "Extension CI Gate",
                "path": ".github/workflows/mirror-room-extensions.yml",
                "kind": "ci",
            },
        ],
    }


__all__ = [
    "MirrorAttemptView",
    "MirrorMetricView",
    "MirrorRoomObservatory",
    "get_default_observatory",
    "mirror_room_file_tree",
]
