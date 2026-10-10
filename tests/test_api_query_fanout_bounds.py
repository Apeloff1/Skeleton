"""Fan-out bounds for retrieval ``k`` and memory ``top_k``.

``POST /api/v1/retrieval/query`` and ``POST /api/v1/memory/query`` used to
accept any positive integer, letting a single request fan out unbounded work
across the quad retriever planes / memory tiers. The routes now reject values
above the caps with ``invalid_argument`` -> HTTP 422 instead of silently
clamping. The retrieval cap is pinned to the CLI retrieve handler's cap so the
API and CLI surfaces cannot drift.

Route handlers are called directly with stub state so the bound is tested
without booting Genesis.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402

from skeleton.api import routes  # noqa: E402
from skeleton.app.runtime import runtime_commands  # noqa: E402
from skeleton.application.command_contracts import CommandError  # noqa: E402

MAX_RETRIEVE_K = routes._MAX_RETRIEVAL_K
MAX_MEMORY_TOP_K = routes._MAX_MEMORY_TOP_K


class _FakeQuad:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def retrieve(self, query: str, *, k: int, use_cache: bool = True) -> list[Any]:
        del query, use_cache
        self.calls.append(k)
        return []

    def stats(self) -> dict[str, Any]:
        return {}


class _FakeTrinity:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def query_unified(self, query_text: str, *, top_k_per_tier: int, metadata_filter=None):
        del query_text, metadata_filter
        self.calls.append(top_k_per_tier)
        return SimpleNamespace(
            facts=[],
            persona_frame=[],
            personal_history=[],
            combined_score=0.0,
            token_estimate=0,
            provenance_chain=[],
        )


def _retrieval_state(quad: _FakeQuad) -> SimpleNamespace:
    return SimpleNamespace(genesis=SimpleNamespace(handles={"quad": quad}))


def _memory_state(trinity: _FakeTrinity) -> SimpleNamespace:
    return SimpleNamespace(memory_trinity=trinity)


def _retrieve(payload: dict[str, Any], quad: _FakeQuad) -> dict[str, Any]:
    return asyncio.run(routes.retrieval_query(payload, state=_retrieval_state(quad)))


def _memory(payload: dict[str, Any], trinity: _FakeTrinity) -> dict[str, Any]:
    return asyncio.run(routes.memory_query(payload, state=_memory_state(trinity)))


def test_caps_are_positive_contract_constants() -> None:
    assert isinstance(MAX_RETRIEVE_K, int) and MAX_RETRIEVE_K >= 1
    assert isinstance(MAX_MEMORY_TOP_K, int) and MAX_MEMORY_TOP_K >= 1
    # The CLI retrieve handler must share the same cap as the HTTP route.
    assert runtime_commands._MAX_RETRIEVE_K == MAX_RETRIEVE_K


# --- retrieval k -----------------------------------------------------------


@pytest.mark.parametrize("k", [1, 8, MAX_RETRIEVE_K])
def test_retrieval_query_accepts_k_within_bounds(k: int) -> None:
    quad = _FakeQuad()
    body = _retrieve({"query": "alpha", "k": k}, quad)
    assert body["results"] == []
    assert quad.calls == [k]


def test_retrieval_query_default_k_is_within_bounds() -> None:
    quad = _FakeQuad()
    _retrieve({"query": "alpha"}, quad)
    assert quad.calls == [8]
    assert 1 <= quad.calls[0] <= MAX_RETRIEVE_K


@pytest.mark.parametrize("k", [0, -1])
def test_retrieval_query_rejects_k_below_one(k: int) -> None:
    quad = _FakeQuad()
    with pytest.raises(HTTPException) as exc:
        _retrieve({"query": "alpha", "k": k}, quad)
    assert exc.value.status_code == 422
    assert quad.calls == []


@pytest.mark.parametrize("k", [MAX_RETRIEVE_K + 1, 10_000, 2**31])
def test_retrieval_query_rejects_k_above_cap(k: int) -> None:
    quad = _FakeQuad()
    with pytest.raises(HTTPException) as exc:
        _retrieve({"query": "alpha", "k": k}, quad)
    assert exc.value.status_code == 422
    assert str(MAX_RETRIEVE_K) in str(exc.value.detail)
    assert quad.calls == [], "over-cap k must be rejected before fan-out"


# --- memory top_k ----------------------------------------------------------


@pytest.mark.parametrize("top_k", [1, 3, MAX_MEMORY_TOP_K])
def test_memory_query_accepts_top_k_within_bounds(top_k: int) -> None:
    trinity = _FakeTrinity()
    body = _memory({"query": "alpha", "top_k": top_k}, trinity)
    assert body["facts"] == []
    assert trinity.calls == [top_k]


@pytest.mark.parametrize("top_k", [0, -5])
def test_memory_query_rejects_top_k_below_one(top_k: int) -> None:
    trinity = _FakeTrinity()
    with pytest.raises(HTTPException) as exc:
        _memory({"query": "alpha", "top_k": top_k}, trinity)
    assert exc.value.status_code == 422
    assert trinity.calls == []


@pytest.mark.parametrize("top_k", [MAX_MEMORY_TOP_K + 1, 1_000_000])
def test_memory_query_rejects_top_k_above_cap(top_k: int) -> None:
    trinity = _FakeTrinity()
    with pytest.raises(HTTPException) as exc:
        _memory({"query": "alpha", "top_k": top_k}, trinity)
    assert exc.value.status_code == 422
    assert str(MAX_MEMORY_TOP_K) in str(exc.value.detail)
    assert trinity.calls == [], "over-cap top_k must be rejected before fan-out"


# --- CLI retrieve handler parity ---------------------------------------------


def test_retrieve_command_handler_rejects_k_above_cap() -> None:
    quad = _FakeQuad()
    handle = runtime_commands._retrieve_handler(_retrieval_state(quad))
    with pytest.raises(CommandError) as exc:
        handle({"query": "alpha", "k": MAX_RETRIEVE_K + 1})
    assert exc.value.code == "invalid_argument"
    assert quad.calls == []
