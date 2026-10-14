"""Catalog and idle research integration regression tests."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_video_catalog import CatalogPolicy, ingest_video_catalog
from skeleton.ai.webcrawler.dragon_video_history import DragonVideoHistory
from skeleton.ai.webcrawler.dragon_idle_planner import IdleVideoPlanner, IdleVideoPolicy
from skeleton.ai.webcrawler.dragon_idle_research import (
    ResearchConsent, prepare_idle_video_research,
)
from skeleton.ai.webcrawler.dragon_interest_signals import InterestSignal, SignalKind


def row(url, title="Video", tags=("science",), provider="trusted"):
    return {"url": url, "title": title, "tags": tags, "provider": provider}


def test_catalog_is_consent_bound_deterministic_and_deduplicated():
    rows = (row("https://example.org/watch?v=2", "B"),
            row("https://example.org/watch?v=1", "A"),
            row("https://example.org/watch?v=1", "A"),
            row("https://127.0.0.1/video", "Private"))
    with pytest.raises(PermissionError):
        ingest_video_catalog(rows)
    first = ingest_video_catalog(rows, authorized=True)
    second = ingest_video_catalog(tuple(reversed(rows)), authorized=True)
    assert first.candidates == second.candidates
    assert first.fingerprint == second.fingerprint
    assert first.accepted == 2
    assert first.rejected == 1


def test_catalog_provider_allowlist_and_budgets():
    receipt = ingest_video_catalog(
        (row("https://example.org/watch?v=1", provider="untrusted"),),
        authorized=True, policy=CatalogPolicy(allow_providers=("trusted",)),
    )
    assert receipt.accepted == 0 and receipt.rejected == 1
    with pytest.raises(ValueError, match="budget"):
        ingest_video_catalog((row("https://example.org/1"),
                              row("https://example.org/2")),
                             authorized=True, policy=CatalogPolicy(max_candidates=1))


def test_idle_pipeline_requires_explicit_consent_and_idle_time():
    history = DragonVideoHistory(sqlite3.connect(":memory:"))
    history.record("owner", "https://example.org/watch?v=1", "Science",
                   watched_at=100, duration_ms=1000, watched_ms=900,
                   tags=("science",), consent=True)
    planner = IdleVideoPlanner(IdleVideoPolicy(min_idle_seconds=30))
    planner.activity(100)
    signals = (InterestSignal("s1", SignalKind.LIKE, ("science",), 100,
                              consent=True),)
    rows = (row("https://example.org/watch?v=2", "New science"),)
    consent = ResearchConsent(history=True, signals=True, catalog=True,
                              discovery=True)
    with pytest.raises(PermissionError):
        prepare_idle_video_research(
            owner="owner", now=140, history=history, signals=signals,
            catalog_rows=rows, planner=planner, consent=ResearchConsent(),
        )
    before_idle = prepare_idle_video_research(
        owner="owner", now=120, history=history, signals=signals,
        catalog_rows=rows, planner=planner, consent=consent,
    )
    assert before_idle.awaiting_approval == 0
    report = prepare_idle_video_research(
        owner="owner", now=140, history=history, signals=signals,
        catalog_rows=rows, planner=planner, consent=consent,
    )
    assert report.awaiting_approval == 1
    assert report.proposals[0].requires_approval
    assert not report.ingestion_started
