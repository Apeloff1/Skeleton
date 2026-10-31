"""Monotonic, deterministic anti-thrash gate for measured local energy admission.

This controller only tightens an existing operator/resource admission. It
never starts model work, raises device limits or alters hardware controls.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math

from skeleton.app.offline_energy_budget import EnergyAdmission

SCHEMA = "skeleton.offline.energy-hysteresis.v1"


class HysteresisError(ValueError):
    """Invalid sample chronology, policy or energy admission."""


@dataclass(frozen=True, slots=True)
class HysteresisPolicy:
    recovery_samples: int = 3
    recovery_cooldown_ns: int = 5_000_000_000
    max_sample_age_ns: int = 10_000_000_000
    max_recovery_step: int = 1

    def __post_init__(self) -> None:
        if type(self.recovery_samples) is not int or not 2 <= self.recovery_samples <= 100:
            raise HysteresisError("invalid recovery sample count")
        if type(self.recovery_cooldown_ns) is not int or not 0 <= self.recovery_cooldown_ns <= 3600 * 10**9:
            raise HysteresisError("invalid cooldown")
        if type(self.max_sample_age_ns) is not int or not 1 <= self.max_sample_age_ns <= 3600 * 10**9:
            raise HysteresisError("invalid sample age")
        if type(self.max_recovery_step) is not int or not 1 <= self.max_recovery_step <= 32:
            raise HysteresisError("invalid recovery step")


@dataclass(frozen=True, slots=True)
class HysteresisReceipt:
    admitted_workers: int
    candidate_workers: int
    healthy_streak: int
    reason: str
    digest: str
    sample_ns: int


class EnergyHysteresis:
    """Immediate shedding, slow bounded recovery, stale telemetry fails closed."""

    def __init__(self, policy: HysteresisPolicy | None = None) -> None:
        self.policy = policy or HysteresisPolicy()
        if not isinstance(self.policy, HysteresisPolicy):
            raise HysteresisError("invalid hysteresis policy")
        self.workers = 0
        self.healthy_streak = 0
        self.last_change_ns: int | None = None
        self.last_seen_ns: int | None = None
        self.last_receipt: HysteresisReceipt | None = None

    def step(self, candidate: EnergyAdmission, *, now_ns: int, sampled_ns: int) -> HysteresisReceipt:
        if not isinstance(candidate, EnergyAdmission):
            raise HysteresisError("source-bound energy admission required")
        if any(type(value) is not int or value < 0 for value in (now_ns, sampled_ns)):
            raise HysteresisError("invalid monotonic timestamp")
        if sampled_ns > now_ns or now_ns - sampled_ns > self.policy.max_sample_age_ns:
            target, reason = 0, "stale_or_future_telemetry"
        else:
            target, reason = candidate.allowed_workers, "within_measured_energy_limit"
        if type(target) is not int or not 0 <= target <= candidate.base_workers <= 256:
            raise HysteresisError("candidate exceeds its source resource budget")
        if self.last_seen_ns is not None and now_ns < self.last_seen_ns:
            raise HysteresisError("monotonic clock moved backwards")
        self.last_seen_ns = now_ns
        if target < self.workers:
            self.workers = target
            self.healthy_streak = 0
            self.last_change_ns = now_ns
            reason = "immediate_pressure_shedding" if target else reason
        elif target > self.workers:
            self.healthy_streak += 1
            cooled = (self.last_change_ns is None
                      or now_ns - self.last_change_ns >= self.policy.recovery_cooldown_ns)
            if self.healthy_streak >= self.policy.recovery_samples and cooled:
                self.workers = min(target, self.workers + self.policy.max_recovery_step)
                self.healthy_streak = 0
                self.last_change_ns = now_ns
                reason = "bounded_recovery"
            else:
                reason = "recovery_hysteresis"
        else:
            self.healthy_streak = 0
        body = {"schema": SCHEMA, "candidate_digest": candidate.digest,
                "candidate_workers": target, "admitted_workers": self.workers,
                "healthy_streak": self.healthy_streak, "reason": reason,
                "sample_ns": sampled_ns, "now_ns": now_ns,
                "policy": {"recovery_samples": self.policy.recovery_samples,
                           "recovery_cooldown_ns": self.policy.recovery_cooldown_ns,
                           "max_sample_age_ns": self.policy.max_sample_age_ns,
                           "max_recovery_step": self.policy.max_recovery_step}}
        digest = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipt = HysteresisReceipt(self.workers, target, self.healthy_streak,
                                    reason, digest, sampled_ns)
        self.last_receipt = receipt
        return receipt


__all__ = ["EnergyHysteresis", "HysteresisError", "HysteresisPolicy", "HysteresisReceipt"]
