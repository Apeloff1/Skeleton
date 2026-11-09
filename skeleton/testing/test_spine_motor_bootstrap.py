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
from skeleton.persistence.spine_motor_preflight import (
    SpineMotorPreflight,
    SpineMotorPreflightError,
)
from skeleton.persistence.spine_motor_preflight_verify import (
    SpineMotorPreflightVerify,
    SpineMotorPreflightVerifyError,
)


class _AsyncCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[list[tuple[str, int]], bool, str]] = []

    async def create_index(
        self,
        keys,
        unique: bool = False,
        name: str | None = None,
    ):
        normalized = list(keys)
        assert isinstance(name, str) and name
        self.calls.append((normalized, unique, name))
        return name


class _SyncCollection(_AsyncCollection):
    def create_index(
        self,
        keys,
        unique: bool = False,
        name: str | None = None,
    ):
        normalized = list(keys)
        assert isinstance(name, str) and name
        self.calls.append((normalized, unique, name))
        return name


class _Broken:
    async def create_index(
        self,
        keys,
        unique: bool = False,
        name: str | None = None,
    ):
        raise RuntimeError("driver fault")


class _BadResult:
    async def create_index(
        self,
        keys,
        unique: bool = False,
        name: str | None = None,
    ):
        return {"not": "an index identity"}


class _WrongName:
    async def create_index(
        self,
        keys,
        unique: bool = False,
        name: str | None = None,
    ):
        return "wrong_index_name"


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
    assert len(first["digest"]) == 64
    assert [row["index_name"] for row in first["results"]] == [
        "namespace_1_consumer_id_1_event_id_1",
        "namespace_1_consumer_id_1_operation_id_1",
        "namespace_1_tenant_id_1_resource_id_1",
    ]
    assert all(row["result"] == row["index_name"] for row in first["results"])
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

    with pytest.raises(SpineMotorBootstrapError, match="identity mismatch"):
        asyncio.run(SpineMotorBootstrap().apply(collections))


def test_bootstrap_rejects_wrong_driver_index_name() -> None:
    collections = _collections()
    collections["fence"] = _WrongName()

    with pytest.raises(SpineMotorBootstrapError, match="identity mismatch"):
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


def test_bootstrap_verifier_rejects_result_identity_tamper() -> None:
    card = asyncio.run(SpineMotorBootstrap().apply(_collections()))
    forged = copy.deepcopy(card)
    forged["results"][0]["result"] = "wrong_index_name"

    with pytest.raises(
        SpineMotorBootstrapVerifyError,
        match="result identity changed",
    ):
        SpineMotorBootstrapVerify().verify(forged)


def test_bootstrap_verifier_rejects_digest_tamper() -> None:
    card = asyncio.run(SpineMotorBootstrap().apply(_collections()))
    forged = copy.deepcopy(card)
    forged["digest"] = "0" * 64

    with pytest.raises(
        SpineMotorBootstrapVerifyError,
        match="evidence digest mismatch",
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


class _PreflightDatabase:
    def __init__(
        self,
        *,
        ping_ok: int = 1,
        hello_ok: int = 1,
        min_wire: int = 0,
        max_wire: int = 21,
        broken_collection: str | None = None,
    ) -> None:
        self.ping_ok = ping_ok
        self.hello_ok = hello_ok
        self.min_wire = min_wire
        self.max_wire = max_wire
        self.broken_collection = broken_collection
        self.commands: list[str] = []

    async def command(self, name: str):
        self.commands.append(name)
        if name == "ping":
            return {"ok": self.ping_ok}
        if name == "hello":
            return {
                "ok": self.hello_ok,
                "minWireVersion": self.min_wire,
                "maxWireVersion": self.max_wire,
            }
        raise RuntimeError("unexpected command")

    def get_collection(self, name: str):
        if name == self.broken_collection:
            return object()
        return _AsyncCollection(name)


def test_motor_preflight_qualifies_protocol_without_activation() -> None:
    database = _PreflightDatabase()
    card = asyncio.run(SpineMotorPreflight().probe(database))
    verified = SpineMotorPreflightVerify().verify(card)

    assert database.commands == ["ping", "hello"]
    assert card["protocol_qualified"] is True
    assert card["collections"] == ["receipts", "watermarks", "fence"]
    assert card["min_wire_version"] == 0
    assert card["max_wire_version"] == 21
    assert len(card["digest"]) == 64
    assert card["driver_imported"] is False
    assert card["live_motor"] is False
    assert card["activated"] is False
    assert verified["verified"] is True
    assert verified["live_motor"] is False


@pytest.mark.parametrize(
    ("database", "match"),
    [
        (_PreflightDatabase(ping_ok=0), "ping did not return ok=1"),
        (_PreflightDatabase(hello_ok=0), "hello did not return ok=1"),
        (_PreflightDatabase(min_wire=9, max_wire=8), "wire-version range is invalid"),
        (_PreflightDatabase(broken_collection="fence"), "does not expose create_index"),
    ],
)
def test_motor_preflight_fails_closed(database, match: str) -> None:
    with pytest.raises(SpineMotorPreflightError, match=match):
        asyncio.run(SpineMotorPreflight().probe(database))


def test_motor_preflight_verifier_rejects_tampered_digest() -> None:
    card = asyncio.run(SpineMotorPreflight().probe(_PreflightDatabase()))
    forged = copy.deepcopy(card)
    forged["digest"] = "0" * 64

    with pytest.raises(SpineMotorPreflightVerifyError, match="digest mismatch"):
        SpineMotorPreflightVerify().verify(forged)


def test_motor_preflight_verifier_rejects_activation_claim() -> None:
    card = asyncio.run(SpineMotorPreflight().probe(_PreflightDatabase()))
    forged = copy.deepcopy(card)
    forged["live_motor"] = True

    with pytest.raises(SpineMotorPreflightVerifyError, match="gained live authority"):
        SpineMotorPreflightVerify().verify(forged)
