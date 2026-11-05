"""Fail-closed regression coverage for swarm micro-DB seeding budgets."""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from routes.swarm_hub import SeedReq
from seeds import hyperscale_micro_dbs as seeder


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 0, -1, 201])
def test_route_rejects_nonfinite_nonpositive_or_excessive_multiplier(value):
    with pytest.raises(ValidationError):
        SeedReq(target_multiplier=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 0, -1, 201, True, "3"])
def test_direct_seed_rejects_bad_multiplier_before_database(monkeypatch, value):
    def forbidden_database(*_args, **_kwargs):
        raise AssertionError("database was opened before multiplier was validated")

    monkeypatch.setattr(seeder, "MongoClient", forbidden_database)
    with pytest.raises(ValueError, match="target_multiplier"):
        seeder.seed_all(target_multiplier=value)


def test_route_keeps_finite_valid_budgets():
    for value in (0.001, 1.0, 200):
        assert math.isfinite(SeedReq(target_multiplier=value).target_multiplier)


def test_route_cannot_dispatch_invalid_budget(monkeypatch):
    # Even direct model construction cannot reach the seed command for NaN.
    with pytest.raises(ValidationError):
        SeedReq(target_multiplier=float("nan"))
