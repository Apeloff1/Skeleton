"""Fail-closed integer/boolean payload types for shared command contracts."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from skeleton.application.command_contracts import CommandError, require_bool, require_int
from skeleton.application import build_runtime_command_service


def test_require_bool_rejects_truthy_stand_ins() -> None:
    assert require_bool({}, "repair", False) is False
    assert require_bool({"repair": True}, "repair", False) is True
    assert require_bool({"repair": False}, "repair", True) is False
    for value in (1, 0, "false", "true", None, 1.0):
        with pytest.raises(CommandError) as exc_info:
            require_bool({"repair": value}, "repair", False)
        assert exc_info.value.code == "invalid_argument"
        assert exc_info.value.http_status == 422


def test_require_int_rejects_bool_float_and_numeric_strings() -> None:
    assert require_int({}, "top_k", 3, minimum=1) == 3
    assert require_int({"top_k": 8}, "top_k", 3, minimum=1) == 8
    for value in (True, False, "3", 1.5, 3.0, None, "1"):
        with pytest.raises(CommandError) as exc_info:
            require_int({"top_k": value}, "top_k", 3, minimum=1)
        assert exc_info.value.code == "invalid_argument"
    with pytest.raises(CommandError) as too_small:
        require_int({"top_k": 0}, "top_k", 3, minimum=1)
    assert ">= 1" in too_small.value.message


class _MemoryHit:
    def __init__(self, text: str) -> None:
        self.chunk = type("Chunk", (), {"text": text})()


class _MemoryResult:
    facts = (_MemoryHit("fact"),)
    persona_frame = ()
    personal_history = ()
    combined_score = 1.0
    token_estimate = 4
    provenance_chain = []


class _Memory:
    def query_unified(self, query, top_k_per_tier=3, metadata_filter=None):
        self.query = query
        self.top_k_per_tier = top_k_per_tier
        self.metadata_filter = metadata_filter
        return _MemoryResult()


class _Game:
    def __init__(self, repair: bool) -> None:
        self.repair = repair

    def to_dict(self):
        return {"repair": self.repair}


class _Forge:
    def run(self, answers, title=None, target="json", repair=False):
        self.repair = repair
        return _Game(repair)


class _State:
    genesis = None
    memory_trinity = _Memory()
    gameforge = _Forge()
    registry = None

    def is_healthy(self):
        return {"overall": True, "checks": {}}


def test_memory_command_rejects_coerced_top_k() -> None:
    service = build_runtime_command_service(_State())
    ok = service.execute("memory", {"query": "hello", "top_k": 2})
    assert ok.ok is True
    assert ok.data["facts"] == ["fact"]

    defaulted = service.execute("memory", {"query": "hello"})
    assert defaulted.ok is True

    for payload in (
        {"query": "hello", "top_k": True},
        {"query": "hello", "top_k": "3"},
        {"query": "hello", "top_k": 1.5},
        {"query": "hello", "top_k": 0},
    ):
        result = service.execute("memory", payload)
        assert result.ok is False
        assert result.to_payload()["error"]["code"] == "invalid_argument"
        assert result.http_status == 422


def test_run_command_rejects_coerced_repair_flag() -> None:
    service = build_runtime_command_service(_State())
    ok = service.execute("run", {"answers": {}, "repair": True})
    assert ok.ok is True
    assert ok.data["game"]["repair"] is True

    defaulted = service.execute("run", {"answers": {}})
    assert defaulted.ok is True
    assert defaulted.data["game"]["repair"] is False

    for repair in (1, "false", "true", None):
        result = service.execute("run", {"answers": {}, "repair": repair})
        assert result.ok is False
        assert result.to_payload()["error"]["code"] == "invalid_argument"


def test_http_retrieval_query_rejects_coerced_k_and_cache_flag() -> None:
    from skeleton.api import routes

    class _Quad:
        def retrieve(self, query, k=8, use_cache=True):
            self.k = k
            self.use_cache = use_cache
            return []

        def stats(self):
            return {}

    class _Genesis:
        handles = {"quad": _Quad()}

    class _HttpState:
        genesis = _Genesis()

    body = asyncio.run(routes.retrieval_query({"query": "alpha", "k": 4, "use_cache": False}, _HttpState()))
    assert body["query"] == "alpha"
    assert body["results"] == []

    with pytest.raises(HTTPException) as coerced_k:
        asyncio.run(routes.retrieval_query({"query": "alpha", "k": True}, _HttpState()))
    assert coerced_k.value.status_code == 422

    with pytest.raises(HTTPException) as coerced_cache:
        asyncio.run(routes.retrieval_query({"query": "alpha", "use_cache": "false"}, _HttpState()))
    assert coerced_cache.value.status_code == 422
