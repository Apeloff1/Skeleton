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


@pytest.mark.parametrize("subset", [
    ["unknown-agent"],
    ["unknown-agent", "unknown-agent"],
    ["x" * 1000],
    ["unknown-agent"] * 201,
])
def test_route_rejects_unknown_or_oversize_subset(subset):
    with pytest.raises(ValidationError):
        SeedReq(subset=subset)


def test_explicit_empty_subset_never_opens_mongo_or_writes(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("empty subset must not touch Mongo or create shards")

    monkeypatch.setattr(seeder, "MongoClient", forbidden)
    monkeypatch.setattr(seeder, "write_shard", forbidden)
    monkeypatch.setattr(seeder, "vault_stats", lambda: {
        "shard_count": 5,
        "total_rows": 100,
        "total_compressed_bytes": 10,
        "total_raw_bytes": 100,
        "avg_compression_ratio": 10.0,
    })
    result = seeder.seed_all(subset=[], force=True)
    assert result["created"] == 0
    assert result["skipped"] == 0
    assert result["total_shards"] == 5
    assert SeedReq(subset=[]).subset == []


@pytest.mark.parametrize("subset", [
    "not-a-list",
    ["unknown-agent"],
    ["x" * 1000],
    [1234],
])
def test_direct_seeder_rejects_bad_subset_before_mongo(monkeypatch, subset):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("invalid subset touched database")

    monkeypatch.setattr(seeder, "MongoClient", forbidden)
    with pytest.raises(ValueError, match="subset"):
        seeder.seed_all(subset=subset)
