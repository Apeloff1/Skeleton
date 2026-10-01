from __future__ import annotations

import asyncio
import copy

import pytest

from skeleton.persistence.spine_motor_bootstrap import (
    SpineMotorBootstrap,
    SpineMotorBootstrapError,
)
from skeleton.persistence.spine_motor_bootstrap_replay import (
    SpineMotorBootstrapReplay,
    SpineMotorBootstrapReplayError,
)
from skeleton.persistence.spine_motor_bootstrap_verify import (
    SpineMotorBootstrapVerify,
    SpineMotorBootstrapVerifyError,
)
from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class _AsyncCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[list[tuple[str, int]], bool]] = []

    async def create_index(self, keys, unique: bool = False):
        normalized = list(keys)
        self.calls.append((normalized, unique))
        fields = "_".join(key for key, _direction in normalized)
        return f"{self.name}:{fields}:{int(unique)}"


class _SyncCollection(_AsyncCollection):
    def create_index(self, keys, unique: bool = False):
        normalized = list(keys)
        self.calls.append((normalized, unique))
        fields = "_".join(key for key, _direction in normalized)
        return f"{self.name}:{fields}:{int(unique)}"


class _Broken:
    async def create_index(self, keys, unique: bool = False):
        raise RuntimeError("driver fault")


class _BadResult:
    async def create_index(self, keys, unique: bool = False):
        return {"not": "an index identity"}


def _collections(factory=_AsyncCollection):
    return {
        "receipts": factory("receipts"),
        "watermarks": factory("watermarks"),
        "fence": factory("fence"),
    }


def test_motor_plan_is_deterministic_and_driver_dark() -> None:
    first = SpineMotorPlan().card()
    second = SpineMotorPlan().card()

    assert first == second
    assert first["count"] == 3
    assert len(first["digest"]) == 64
    assert [row["collection"] for row in first["indexes"]] == [
        "receipts",
        "watermarks",
        "fence",
    ]
    assert all(row["unique"] is True for row in first["indexes"])
    assert first["live_motor"] is False
    assert first["driver_imported"] is False
    assert first["completion_checkbox"] is False


def test_async_bootstrap_verifies_and_replays_equivalently() -> None:
    bootstrap = SpineMotorBootstrap()
    first_collections = _collections()
    second_collections = _collections()

    first = asyncio.run(bootstrap.apply(first_collections))
    second = asyncio.run(bootstrap.apply(second_collections))

    assert first["applied"] == 3
    assert first["missing"] == 0
    assert first["failures"] == 0
    assert first["bootstrap_exercised"] is True
    assert first["live_motor"] is False
    assert all(collection.calls for collection in first_collections.values())

    verified = SpineMotorBootstrapVerify().verify(first)
    replay = SpineMotorBootstrapReplay().card(first=first, second=second)
    assert verified["verified"] is True
    assert verified["verified_indexes"] == 3
    assert replay["equivalent"] is True
    assert replay["applied"] == 3
    assert replay["live_motor"] is False


def test_sync_create_index_protocol_is_supported() -> None:
    card = asyncio.run(SpineMotorBootstrap().apply(_collections(_SyncCollection)))
    assert card["applied"] == 3
    assert all(isinstance(row["result"], str) for row in card["results"])


def test_bootstrap_fails_closed_on_missing_collection() -> None:
    collections = _collections()
    collections.pop("fence")

    with pytest.raises(SpineMotorBootstrapError, match="missing bootstrap collections"):
        asyncio.run(SpineMotorBootstrap().apply(collections))


def test_bootstrap_fails_closed_on_driver_fault() -> None:
    collections = _collections()
    collections["fence"] = _Broken()

    with pytest.raises(SpineMotorBootstrapError, match="index bootstrap failed"):
        asyncio.run(SpineMotorBootstrap().apply(collections))


def test_bootstrap_rejects_non_text_driver_result() -> None:
    collections = _collections()
    collections["fence"] = _BadResult()

    with pytest.raises(SpineMotorBootstrapError, match="text or None"):
        asyncio.run(SpineMotorBootstrap().apply(collections))


def test_bootstrap_verifier_rejects_plan_identity_drift() -> None:
    card = asyncio.run(SpineMotorBootstrap().apply(_collections()))
    forged = copy.deepcopy(card)
    forged["plan_digest"] = "f" * 64

    with pytest.raises(
        SpineMotorBootstrapVerifyError,
        match="plan digest mismatch",
    ):
        SpineMotorBootstrapVerify().verify(forged)


def test_bootstrap_replay_rejects_result_drift() -> None:
    first = asyncio.run(SpineMotorBootstrap().apply(_collections()))
    second = copy.deepcopy(first)
    second["results"][0]["result"] = "changed"

    with pytest.raises(
        SpineMotorBootstrapReplayError,
        match="bootstrap replay result changed",
    ):
        SpineMotorBootstrapReplay().card(first=first, second=second)
