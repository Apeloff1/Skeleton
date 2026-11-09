"""Exercise actual frontier turns, throttling, retries and indexed continuation."""
import sqlite3
from unittest.mock import patch

import pytest

from skeleton.ai.webcrawler.core import CrawlBudget, CrawlEngine, CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.game_knowledge_acquisition import (
    GameSource, acquire_game_batch, acquire_game_documents, queue_game_sources,
    prioritize_game_sources,
)
from skeleton.ai.webcrawler.game_builder_knowledge_runtime import KnowledgeDrivenGameBuilder


class Pages:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = failures or {}

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        status = self.failures.pop(url, 200)
        text = (f"Movement jump collision camera design for {url}. " * 8).encode()
        return FetchResponse(url, status, {
            "content-type": "text/plain", "retry-after": "7",
        }, text, 100)


def crawler(*urls, delay=1, failures=None, budget=None):
    pages = Pages(failures)
    result = CrawlEngine(pages, policy=CrawlPolicy(
        max_depth=0, min_host_delay_seconds=delay,
    ), budget=budget)
    for url in urls:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        result.install_robots(f"{parts.scheme}://{parts.netloc}", "User-agent: *\nAllow: /")
        result.enqueue(url)
    return result, pages


def test_delayed_turn_stops_and_resumes_without_spinning_or_skipping():
    engine, pages = crawler("https://docs.example/a", "https://docs.example/b")
    with patch.object(engine, "step", wraps=engine.step) as step:
        first = acquire_game_batch(engine, now=100, max_steps=10000)
        assert step.call_count == 1
        assert first.stop_reason == "deferred"
        assert first.next_ready_at == 101
        assert first.pending_sources == 1
        assert first.requests == 1
        assert first.response_bytes > 0
        assert len(first.documents) == 1
        waiting = acquire_game_batch(engine, now=100)
        assert waiting.steps == 0 and waiting.requests == 0
        assert step.call_count == 1
    second = acquire_game_batch(engine, now=101)
    assert second.stop_reason == "frontier_empty"
    assert second.next_ready_at is None
    assert len(second.documents) == 1
    assert pages.calls == ["https://docs.example/a", "https://docs.example/b"]


def test_other_hosts_progress_while_first_host_waits():
    engine, _ = crawler("https://a.example/1", "https://a.example/2", "https://b.example/1")
    result = acquire_game_batch(engine, now=100)
    assert [d.canonical_url for d in result.documents] == [
        "https://a.example/1", "https://b.example/1",
    ]
    assert result.next_ready_at == 101
    assert result.steps == 2


def test_retry_after_is_visible_and_does_not_advance_clock():
    url = "https://a.example/retry"
    engine, pages = crawler(url, failures={url: 429})
    result = acquire_game_batch(engine, now=100)
    assert result.documents == ()
    assert result.stop_reason == "deferred"
    assert result.next_ready_at == 107
    assert len(pages.calls) == 1
    assert acquire_game_batch(engine, now=106).steps == 0
    assert len(acquire_game_batch(engine, now=107).documents) == 1


@pytest.mark.parametrize("limit,reason", [("max_documents", "document_limit"), ("max_steps", "step_limit")])
def test_turn_limits_leave_unprocessed_work_queued(limit, reason):
    engine, pages = crawler("https://a.example/1", "https://b.example/2", delay=0)
    result = acquire_game_batch(engine, now=100, **{limit: 1})
    assert result.stop_reason == reason
    assert result.pending_sources == 1 and len(pages.calls) == 1
    assert len(acquire_game_documents(engine, now=100)) == 1


def test_budget_exhaustion_is_distinct_from_empty_and_delayed():
    engine, pages = crawler("https://a.example/a", budget=CrawlBudget(max_requests=0))
    result = acquire_game_batch(engine, now=100)
    assert result.stop_reason == "budget_exhausted"
    assert result.pending_sources == 1
    assert not pages.calls


