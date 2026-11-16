"""Crawler readiness is an observation, not a schema mutation."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio

import pytest

from core import dragon_crawler as crawler


def inventory():
    return {str(index): {"key": list(keys)}
            for index, keys in enumerate(crawler.CRAWLER_SESSION_INDEXES)}


@pytest.mark.parametrize("mutation", ["missing", "reversed", "hidden", "sparse",
                                      "partial", "ttl", "unique", "malformed"])
def test_index_inventory_requires_full_canonical_key_order(mutation):
    rows = inventory()
    if mutation == "missing":
        rows.pop("0")
    elif mutation == "reversed":
        rows["0"]["key"].reverse()
    elif mutation == "partial":
        rows["0"]["partialFilterExpression"] = {"status": "ready"}
    elif mutation == "ttl":
        rows["0"]["expireAfterSeconds"] = 60
    elif mutation == "malformed":
        rows["0"]["key"] = [["tenant_id", True]]
    else:
        rows["0"][mutation] = True
    assert crawler._required_indexes_observed(rows) is False


def test_complete_inventory_qualifies_without_index_names_as_authority():
    assert crawler._required_indexes_observed(inventory())


@pytest.mark.parametrize("complete", [True, False])
def test_readiness_never_mutates_schema_or_authorizes_writer_cache(monkeypatch, complete):
    app = object.__new__(crawler.DragonCrawlerApplication)
    app.database = SimpleNamespace(command=AsyncMock(return_value={"ok": 1}))
    app.sessions = SimpleNamespace(index_information=AsyncMock(return_value=inventory() if complete else {}),
                                   create_index=AsyncMock())
    app.engine = SimpleNamespace(provider_status=AsyncMock(return_value={}))
    app._indexes_ready = False
    monkeypatch.setattr(crawler, "_core", lambda: object())
    monkeypatch.setattr(app, "_readiness_payload",
                         lambda available,code,message: {"available":available,"code":code})
    result = asyncio.run(app.readiness())
    assert result == {"available":complete, "code":"ready" if complete else "crawler_indexes_unavailable"}
    app.sessions.create_index.assert_not_awaited()
    assert app._indexes_ready is False
    assert app.engine.provider_status.await_count == int(complete)


def test_crawler_index_initialization_remains_explicit_and_idempotent():
    app = object.__new__(crawler.DragonCrawlerApplication)
    app.sessions = SimpleNamespace(create_index=AsyncMock())
    app._indexes_ready = False
    async def initialize():
        await app.ensure_indexes()
        await app.ensure_indexes()
    asyncio.run(initialize())
    assert app._indexes_ready
    assert [call.args[0] for call in app.sessions.create_index.await_args_list] == [
        list(keys) for keys in crawler.CRAWLER_SESSION_INDEXES
    ]
