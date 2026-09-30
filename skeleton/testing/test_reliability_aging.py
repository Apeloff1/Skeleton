from __future__ import annotations

import pytest

from skeleton.reliability.aging import (
    AgingAsset,
    AgingPolicy,
    AgingPolicyError,
    AgingSimulator,
)


POLICY = AgingPolicy(
    warning_age=10,
    retirement_age=20,
    max_generation=4,
    max_history=32,
)


def test_accelerated_time_matches_equivalent_stepwise_aging() -> None:
    fast = AgingSimulator(POLICY)
    slow = AgingSimulator(POLICY)
    asset = AgingAsset("asset-a", generation=1)

    accelerated = fast.accelerated_advance(
        asset,
        elapsed_units=4,
        acceleration=3,
    )
    stepped = slow.advance(asset, steps=12)

    assert accelerated == stepped
    assert accelerated.age == 12
    assert fast.state(accelerated) == "aging"


def test_long_soak_history_remains_bounded() -> None:
    sim = AgingSimulator(POLICY)
    asset = AgingAsset("asset-a", generation=1)

    asset = sim.advance(asset, steps=10_000)

    assert sim.step == 10_000
    assert len(sim.history()) == POLICY.max_history
    assert sim.history()[0].step == 10_000 - POLICY.max_history + 1
    assert sim.state(asset) == "retire_required"


def test_aging_state_transitions_are_deterministic() -> None:
    sim = AgingSimulator(POLICY)
    asset = AgingAsset("asset-a", generation=1)

    asset = sim.advance(asset, steps=9)
    assert sim.state(asset) == "active"

    asset = sim.advance(asset)
    assert sim.state(asset) == "aging"

    asset = sim.advance(asset, steps=10)
    assert sim.state(asset) == "retire_required"


def test_retirement_requires_explicit_replacement_migration() -> None:
    sim = AgingSimulator(POLICY)
    old = sim.advance(AgingAsset("asset-old", generation=2), steps=20)

    retired, replacement, receipt = sim.retire_and_migrate(
        old,
        replacement_asset_id="asset-new",
    )

    assert retired.retired is True
    assert retired.replacement_id == "asset-new"
    assert replacement.asset_id == "asset-new"
    assert replacement.generation == 3
    assert replacement.age == 0
    assert len(receipt.receipt_digest) == 64
    assert receipt.source_age == 20


def test_asset_over_generation_limit_requires_retirement_even_when_young() -> None:
    sim = AgingSimulator(POLICY)
    asset = AgingAsset("legacy", generation=5, age=1)

    assert sim.state(asset) == "retire_required"
    _, replacement, _ = sim.retire_and_migrate(
        asset,
        replacement_asset_id="legacy-migrated",
    )
    assert replacement.generation == 6


def test_retirement_cannot_happen_early_or_reuse_identity() -> None:
    sim = AgingSimulator(POLICY)
    fresh = AgingAsset("fresh", generation=1, age=1)

    with pytest.raises(AgingPolicyError, match="not eligible"):
        sim.retire_and_migrate(fresh, replacement_asset_id="new")

    old = AgingAsset("old", generation=1, age=20)
    with pytest.raises(AgingPolicyError, match="must be new"):
        sim.retire_and_migrate(old, replacement_asset_id="old")


def test_retired_asset_does_not_continue_aging_silently() -> None:
    sim = AgingSimulator(POLICY)
    old = AgingAsset("old", generation=1, age=20)
    retired, _, _ = sim.retire_and_migrate(
        old,
        replacement_asset_id="new",
    )

    after = sim.advance(retired, steps=100)
    assert after.age == retired.age
    assert sim.state(after) == "retired"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"warning_age": 0, "retirement_age": 2, "max_generation": 1},
        {"warning_age": 2, "retirement_age": 2, "max_generation": 1},
        {"warning_age": 3, "retirement_age": 2, "max_generation": 1},
        {"warning_age": 1, "retirement_age": 2, "max_generation": 0},
        {"warning_age": 1, "retirement_age": 2, "max_generation": 1, "max_history": 0},
    ],
)
def test_invalid_aging_policy_fails_fast(kwargs) -> None:
    with pytest.raises(AgingPolicyError):
        AgingPolicy(**kwargs)
