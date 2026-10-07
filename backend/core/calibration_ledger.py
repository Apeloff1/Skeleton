"""Tamper-evident calibration ledger for epistemic forecasts.

Calibration measures forecast reliability; it never promotes claims and never
counts as evidence. Metrics describe forecasting behavior only after outcomes are
resolved by empirical verification attestations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
from typing import Any

from core.file_lease import FileLease


CALIBRATION_VERSION = 1


class CalibrationIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Forecast:
    id: str
    claim: str
    probability: float
    forecaster: str
    context_sha256: str
    created_at: str
    outcome: bool | None = None
    resolved_at: str = ""
    resolution_attestation_sha256: str = ""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _probability(value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("probability must be finite and between 0 and 1")
    return number


def _sha256(value: str, *, field: str) -> str:
    value = str(value or "").lower().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be a 64-character sha256")
    return value


class CalibrationLedger:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "calibration-ledger.json"
        self._lease = FileLease(self.root / ".calibration.lock")
        with self._lease.acquire():
            if not self.path.exists(): self._write({})
            else: self._load()

    @staticmethod
    def _checksum(rows: dict[str, dict[str, Any]]) -> str:
        return _sha({"version": CALIBRATION_VERSION, "forecasts": rows})

    def _load(self) -> dict[str, dict[str, Any]]:
        try: env = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CalibrationIntegrityError("calibration ledger unreadable") from exc
        rows = env.get("forecasts"); checksum = env.get("sha256")
        if env.get("version") != CALIBRATION_VERSION:
            raise CalibrationIntegrityError("unsupported calibration ledger version")
        if not isinstance(rows, dict) or not isinstance(checksum, str):
            raise CalibrationIntegrityError("calibration ledger malformed")
        if not hmac.compare_digest(checksum, self._checksum(rows)):
            raise CalibrationIntegrityError("calibration ledger checksum mismatch")
        return {str(k): dict(v) for k, v in rows.items() if isinstance(v, dict)}

    def _write(self, rows: dict[str, dict[str, Any]]) -> None:
        env = {"version": CALIBRATION_VERSION, "forecasts": rows, "sha256": self._checksum(rows)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(env)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    @staticmethod
    def _restore(raw: dict[str, Any]) -> Forecast:
        return Forecast(
            id=str(raw["id"]), claim=str(raw["claim"]), probability=float(raw["probability"]),
            forecaster=str(raw["forecaster"]), context_sha256=str(raw.get("context_sha256", "")),
            created_at=str(raw["created_at"]), outcome=raw.get("outcome"),
            resolved_at=str(raw.get("resolved_at", "")),
            resolution_attestation_sha256=str(raw.get("resolution_attestation_sha256", "")),
        )

    def forecast(self, *, claim: str, probability: float, forecaster: str,
                 context_sha256: str = "", forecast_id: str | None = None,
                 created_at: str | None = None) -> Forecast:
        claim = " ".join(str(claim).split()).strip(); forecaster = str(forecaster).strip()
        if not claim or not forecaster: raise ValueError("claim and forecaster are required")
        probability = _probability(probability)
        if context_sha256: context_sha256 = _sha256(context_sha256, field="context_sha256")
        stamp = created_at or datetime.now(UTC).isoformat()
        identity = forecast_id or _sha({"claim": claim, "forecaster": forecaster, "context": context_sha256, "created_at": stamp})[:32]
        row = Forecast(identity, claim, probability, forecaster[:300], context_sha256, stamp)
        with self._lease.acquire():
            rows = self._load(); existing = rows.get(identity)
            if existing is not None:
                restored = self._restore(existing)
                if (restored.claim, restored.probability, restored.forecaster, restored.context_sha256) != (row.claim, row.probability, row.forecaster, row.context_sha256):
                    raise CalibrationIntegrityError("forecast identity collision")
                return restored
            rows[identity] = asdict(row); self._write(rows); return row

    def resolve(self, forecast_id: str, *, outcome: bool, verification_attestation_sha256: str,
                resolved_at: str | None = None) -> Forecast:
        attestation = _sha256(verification_attestation_sha256, field="verification attestation")
        stamp = resolved_at or datetime.now(UTC).isoformat()
        with self._lease.acquire():
            rows = self._load(); raw = rows.get(forecast_id)
            if raw is None: raise KeyError(forecast_id)
            if raw.get("outcome") is not None:
                prior = self._restore(raw)
                if prior.outcome != bool(outcome) or prior.resolution_attestation_sha256 != attestation:
                    raise CalibrationIntegrityError("forecast resolution is immutable")
                return prior
            raw["outcome"] = bool(outcome); raw["resolved_at"] = stamp
            raw["resolution_attestation_sha256"] = attestation
            rows[forecast_id] = raw; self._write(rows); return self._restore(raw)

    def snapshot(self, *, resolved_only: bool = False) -> tuple[Forecast, ...]:
        with self._lease.acquire(): rows = self._load()
        values = [self._restore(raw) for raw in rows.values()]
        if resolved_only: values = [row for row in values if row.outcome is not None]
        return tuple(sorted(values, key=lambda row: (row.created_at, row.id)))

    def metrics(self, *, bins: int = 10, forecaster: str | None = None) -> dict[str, Any]:
        if bins < 2 or bins > 100: raise ValueError("bins must be between 2 and 100")
        rows = [row for row in self.snapshot(resolved_only=True) if forecaster is None or row.forecaster == forecaster]
        if not rows:
            return {"resolved": 0, "brier_score": None, "log_loss": None, "ece": None,
                    "max_calibration_gap": None, "mean_forecast": None, "base_rate": None,
                    "calibration_bias": None, "sharpness": None, "bins": [],
                    "calibration_available": False, "calibration_mature": False}

        outcomes = [float(bool(row.outcome)) for row in rows]
        probabilities = [row.probability for row in rows]
        brier = sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(rows)
        epsilon = 1e-12
        log_loss = -sum(y * math.log(max(p, epsilon)) + (1.0 - y) * math.log(max(1.0 - p, epsilon))
                        for p, y in zip(probabilities, outcomes)) / len(rows)
        mean_forecast = sum(probabilities) / len(rows); base_rate = sum(outcomes) / len(rows)
        sharpness = sum((p - mean_forecast) ** 2 for p in probabilities) / len(rows)

        bucket_rows: list[dict[str, Any]] = []; ece = 0.0; max_gap = 0.0
        for index in range(bins):
            lo = index / bins; hi = (index + 1) / bins
            if index == bins - 1:
                bucket = [row for row in rows if lo <= row.probability <= hi]
            else:
                bucket = [row for row in rows if lo <= row.probability < hi]
            if not bucket: continue
            mean_p = sum(row.probability for row in bucket) / len(bucket)
            observed = sum(bool(row.outcome) for row in bucket) / len(bucket)
            gap = abs(mean_p - observed); ece += gap * len(bucket) / len(rows); max_gap = max(max_gap, gap)
            bucket_rows.append({"lower": lo, "upper": hi, "count": len(bucket),
                                "mean_probability": round(mean_p, 6), "observed_frequency": round(observed, 6),
                                "absolute_gap": round(gap, 6)})
        return {"resolved": len(rows), "brier_score": round(brier, 6), "log_loss": round(log_loss, 6),
                "ece": round(ece, 6), "max_calibration_gap": round(max_gap, 6),
                "mean_forecast": round(mean_forecast, 6), "base_rate": round(base_rate, 6),
                "calibration_bias": round(mean_forecast - base_rate, 6), "sharpness": round(sharpness, 6),
                "bins": bucket_rows, "calibration_available": True, "calibration_mature": len(rows) >= 30}

    def stats(self) -> dict[str, Any]:
        rows = self.snapshot(); resolved = sum(row.outcome is not None for row in rows)
        with self._lease.acquire(): raw = self._load()
        return {"version": CALIBRATION_VERSION, "forecasts": len(rows), "resolved": resolved,
                "unresolved": len(rows) - resolved, "cross_process_locking": True,
                "lock_backend": self._lease.backend, "sha256": self._checksum(raw),
                "truth_authority": False}
