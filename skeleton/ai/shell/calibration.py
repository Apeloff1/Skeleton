"""Online empirical calibration for model and command shell outcomes."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading


@dataclass(frozen=True)
class CalibrationSnapshot:
    key: str
    attempts: int
    successes: int
    verified_successes: int
    avg_latency_ms: float
    predicted_success: float
    confidence_error: float

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "attempts": self.attempts,
            "successes": self.successes,
            "verified_successes": self.verified_successes,
            "avg_latency_ms": self.avg_latency_ms,
            "predicted_success": self.predicted_success,
            "confidence_error": self.confidence_error,
        }


@dataclass
class _MutableCalibration:
    attempts: int = 0
    successes: int = 0
    verified_successes: int = 0
    latency_total_ms: float = 0.0
    confidence_error_total: float = 0.0


class AICalibration:
    """Beta-smoothed success calibration with bounded key cardinality."""

    def __init__(self, *, max_keys: int = 4096) -> None:
        if max_keys <= 0:
            raise ValueError("max_keys must be positive")
        self.max_keys = max_keys
        self._items: dict[str, _MutableCalibration] = {}
        self._lock = threading.RLock()

    def record(
        self,
        key: str,
        *,
        predicted_confidence: float,
        success: bool,
        verified: bool,
        latency_ms: float,
    ) -> CalibrationSnapshot:
        if not key or len(key) > 256:
            raise ValueError("invalid calibration key")
        if not 0.0 <= predicted_confidence <= 1.0:
            raise ValueError("predicted_confidence out of range")
        if latency_ms < 0 or not math.isfinite(latency_ms):
            raise ValueError("latency_ms must be finite and non-negative")
        with self._lock:
            state = self._items.get(key)
            if state is None:
                if len(self._items) >= self.max_keys:
                    raise RuntimeError("calibration key capacity exhausted")
                state = _MutableCalibration()
                self._items[key] = state
            state.attempts += 1
            state.successes += int(bool(success))
            state.verified_successes += int(bool(success and verified))
            state.latency_total_ms += latency_ms
            state.confidence_error_total += abs(predicted_confidence - float(bool(success)))
            return self.get(key)

    def get(self, key: str) -> CalibrationSnapshot:
        with self._lock:
            state = self._items[key]
            predicted = (state.successes + 1.0) / (state.attempts + 2.0)
            return CalibrationSnapshot(
                key=key,
                attempts=state.attempts,
                successes=state.successes,
                verified_successes=state.verified_successes,
                avg_latency_ms=state.latency_total_ms / state.attempts,
                predicted_success=predicted,
                confidence_error=state.confidence_error_total / state.attempts,
            )

    def snapshot(self) -> tuple[CalibrationSnapshot, ...]:
        with self._lock:
            return tuple(self.get(key) for key in sorted(self._items))
