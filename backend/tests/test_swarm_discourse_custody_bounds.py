"""Core discourse safeguards apply to direct calls, bad archives and DB queries."""
from __future__ import annotations

import random

import pytest

from core import discourse_engine as engine


@pytest.mark.parametrize("context", [
    "not-a-dict",
    {"tags": "a" * 5000},
    {"tags": ["tag"] * 33},
    {"tags": ["x" * 129]},
    {"genre": "x" * 257},
    {"seed": {"nested": "untrusted"}},
    {"seed": "x" * 129},
    {"era_year": float("nan")},
])
def test_unsafe_context_rejected_before_archive_access(monkeypatch, context):
    def forbidden(*_a, **_kw):
        raise AssertionError("archive was read before validation")

    monkeypatch.setattr(engine, "get_shard_entry", forbidden)
    with pytest.raises(ValueError):
        engine.simulate("build-1", "design", context, persist=False)


@pytest.mark.parametrize("rounds", [0, -1, 11, 1.5, True])
def test_direct_simulation_rejects_invalid_rounds(monkeypatch, rounds):
    monkeypatch.setattr(engine, "get_shard_entry", lambda *_: (_ for _ in ()).throw(AssertionError("archive read")))
    with pytest.raises(ValueError, match="rounds"):
        engine.simulate("b", "p", {}, rounds=rounds, persist=False)


@pytest.mark.parametrize("row", [
    None,
    "not-a-dict",
    {"lore": "malformed string"},
    {"lore": {"a": "not a list"}},
    {"lore": []},
    {"lore": [42]},
    {"lore": ["a" * 100_000]},
    {"title": "b" * 100_000},
])
def test_malformed_lore_never_crashes_or_amplifies_output(row):
    agent = {"domain": "rendering", "expertise": ["a", "b"], "agent": "test", "category": "graphics"}
    line = engine._agent_line(agent, [row], random.Random(1), "suggests")
    assert "rendering" in line or "test" in line
    assert len(line) < 500


@pytest.mark.parametrize("invalid", [0, -3, True, "100", 1.5])
def test_disallowed_query_limits_fail_before_database(monkeypatch, invalid):
    class BadDB:
        def find(self, *_a):
            raise AssertionError("DB must not be touched")

    monkeypatch.setattr(engine, "_discourse", BadDB())
    with pytest.raises(ValueError, match="limit"):
        engine.latest(invalid)
    with pytest.raises(ValueError, match="limit"):
        engine.get_for_build("b", limit=invalid)


def test_database_queries_are_bounded_to_100_rows(monkeypatch):
    seen = []

    class Cursor:
        def sort(self, *_a):
            return self
        def limit(self, limit):
            seen.append(limit)
            return self
        def __iter__(self):
            yield {"_id": 1, "build_id": "b", "phase": "p"}

    class DB:
        def find(self, query):
            seen.append(query)
            return Cursor()

    monkeypatch.setattr(engine, "_discourse", DB())
    assert len(engine.latest(1_000_000)) == 1
    assert len(engine.get_for_build("b", limit=1_000_000)) == 1
    assert seen[1] == 100
    assert seen[3] == 100


def test_context_tags_are_fenced_before_agent_ranking(monkeypatch):
    captured = []
    monkeypatch.setattr(engine, "find_relevant", lambda tokens, limit: captured.extend(tokens) or [])
    monkeypatch.setattr(engine, "pick_balanced", lambda count: [])
    engine._gather_agents({"tags": ["foo bar " * 10] * 32}, count=6)
    assert len(captured) <= 64
