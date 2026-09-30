"""Deterministic long-horizon aging and retirement simulation for P1 AC-23."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import hashlib
import json


class AgingPolicyError(ValueError):
    """Aging simulation or retirement policy is invalid."""


@dataclass(frozen=True, slots=True)
class AgingPolicy:
    warning_age: int
    retirement_age: int
    max_generation: int
    max_history: int = 1024

    def __post_init__(self) -> None:
        for name in ("warning_age", "retirement_age", "max_generation", "max_history"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AgingPolicyError(f"{name} must be a positive integer")
        if self.warning_age >= self.retirement_age:
            raise AgingPolicyError("warning_age must precede retirement_age")


@dataclass(frozen=True, slots=True)
class AgingAsset:
    asset_id: str
    generation: int
    age: int = 0
    retired: bool = False
    replacement_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise AgingPolicyError("asset_id must be non-empty")
        if self.generation < 1 or self.age < 0:
            raise AgingPolicyError("generation/age invalid")
        if self.retired and not self.replacement_id:
            raise AgingPolicyError("retired asset requires replacement_id")


@dataclass(frozen=True, slots=True)
class AgingEvent:
    step: int
    asset_id: str
    age: int
    state: str


@dataclass(frozen=True, slots=True)
class RetirementMigrationReceipt:
    source_asset_id: str
    source_generation: int
    replacement_asset_id: str
    replacement_generation: int
    source_age: int
    receipt_digest: str


class AgingSimulator:
    """Bounded deterministic simulator over an accelerated logical clock."""

    def __init__(self, policy: AgingPolicy) -> None:
        if not isinstance(policy, AgingPolicy):
            raise TypeError("policy must be AgingPolicy")
        self.policy = policy
        self._step = 0
        self._history: deque[AgingEvent] = deque(maxlen=policy.max_history)

    @property
    def step(self) -> int:
        return self._step

    def history(self) -> tuple[AgingEvent, ...]:
        return tuple(self._history)

    def advance(self, asset: AgingAsset, *, steps: int = 1) -> AgingAsset:
        if not isinstance(asset, AgingAsset):
            raise TypeError("asset must be AgingAsset")
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
            raise AgingPolicyError("steps must be positive integer")
        current = asset
        for _ in range(steps):
            self._step += 1
            if current.retired:
                state = "retired"
            else:
                current = replace(current, age=current.age + 1)
                state = self.state(current)
            self._history.append(
                AgingEvent(self._step, current.asset_id, current.age, state)
            )
        return current

    def accelerated_advance(
        self,
        asset: AgingAsset,
        *,
        elapsed_units: int,
        acceleration: int,
    ) -> AgingAsset:
        if (
            isinstance(elapsed_units, bool)
            or not isinstance(elapsed_units, int)
            or elapsed_units < 1
            or isinstance(acceleration, bool)
            or not isinstance(acceleration, int)
            or acceleration < 1
        ):
            raise AgingPolicyError("accelerated time inputs must be positive integers")
        return self.advance(asset, steps=elapsed_units * acceleration)

    def state(self, asset: AgingAsset) -> str:
        if asset.retired:
            return "retired"
        if asset.generation > self.policy.max_generation:
            return "retire_required"
        if asset.age >= self.policy.retirement_age:
            return "retire_required"
        if asset.age >= self.policy.warning_age:
            return "aging"
        return "active"

    def retire_and_migrate(
        self,
        asset: AgingAsset,
        *,
        replacement_asset_id: str,
    ) -> tuple[AgingAsset, AgingAsset, RetirementMigrationReceipt]:
        if self.state(asset) != "retire_required":
            raise AgingPolicyError("asset is not eligible for retirement")
        if not replacement_asset_id or replacement_asset_id == asset.asset_id:
            raise AgingPolicyError("replacement_asset_id must be new")
        replacement_generation = (\n            1 if asset.generation >= self.policy.max_generation\n            else asset.generation + 1\n        )
        replacement = AgingAsset(
            asset_id=replacement_asset_id,
            generation=replacement_generation,
            age=0,
        )
        retired = replace(
            asset,
            retired=True,
            replacement_id=replacement_asset_id,
        )
        payload = {
            "source_asset_id": asset.asset_id,
            "source_generation": asset.generation,
            "replacement_asset_id": replacement.asset_id,
            "replacement_generation": replacement.generation,
            "source_age": asset.age,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return (
            retired,
            replacement,
            RetirementMigrationReceipt(
                **payload,
                receipt_digest=digest,
            ),
        )


__all__ = [
    "AgingAsset",
    "AgingEvent",
    "AgingPolicy",
    "AgingPolicyError",
    "AgingSimulator",
    "RetirementMigrationReceipt",
]
