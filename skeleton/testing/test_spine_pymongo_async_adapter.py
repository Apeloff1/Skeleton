from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pymongo")

from skeleton.deploy.spine_pymongo_async import (
    MIN_PYMONGO_ASYNC,
    SpinePyMongoAsyncAdapter,
    SpinePyMongoAsyncAdapterError,
    _version_tuple,
    driver_receipt,
)


def test_supported_async_driver_receipt_is_content_addressed_and_dark() -> None:
    receipt = driver_receipt()
    assert receipt["driver_distribution"] == "pymongo"
    assert receipt["driver_class"] == "AsyncMongoClient"
    assert receipt["supported_async_driver"] is True
    assert receipt["motor_dependency"] is False
    assert receipt["deployment_driver_imported"] is True
    assert receipt["core_driver_imported"] is False
    assert receipt["runtime_activated"] is False
    assert _version_tuple(receipt["driver_version"]) >= MIN_PYMONGO_ASYNC
    assert len(receipt["digest"]) == 64
    assert receipt["completion_checkbox"] is False


def test_adapter_constructs_async_database_without_network_activation() -> None:
    async def scenario() -> None:
        session = SpinePyMongoAsyncAdapter().open(
            uri="mongodb://127.0.0.1:27017",
            database_name="skeleton_p2_adapter_test",
        )
        try:
            assert session.database.name == "skeleton_p2_adapter_test"
            assert session.receipt["runtime_activated"] is False
            assert session.receipt["supported_async_driver"] is True
        finally:
            await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("uri", "database_name", "timeout", "match"),
    [
        ("", "db", 5000, "URI"),
        ("mongodb://127.0.0.1:27017", "", 5000, "database name"),
        ("mongodb://127.0.0.1:27017", "db", 0, "positive integer"),
    ],
)
def test_adapter_rejects_invalid_configuration(
    uri: str, database_name: str, timeout: int, match: str
) -> None:
    with pytest.raises(SpinePyMongoAsyncAdapterError, match=match):
        SpinePyMongoAsyncAdapter().open(
            uri=uri,
            database_name=database_name,
            server_selection_timeout_ms=timeout,
        )
