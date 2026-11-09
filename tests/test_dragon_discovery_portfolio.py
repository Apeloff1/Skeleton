"""Original game project knowledge portfolio: real indexed integration."""
from __future__ import annotations

from hashlib import sha256

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_discovery_facets import DiscoveryFacetIndex
from skeleton.ai.game_builder.dragon_discovery_mission import SourceMission
from skeleton.ai.game_builder.dragon_discovery_portfolio import (
    MissionPortfolio, PortfolioAxis, PortfolioRequest,
)
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore


@pytest.fixture
def game_studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"portfolio.sqlite") as store:
        a = DragonAlmanacs(store)
        topic = a.ensure_topic(
            "studio", ("Sources", "Original games", "Game Boy"),
            authorized=True)
        titles = [
            "original-game-physics-quest-rights",
            "original-game-physics-collision",
            "original-game-physics-gravity",
            "original-game-quest-events",
            "original-game-quest-dialogue",
            "original-game-rights-licenses",
            "original-game-rights-attribution",
            "original-game-graphics-palette",
        ]
        for i, title in enumerate(titles):
            url = canonical_source_url(f"https://research{i}.example/{title}")
            sid = "source-" + sha256(url.encode()).hexdigest()
            body = {
                "source_id": sid, "url": url, "kind": "web_candidate",
                "rights": "not_assessed", "training_authorized": False,
                "discoveries": [{"catalog_id": "game-engine",
                                 "line": i+1, "headers": [title]}],
            }
            store.db.execute(
                "INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
                ("studio", sid, canonical_json(body), canonical_digest(body)))
            store.db.execute(
                "INSERT INTO dragon_almanac_members VALUES(?,?,?)",
                ("studio", topic, sid))
        SequentialAlmanacWorker(a).seed("studio", authorized=True)
        store.db.commit()
        yield store,a,topic


def _request(*, total=7, indexed=True, per_axis=10):
    return PortfolioRequest(
        SourceMission("original game", scan_budget=100, limit=10),
        (PortfolioAxis("physics", "physics and collision", minimum=2, importance=10),
         PortfolioAxis("quests", "quest event narrative", minimum=2, importance=7),
         PortfolioAxis("rights", "rights licenses", minimum=2, importance=10)),
        total_limit=total, per_axis_candidates=per_axis,
        max_per_host=1, indexed=indexed,
    )


def test_portfolio_covers_multiple_engine_axes_without_duplicate_sources(game_studio):
    store,a,topic = game_studio
    idx = DiscoveryFacetIndex(a)
    assert idx.refresh("studio", authorized=True, limit=100)["processed"] == 8
    result = MissionPortfolio(a).build(
        "studio", _request(), authorized=True, topic=topic)
    assert result == MissionPortfolio(a).build(
        "studio", _request(), authorized=True, topic=topic)
    assert result["uncovered_axes"] == []
    assert result["indexed_corpus_current"] is True
    assert len(result["selected"]) <= 7
    assert all(x["proposed_leads"] >= 2 for x in result["axis_coverage"])
    assert len({x["source_id"] for x in result["selected"]}) == len(result["selected"])
    assert len({x["host"] for x in result["selected"]}) == len(result["selected"])
    assert any(len(x["axis_scores"]) >= 2 for x in result["selected"])
    assert all(x["training_authorized"] is False and not x["crawler_authorized"]
               for x in result["selected"])
    assert result["acquisition_queue_modified"] is False
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_jobs WHERE state='pending'"
    ).fetchone()[0] == 8


def test_portfolio_discloses_unmet_axes_and_partial_index(game_studio):
    _, a, _ = game_studio
    portfolio = MissionPortfolio(a)
    before = portfolio.build("studio", _request(total=1), authorized=True)
    assert before["indexed_corpus_current"] is False
    assert len(before["selected"]) <= 1
    assert before["uncovered_axes"]
    DiscoveryFacetIndex(a).refresh("studio", authorized=True, limit=100)
    after = portfolio.build("studio", _request(total=1), authorized=True)
    assert after["indexed_corpus_current"] is True
    assert after["uncovered_axes"]
    assert all(x["coverage_state"] in {
        "candidate_quota_met_not_evidence_approved", "discovery_gap"}
        for x in after["axis_coverage"])


def test_portfolio_fails_closed_for_other_owner_and_untrusted_request(game_studio):
    _, a, topic = game_studio
    planner = MissionPortfolio(a)
    with pytest.raises(PermissionError):
        planner.build("studio", _request(), authorized=False)
    with pytest.raises(ValueError, match="unknown owner topic"):
        planner.build("other", _request(), authorized=True, topic=topic)
    blank = planner.build("other", _request(), authorized=True)
    assert blank["selected"] == []
    assert len(blank["uncovered_axes"]) == 3
    assert blank["training_authorized"] is False


def test_portfolio_contract_rejects_infinite_and_ambiguous_workloads():
    base = SourceMission("original game")
    with pytest.raises(ValueError):
        PortfolioAxis("Bad Axis", "mechanics")
    with pytest.raises(ValueError):
        PortfolioAxis("physics", "  physics  ")
    with pytest.raises(ValueError):
        PortfolioAxis("physics", "physics", minimum=True)
    with pytest.raises(ValueError):
        PortfolioAxis("physics", "physics", importance=11)
    with pytest.raises(ValueError):
        PortfolioRequest(base, ())
    with pytest.raises(ValueError):
        PortfolioRequest(base, (PortfolioAxis("same","physics"),
                                PortfolioAxis("same","physics")))
    with pytest.raises(ValueError):
        PortfolioRequest(base, (PortfolioAxis("physics","physics"),),
                         indexed=1)
    with pytest.raises(ValueError):
        PortfolioRequest(base, (PortfolioAxis("physics","physics"),),
                         total_limit=101)
    with pytest.raises(ValueError):
        PortfolioRequest(base, (PortfolioAxis("physics","physics"),),
                         max_per_host=0)


def test_low_budget_portfolio_always_keeps_rights_and_promotion_closed(game_studio):
    _,a,_ = game_studio
    plan = MissionPortfolio(a).build(
        "studio", _request(indexed=False, total=3, per_axis=1),
        authorized=True)
    assert plan["indexed_search"] is False
    assert plan["indexed_corpus_current"] is None
    assert plan["source_use_authorized"] is False
    assert plan["memory_promotion_authorized"] is False
    assert plan["training_authorized"] is False
    assert plan["portfolio_authority"] == "unreviewed_discovery_metadata_only"


def test_generic_project_labels_cannot_fabricate_axis_specific_coverage(game_studio):
    _,a,_ = game_studio
    DiscoveryFacetIndex(a).refresh("studio", authorized=True, limit=100)
    plan = MissionPortfolio(a).build(
        "studio", _request(), authorized=True)
    for candidate in plan["selected"]:
        for axis in candidate["axis_scores"]:
            if axis == "physics":
                assert "physics" in candidate["url"]
            elif axis == "quests":
                assert "quest" in candidate["url"]
            elif axis == "rights":
                assert "rights" in candidate["url"]
    with pytest.raises(ValueError, match="distinctive"):
        MissionPortfolio(a).build(
            "studio", PortfolioRequest(
                SourceMission("original game", limit=10, scan_budget=100),
                (PortfolioAxis("copy", "original game", minimum=2),)),
            authorized=True)
