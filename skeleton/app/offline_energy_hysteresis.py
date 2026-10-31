"""Monotonic, deterministic anti-thrash gate for measured local energy admission.

This controller only tightens an existing operator/resource admission. It
never starts model work, raises device limits or alters hardware controls.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import hmac
from typing import Mapping

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
            target = candidate.allowed_workers
            reason = candidate.reason if target == 0 else "within_measured_energy_limit"
        if type(target) is not int or not 0 <= target <= candidate.base_workers <= 256:
            raise HysteresisError("candidate exceeds its source resource budget")
        if self.last_seen_ns is not None and now_ns <= self.last_seen_ns:
            raise HysteresisError("non-advancing monotonic sample clock")
        # Validate candidate before consuming the monotonic clock tick.
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
        self.last_seen_ns = now_ns
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



    def checkpoint(self) -> dict[str, object]:
        """Deterministic integrity receipt, not a trusted anti-rollback anchor."""
        body: dict[str, object] = {
            "schema": "skeleton.offline.energy-hysteresis-checkpoint.v1",
            "policy": asdict(self.policy),
            "workers": self.workers,
            "healthy_streak": self.healthy_streak,
            "last_change_ns": self.last_change_ns,
            "last_seen_ns": self.last_seen_ns,
            "last_receipt_digest": self.last_receipt.digest if self.last_receipt else None,
        }
        digest = sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        return {**body, "digest": digest}

    @classmethod
    def restart_from_checkpoint(
        cls, state: Mapping[str, object], *, expected_digest: str,
    ) -> "EnergyHysteresis":
        """Fail closed across restarts: validate history, import zero grants.

        The caller must pin expected_digest outside this mutable checkpoint.
        A hash cannot prove the current OS monotonic epoch or prevent a
        coordinated rollback of both checkpoint and caller's digest.
        """
        fields = {
            "schema", "policy", "workers", "healthy_streak",
            "last_change_ns", "last_seen_ns", "last_receipt_digest", "digest",
        }
        if not isinstance(state, Mapping) or set(state) != fields:
            raise HysteresisError("invalid energy checkpoint shape")
        if state["schema"] != "skeleton.offline.energy-hysteresis-checkpoint.v1":
            raise HysteresisError("unsupported energy checkpoint")
        if (type(expected_digest) is not str or len(expected_digest) != 64
                or any(c not in "0123456789abcdef" for c in expected_digest)):
            raise HysteresisError("trusted checkpoint digest required")
        body = {k: state[k] for k in fields if k != "digest"}
        try:
            actual = sha256(json.dumps(
                body, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")).hexdigest()
        except (ValueError, TypeError, OverflowError) as exc:
            raise HysteresisError("invalid energy checkpoint encoding") from exc
        if (type(state["digest"]) is not str
                or not hmac.compare_digest(state["digest"], actual)
                or not hmac.compare_digest(expected_digest, actual)):
            raise HysteresisError("energy checkpoint integrity mismatch")
        raw_policy = state["policy"]
        if (type(raw_policy) is not dict
                or set(raw_policy) != set(HysteresisPolicy.__dataclass_fields__)):
            raise HysteresisError("invalid checkpoint policy")
        policy = HysteresisPolicy(**raw_policy)
        workers, streak = state["workers"], state["healthy_streak"]
        if (type(workers) is not int or not 0 <= workers <= 256
                or type(streak) is not int or not 0 <= streak < policy.recovery_samples):
            raise HysteresisError("invalid checkpoint admission")
        seen, changed = state["last_seen_ns"], state["last_change_ns"]
        if any(v is not None and (type(v) is not int or v < 0)
               for v in (seen, changed)):
            raise HysteresisError("invalid checkpoint chronology")
        if changed is not None and (seen is None or changed > seen):
            raise HysteresisError("invalid checkpoint chronology")
        prior = state["last_receipt_digest"]
        if prior is not None and (
            type(prior) is not str or len(prior) != 64
            or any(c not in "0123456789abcdef" for c in prior)
        ):
            raise HysteresisError("invalid prior energy receipt")
        return cls(policy)  # No inherited workers or stale monotonic epoch.

__all__ = ["EnergyHysteresis", "HysteresisError", "HysteresisPolicy", "HysteresisReceipt"]
