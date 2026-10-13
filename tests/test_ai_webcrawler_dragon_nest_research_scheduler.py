"""Research intents are not source permissions, XP, or autonomous crawls."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.webcrawler.dragon_nest_progression import (
    AcquiredKnowledge, feed_parent, new_nest,
)
from skeleton.ai.webcrawler.dragon_nest_research_scheduler import (
    IdleResearchPolicy, ResearchLead, plan_idle_research,
)
from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample

T0 = "2026-10-12T12:00:00Z"
T1 = "2026-10-12T12:10:00Z"


def adult():
    nest = new_nest(
        "owner-a", ("source-a", "source-b"),
        focus_tags=("game-code",), adjacent_tags=("software-debug",), at=T0,
    )
    for source, sha in (("source-a", "a" * 64), ("source-b", "b" * 64)):
        nest = feed_parent(nest, source, content_sha256=sha, at=T0,
                           authorized=True, reviewed=True, lawful=True)
    return nest


def hardware(*, memory=512 * 1024 * 1024, pressure=0.1, charging=True, age=0):
    return HardwareSample(memory, 8, pressure, 0.75, charging, False, 1000 - age)


def lead(name, lane="article", *, tags=("game-code",), age="2026-10-12T12:05:00Z",
         published="2026-10-11T08:00:00Z", digest=""):
    domain = "www.youtube.com" if lane == "video" else "docs.example.org"
    return ResearchLead(name, f"https://{domain}/research/{name}", tags,
                        lane, age, digest, published if lane == "updates" else None)


def plan(nest=None, leads=(), sample=None, **kw):
    return plan_idle_research(
        nest if nest is not None else adult(), tuple(leads),
        sample if sample is not None else hardware(),
        at=kw.pop("at", T1), idle_since=kw.pop("idle_since", T0),
        now_seconds=kw.pop("now_seconds", 1000),
        consented=kw.pop("consented", True),
        authorized=kw.pop("authorized", True), **kw,
    )


def test_empty_egg_nest_cannot_schedule_idle_jobs():
    nest = new_nest("owner-a", ("s",), focus_tags=("game-code",), at=T0)
    result = plan(nest, [lead("a")])
    assert result.assignments == ()
    assert result.reason == "three_hatchlings_not_unlocked"


@pytest.mark.parametrize("override,reason", [
    ({"authorized": False}, "authorization_or_consent_absent"),
    ({"consented": False}, "authorization_or_consent_absent"),
    ({"idle_since": "2026-10-12T12:09:00Z"}, "foreground_or_insufficient_idle_time"),
    ({"idle_since": "2026-10-12T12:11:00Z"}, "foreground_or_insufficient_idle_time"),
])
def test_no_background_work_without_trusted_idle_and_consent(override, reason):
    result = plan(leads=[lead("a")], **override)
    assert not result.assignments and result.reason == reason


@pytest.mark.parametrize("sample", [
    hardware(memory=1024),
    hardware(pressure=0.99),
    hardware(age=10),
    HardwareSample(512 * 1024 * 1024, 8, 0.1, .05, False, False, 1000),
])
def test_resource_pressure_suspends_all_hatchlings(sample):
    result = plan(leads=[lead("a")], sample=sample)
    assert result.assignments == ()
    assert result.reason != "untrusted_intents_require_separate_worker_admission"


def test_three_lanes_receive_distinct_fair_and_bounded_intents():
    candidates = (
        *(lead(f"article-{i}") for i in range(20)),
        *(lead(f"video-{i}", "video", tags=("software-debug",)) for i in range(4)),
        *(lead(f"updated-{i}", "updates") for i in range(4)),
    )
    result = plan(leads=candidates)
    assert len(result.assignments) == 6
    assert [x.lane for x in result.assignments].count("article") == 2
    assert [x.lane for x in result.assignments].count("video") == 2
    assert [x.lane for x in result.assignments].count("updates") == 2
    assert all(x.evidence_only and not x.execution_authorized
               and not x.memory_promotion_authorized for x in result.assignments)
    assert not result.execution_authorized and not result.memory_promotion_authorized
    assert result.requires_worker_admission
    assert result == plan(leads=candidates)


def test_focus_beats_adjacent_but_adjacent_is_still_admitted():
    result = plan(leads=[
        lead("adjacent", tags=("software-debug",)),
        lead("primary", tags=("game-code",)),
    ])
    assert tuple(x.source_id for x in result.assignments) == ("primary", "adjacent")
    assert result.assignments[0].importance == "task"
    assert result.assignments[1].importance == "adjacent"


def test_stale_unknown_and_duplicate_candidates_never_mint_work():
    candidates = (
        lead("a", digest="a" * 64),
        lead("a", digest="a" * 64),
        lead("irrelevant", tags=("tourism",)),
        lead("stale", age="2020-01-01T00:00:00Z"),
        lead("future", age="2026-10-13T00:00:00Z"),
        lead("no-date", "updates", published="2020-01-01T00:00:00Z"),
    )
    result = plan(leads=candidates)
    assert len(result.assignments) == 1
    assert result.assignments[0].source_id == "a"
    assert result.suppressed_duplicates == 1


def test_known_source_version_cannot_be_requeued_solely_from_digest_hint():
    from skeleton.ai.webcrawler.dragon_nest_progression import learn_when_idle
    nest = adult()
    digest = "c" * 64
    evidence = AcquiredKnowledge(
        "a", digest, T1, ("game-code",), True, True, .95,
        "2026-10-11T00:00:00Z", "article",
    )
    nest = learn_when_idle(nest, "article", evidence, at=T1,
                           idle_since=T0, consented=True,
                           background_allowed=True, owner_authorized=True)
    result = plan(nest, [lead("a", digest=digest),
                         lead("b", digest="d" * 64)])
    assert [a.source_id for a in result.assignments] == ["b"]
    assert result.suppressed_duplicates == 1


@pytest.mark.parametrize("kwargs", [
    {"lane": "video", "domain": "docs"},
    {"lane": "article", "domain": "video"},
])
def test_no_video_article_mislabel(kwargs):
    domain = "www.youtube.com" if kwargs["domain"] == "video" else "docs.example.org"
    with pytest.raises(ValueError, match="specialist"):
        ResearchLead("x", "https://" + domain + "/x", ("game-code",),
                     kwargs["lane"], T1)


@pytest.mark.parametrize("url", [
    "http://docs.example.org/x",
    "https://user:pass@docs.example.org/x",
    "https://localhost/private",
    "https://127.0.0.1/private",
    "https://169.254.169.254/metadata",
    "https://docs.example.org/x?utm_source=hidden",
    "https://docs.example.org/x#anchor",
])
def test_leads_reject_unsafe_identity_syntax(url):
    with pytest.raises(ValueError):
        ResearchLead("x", url, ("game-code",), "article", T1)


def test_planning_budget_admits_no_more_than_typed_limits():
    items = tuple(lead(str(i)) for i in range(32))
    policy = IdleResearchPolicy(max_per_lane=1, max_assignments=1)
    assert len(plan(leads=items, policy=policy).assignments) == 1
    with pytest.raises(ValueError, match="bounded"):
        plan(leads=items, policy=IdleResearchPolicy(max_leads=10))