def test_rejected_proposals_are_bounded_even_for_infinite_stream():
    engine, _ = crawler()
    consumed = []
    def rejected():
        while True:
            consumed.append(1)
            yield GameSource("http://127.0.0.1/private", "", "", "", "")
    assert queue_game_sources(engine, rejected(), max_enqueues=3) == ()
    assert len(consumed) == 3


def test_checkpoint_recovery_preserves_cooldown_and_indexed_continuation():
    engine, pages = crawler("https://docs.example/a", "https://docs.example/b")
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    first = builder.resume_acquisition(engine, engine="godot", now=100, authorized=True)
    engine.checkpoint("game-research")
    restarted = CrawlEngine(pages, policy=engine.policy, store=engine.store)
    assert restarted.restore("game-research")
    restarted.install_robots("https://docs.example", "User-agent: *\nAllow: /")
    second = builder.resume_acquisition(restarted, engine="godot", now=101, authorized=True)
    assert first.stop_reason == "deferred" and second.stop_reason == "frontier_empty"
    hits = builder.knowledge.search("movement collision", engine="godot")
    assert {hit.source_url for hit in hits} == {"https://docs.example/a", "https://docs.example/b"}


def test_builder_bounds_existing_frontier_before_fetch_and_index():
    engine, pages = crawler(*(f"https://docs.example/{n}" for n in range(5)), delay=0)
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    result = builder.resume_acquisition(engine, engine="web", now=100,
                                        authorized=True, max_documents=2)
    assert result.stop_reason == "document_limit" and len(pages.calls) == 2
    assert builder.knowledge.db.execute("SELECT COUNT(*) FROM game_knowledge_sources").fetchone()[0] == 2
    assert engine.pending_count == 3


def test_discovery_shares_seed_ceiling_with_official_docs():
    engine, _ = crawler(delay=0)
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    suggested = (GameSource("https://other.example/a", "", "", "", ""),)
    with patch("skeleton.ai.webcrawler.game_builder_knowledge_runtime.discover_game_research", return_value=suggested):
        builder.discover_and_acquire(engine, lambda: None, genre="platformer", engine="web",
                                     now=100, authorized=True, max_sources=1, max_steps=1)
    assert len(engine._seen | engine._queued) == 1


@pytest.mark.parametrize("kwargs", [
    {"now": float("nan")}, {"now": True}, {"max_steps": True},
    {"max_steps": 0}, {"max_documents": 1.5}, {"max_documents": 0},
])
def test_invalid_batch_is_rejected_before_fetch(kwargs):
    engine, pages = crawler("https://a.example/a")
    with pytest.raises(ValueError):
        acquire_game_batch(engine, **({"now": 100} | kwargs))
    assert not pages.calls and engine.pending_count == 1


def test_resume_requires_authorization_before_any_work():
    engine, pages = crawler("https://a.example/a")
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    with pytest.raises(PermissionError):
        builder.resume_acquisition(engine, engine="web", now=100, authorized=False)
    assert not pages.calls


def test_invalid_discovery_budget_fails_before_transport_or_seeding():
    engine, pages = crawler()
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    with patch("skeleton.ai.webcrawler.game_builder_knowledge_runtime.discover_game_research") as discover:
        with pytest.raises(ValueError):
            builder.discover_and_acquire(engine, lambda: None, genre="platformer", engine="web",
                                         now=100, authorized=True, max_steps=0)
        discover.assert_not_called()
    assert not pages.calls and engine.pending_count == 0


def test_prioritization_does_not_materialize_unbounded_input():
    consumed = []
    def candidates():
        while True:
            consumed.append(1)
            yield GameSource("https://a.example/a", "jump", "", "", "")
    with pytest.raises(ValueError):
        prioritize_game_sources(candidates(), genre="platformer", engine="web", max_sources=2)
    assert len(consumed) == 3
