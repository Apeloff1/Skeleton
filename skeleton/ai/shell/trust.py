"""Advisory trust profiles derived from observed model behavior."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from skeleton.shells.ai.calibration import AICalibration


@dataclass(frozen=True)
class ModelTrustProfile:
    model_id: str
    observations: int
    success_rate: float
    verified_rate: float
    average_latency_ms: float
    calibration_error: float
    trust_score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "observations": self.observations,
            "success_rate": self.success_rate,
            "verified_rate": self.verified_rate,
            "average_latency_ms": self.average_latency_ms,
            "calibration_error": self.calibration_error,
            "trust_score": self.trust_score,
        }


class ModelTrustRegistry:
    """Trust is routing advice only and never grants shell capabilities."""

    def __init__(self, calibration: AICalibration) -> None:
        self.calibration = calibration
        self._verified: dict[str, tuple[int, int]] = {}
        self._lock = threading.RLock()

    def record_verification(self, model_id: str, *, verified: bool) -> None:
        if not model_id or len(model_id) > 256:
            raise ValueError("invalid model_id")
        with self._lock:
            total, passed = self._verified.get(model_id, (0, 0))
            self._verified[model_id] = (total + 1, passed + int(bool(verified)))

    def profile(self, model_id: str) -> ModelTrustProfile:
        calibration = self.calibration.get(model_id)
        with self._lock:
            total, passed = self._verified.get(model_id, (0, 0))
        verified_rate = passed / total if total else 0.5
        trust = (
            calibration.predicted_success * 0.45
            + verified_rate * 0.35
            + max(0.0, 1.0 - calibration.confidence_error) * 0.20
        )
        if calibration.attempts < 5:
            trust *= 0.75
        return ModelTrustProfile(
            model_id=model_id,
            observations=calibration.attempts,
            success_rate=calibration.predicted_success,
            verified_rate=verified_rate,
            average_latency_ms=calibration.avg_latency_ms,
            calibration_error=calibration.confidence_error,
            trust_score=max(0.0, min(1.0, trust)),
        )
