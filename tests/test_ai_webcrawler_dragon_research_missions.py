"""Tests for broad research mission planning."""
import pytest
from skeleton.ai.webcrawler.dragon_research_missions import (
    ResearchInterest, MissionPolicy, plan_research,
)
from skeleton.ai.webcrawler.dragon_research_discovery import ResearchSource


def test_wide_scope_sources():
    mission = plan_research(
        "alice", (ResearchInterest("quantum materials", 0.9),),
        authorized=True,
    )
    assert {q.sources[0] for q in mission.queries} == {
        ResearchSource.WIKIPEDIA, ResearchSource.CROSSREF,
        ResearchSource.OPENALEX, ResearchSource.EUROPE_PMC,
    }


def test_geographic_search_requires_separate_consent():
    interests = (ResearchInterest("historic museums", 0.8),)
    policy = MissionPolicy(include_places=True)
    without = plan_research(
        "alice", interests, authorized=True, policy=policy,
    )
    with_places = plan_research(
        "alice", interests, authorized=True,
        geographic_consent=True, policy=policy,
    )
    assert all(
        q.sources[0] is not ResearchSource.OPENSTREETMAP
        for q in without.queries
    )
    assert any(
        q.sources[0] is ResearchSource.OPENSTREETMAP
        for q in with_places.queries
    )


def test_sensitive_interests_are_excluded():
    mission = plan_research(
        "alice", (
            ResearchInterest("medical records", 0.9, sensitive=True),
            ResearchInterest("machine learning", 0.8),
        ), authorized=True,
    )
    assert all(q.terms == "machine learning" for q in mission.queries)


def test_no_sensitive_only_mission():
    with pytest.raises(ValueError):
        plan_research(
            "alice", (ResearchInterest("private health", 0.9, True),),
            authorized=True,
        )


def test_deterministic_fingerprint():
    interests = (
        ResearchInterest("biology", 0.5),
        ResearchInterest("physics", 0.9),
    )
    first = plan_research("alice", interests, authorized=True)
    second = plan_research("alice", tuple(reversed(interests)),
                           authorized=True)
    assert first == second


def test_duplicate_topics_are_merged_by_priority():
    mission = plan_research(
        "alice", (
            ResearchInterest("Biology", 0.3),
            ResearchInterest(" biology ", 0.8),
        ), authorized=True,
    )
    assert len(mission.queries) == 4


def test_query_budget():
    mission = plan_research(
        "alice", (
            ResearchInterest("biology", 0.5),
            ResearchInterest("physics", 0.9),
        ), authorized=True,
        policy=MissionPolicy(max_queries=5),
    )
    assert len(mission.queries) == 5
    assert mission.queries[0].terms == "physics"


def test_authorization_required():
    with pytest.raises(PermissionError):
        plan_research(
            "alice", (ResearchInterest("science", 0.9),),
            authorized=False,
        )
