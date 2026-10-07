"""Anomaly detector — statistical outlier detection for telemetry.

Provides real-time anomaly detection using z-score, IQR, and
exponential moving average methods. Integrates with the dashboard
for automatic alert firing when anomalies are detected.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AnomalyConfig:
    method: str = "zscore"
    zscore_threshold: float = 3.0
    iqr_multiplier: float = 1.5
    ema_alpha: float = 0.3
    ema_threshold_multiplier: float = 3.0
    window_size: int = 100


class AnomalyDetector:
    """Statistical anomaly detector with multiple methods."""

    def __init__(self, metric_name: str, config: Optional[AnomalyConfig] = None):
        self.metric_name = metric_name
        self.config = config or AnomalyConfig()
        self._window: List[float] = []
        self._ema = 0.0
        self._ema_var = 0.0
        self._anomalies: List[Dict[str, Any]] = []

    def feed(self, value: float) -> Optional[Dict[str, Any]]:
        self._window.append(value)
        if len(self._window) > self.config.window_size:
            self._window.pop(0)

        if len(self._window) < 2:
            self._ema = value
            return None

        is_anomaly = False
        score = 0.0

        if self.config.method == "zscore":
            mean = sum(self._window) / len(self._window)
            variance = sum((x - mean) ** 2 for x in self._window) / len(self._window)
            std = math.sqrt(variance) if variance > 0 else 1e-9
            score = abs(value - mean) / std
            is_anomaly = score > self.config.zscore_threshold

        elif self.config.method == "iqr":
            sorted_window = sorted(self._window)
            n = len(sorted_window)
            q1 = sorted_window[n // 4]
            q3 = sorted_window[(3 * n) // 4]
            iqr = q3 - q1
            lower = q1 - self.config.iqr_multiplier * iqr
            upper = q3 + self.config.iqr_multiplier * iqr
            is_anomaly = value < lower or value > upper
            score = max(abs(value - lower), abs(value - upper)) / max(iqr, 1e-9)

        elif self.config.method == "ema":
            delta = value - self._ema
            self._ema += self.config.ema_alpha * delta
            self._ema_var = (1 - self.config.ema_alpha) * self._ema_var + self.config.ema_alpha * (delta ** 2)
            threshold = self.config.ema_threshold_multiplier * math.sqrt(self._ema_var)
            score = abs(delta)
            is_anomaly = score > threshold

        if is_anomaly:
            anomaly = {
                "timestamp_ns": time.time_ns(),
                "metric": self.metric_name,
                "value": value,
                "score": round(score, 3),
                "method": self.config.method,
                "window_size": len(self._window),
            }
            self._anomalies.append(anomaly)
            return anomaly
        return None

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "anomaly-detector-card",
            "metric": self.metric_name,
            "method": self.config.method,
            "window_size": len(self._window),
            "anomalies_detected": len(self._anomalies),
            "recent_anomalies": self._anomalies[-5:],
        }
