"""Conservative p99-guided offline CPU worker admission.

This consumes source-bound canonical tail profiles; it does not probe hardware,
run models, authenticate telemetry providers, or qualify GPU execution.
Unknown, simulated, stale, or insufficient evidence grants zero new slots.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from typing import Mapping

from .tail_latency_profile import PROFILE_SCHEMA

SCHEMA = "skeleton.ai.tail-admission.v1"
MAX_SLOTS = 64
MAX_BYTES = (1 << 63) - 1


def _digest(body: object) -> str:
    return sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _int(name: str, value: object, *, maximum: int = MAX_BYTES) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid " + name)
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise ValueError("invalid " + name)
    return value


@dataclass(frozen=True, slots=True)
class TailAdmissionPolicy:
    max_slots: int
    memory_per_slot_bytes: int
    p99_ttft_limit_ms: int
    p99_e2e_limit_ms: int
    increase_after_good_windows: int = 3
    reserve_percent: int = 25

    def __post_init__(self) -> None:
        if not 1 <= _int("max_slots", self.max_slots, maximum=MAX_SLOTS) <= MAX_SLOTS:
            raise ValueError("max_slots must be positive")
        for name in ("memory_per_slot_bytes", "p99_ttft_limit_ms", "p99_e2e_limit_ms"):
            if _int(name, getattr(self, name)) == 0:
                raise ValueError("positive " + name + " required")
        if not 1 <= _int("increase_after_good_windows", self.increase_after_good_windows, maximum=100) <= 100:
            raise ValueError("invalid good window count")
        _int("reserve_percent", self.reserve_percent, maximum=90)

    def body(self) -> dict[str, int]:
        return {
            "max_slots": self.max_slots,
            "memory_per_slot_bytes": self.memory_per_slot_bytes,
            "p99_ttft_limit_ms": self.p99_ttft_limit_ms,
            "p99_e2e_limit_ms": self.p99_e2e_limit_ms,
            "increase_after_good_windows": self.increase_after_good_windows,
            "reserve_percent": self.reserve_percent,
        }


class TailAdmissionGovernor:
    """Deterministic hysteresis with explicit generation and profile replay fence.

    State is in-process. The caller must durably CAS the generation and digest
    and re-probe RAM before actual execution; a receipt is not a reservation.
    """

    def __init__(self, policy: TailAdmissionPolicy, *, slots: int = 0,
                 generation: int = 0, good_windows: int = 0,
                 last_profile_digest: str = "0" * 64) -> None:
        if not isinstance(policy, TailAdmissionPolicy):
            raise ValueError("typed tail policy required")
        self.policy = policy
        self.slots = _int("slots", slots, maximum=policy.max_slots)
        self.generation = _int("generation", generation)
        self.good_windows = _int(
            "good_windows", good_windows, maximum=policy.increase_after_good_windows,
        )
        self.last_profile_digest = _sha(last_profile_digest, "last_profile_digest")

    def checkpoint(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": SCHEMA, "policy": self.policy.body(),
            "slots": self.slots, "generation": self.generation,
            "good_windows": self.good_windows,
            "last_profile_digest": self.last_profile_digest,
        }
        return {**body, "digest": _digest(body)}

    @classmethod
    def restore(cls, state: Mapping[str, object]) -> "TailAdmissionGovernor":
        fields = {
            "schema", "policy", "slots", "generation", "good_windows",
            "last_profile_digest", "digest",
        }
        if not isinstance(state, Mapping) or set(state) != fields:
            raise ValueError("invalid tail admission checkpoint")
        if state["schema"] != SCHEMA:
            raise ValueError("unsupported tail admission schema")
        if not hmac.compare_digest(
            _sha(state["digest"], "checkpoint digest"),
            _digest({key: state[key] for key in fields if key != "digest"}),
        ):
            raise ValueError("tail admission checkpoint integrity mismatch")
        raw_policy = state["policy"]
        if type(raw_policy) is not dict or set(raw_policy) != set(TailAdmissionPolicy.__dataclass_fields__):
            raise ValueError("invalid tail policy shape")
        return cls(
            TailAdmissionPolicy(**raw_policy),
            slots=state["slots"], generation=state["generation"],
            good_windows=state["good_windows"],
            last_profile_digest=state["last_profile_digest"],
        )

    def observe(
        self, profile: Mapping[str, object], *, expected_generation: int,
        current_ram_available_bytes: int,
    ) -> dict[str, object]:
        if _int("expected_generation", expected_generation) != self.generation:
            raise ValueError("stale tail admission generation")
        if self.generation == MAX_BYTES:
            raise ValueError("tail admission generation exhausted")
        ram = _int("current_ram_available_bytes", current_ram_available_bytes)
        if not isinstance(profile, Mapping) or profile.get("schema") != PROFILE_SCHEMA:
            raise ValueError("canonical tail profile required")
        digest = _sha(profile.get("digest"), "profile digest")
        if digest == self.last_profile_digest:
            raise ValueError("replayed tail profile")
        body = {key: profile[key] for key in profile if key != "digest"}
        if not hmac.compare_digest(digest, _digest(body)):
            raise ValueError("tail profile integrity mismatch")
        # All input fields are validated before state mutation.
        identity = profile.get("identity")
        resource = profile.get("resource")
        tail = profile.get("tail")
        if not isinstance(identity, Mapping) or not isinstance(resource, Mapping) or not isinstance(tail, Mapping):
            raise ValueError("incomplete tail profile")
        measured = (
            identity.get("evidence") == "measured"
            and profile.get("qualification") == "measured_tail_profile"
            and profile.get("minimum_tail_sample_count_met") is True
            and _int("requests", profile.get("requests"), maximum=10000) >= 100
            and _int("thermal_unavailable_samples", resource.get("thermal_unavailable_samples")) == 0
            and _int("thermal_hold_samples", resource.get("thermal_hold_samples")) == 0
        )
        observed_ram = _int(
            "min_ram_available_bytes", resource.get("min_ram_available_bytes"),
        )
        # Trust the smaller of a fresh host measurement and observed window
        # minimum. RAM is never overcommitted to compensate for slow p99.
        available = min(ram, observed_ram) * (100 - self.policy.reserve_percent) // 100
        memory_slots = min(self.policy.max_slots, available // self.policy.memory_per_slot_bytes)
        p99_ttft = _int("p99_ttft", tail["ttft_ms"]["p99"])
        p99_e2e = _int("p99_e2e", tail["e2e_ms"]["p99"])
        new_slots = min(self.slots, memory_slots)
        good = self.good_windows
        if not measured or memory_slots == 0:
            new_slots = 0
            good = 0
            reason = "unqualified_or_resource_hold"
        elif (p99_ttft > self.policy.p99_ttft_limit_ms
              or p99_e2e > self.policy.p99_e2e_limit_ms):
            new_slots = max(0, min(memory_slots, (self.slots + 1) // 2))
            good = 0
            reason = "p99_backpressure"
        elif (p99_ttft * 5 <= self.policy.p99_ttft_limit_ms * 4
              and p99_e2e * 5 <= self.policy.p99_e2e_limit_ms * 4):
            good += 1
            if good >= self.policy.increase_after_good_windows:
                new_slots = min(memory_slots, self.slots + 1)
                good = 0
            reason = "stable_hysteresis"
        else:
            good = 0
            reason = "tail_guard"
        self.slots = new_slots
        self.good_windows = good
        self.generation += 1
        self.last_profile_digest = digest
        return {
            "schema": "skeleton.ai.tail-admission-receipt.v1",
            "reason": reason, "admitted_slots": new_slots,
            "profile_digest": digest, "device_qualified": False,
            "checkpoint": self.checkpoint(),
        }
