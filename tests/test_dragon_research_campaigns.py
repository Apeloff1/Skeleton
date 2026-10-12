"""Reproducible Dragon research campaigns with exact owner and evidence lineage."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_discovery_facets import DiscoveryFacetIndex
from skeleton.ai.game_builder.dragon_discovery_mission import SourceMission
from skeleton.ai.game_builder.dragon_discovery_portfolio import (
    PortfolioAxis, PortfolioRequest,
)
from skeleton.ai.game_builder.dragon_research_campaigns import DiscoveryCampaigns
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore


@pytest.fixture
def campaign_studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path / "campaign.sqlite") as store:
        almanacs = DragonAlmanacs(store)
        owner = "studio"
        topic = almanacs.ensure_topic(
            owner, ("Sources", "Game Boy", "Original editor"), authorized=True)
        ids = {}
        for title in (
            "original-game-physics-collision",
            "original-game-physics-gravity",
            "original-game-quest-events",
            "original-game-quest-dialogue",
            "original-game-art-palette",
        ):
            url = canonical_source_url(f"https://{title}.example/guide")
            sid = "source-" + sha256(url.encode("utf-8")).hexdigest()
            body = {
                "source_id": sid, "url": url, "kind": "web_candidate",
                "rights": "not_assessed", "training_authorized": False,
                "discoveries": [{"catalog_id": "handheld", "line": 1,
                                 "headers": [title]}],
            }
            store.db.execute(
                "INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
                (owner, sid, canonical_json(body), canonical_digest(body)))
            store.db.execute(
                "INSERT INTO dragon_almanac_members VALUES(?,?,?)",
                (owner, topic, sid))
            ids[title] = sid
        SequentialAlmanacWorker(almanacs).seed(owner, authorized=True)
        store.db.commit()
        index = DiscoveryFacetIndex(almanacs)
        index.refresh(owner, authorized=True, limit=100)
        yield store, almanacs, topic, ids


def _request(include_rights=False):
    axes = [
        PortfolioAxis("physics", "physics collision", minimum=1, importance=10),
        PortfolioAxis("quests", "quest events", minimum=1, importance=8),
    ]
    if include_rights:
        axes.append(PortfolioAxis("rights", "rights licenses", minimum=1,
                                  importance=10))
    return PortfolioRequest(
        SourceMission("original game", scan_budget=100),
        tuple(axes), total_limit=5, per_axis_candidates=10,
        max_per_host=1, indexed=True)


def test_research_campaign_is_idempotent_and_never_self_approves(campaign_studio):
    store, almanacs, topic, ids = campaign_studio
    ledger = DiscoveryCampaigns(almanacs)
    first = ledger.record("studio", "gb-homebrew", _request(),
                          authorized=True, topic=topic)
    assert first["revision"] == 0 and not first["unchanged"]
    unchanged = ledger.record("studio", "gb-homebrew", _request(),
                              authorized=True, topic=topic)
    assert unchanged["revision"] == 0 and unchanged["unchanged"]
    view = ledger.inspect("studio", "gb-homebrew", authorized=True)
    assert view["revision_count"] == 1
    assert view["source_dependencies_current"] is True
    assert view["selected_added_since_previous"]
    assert not view["selected_removed_since_previous"]
    assert view["plan"]["selected"]
    assert not view["cryptographically_signed"]
    assert all(view[k] is False for k in (
        "crawl_authorized", "source_rights_approved",
        "training_authorized", "memory_promotion_authorized"))
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_discovery_campaigns"
    ).fetchone()[0] == 1
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_jobs WHERE state='pending'"
    ).fetchone()[0] == 5


def test_campaign_compare_and_swap_and_axis_gap_delta(campaign_studio):
    store, almanacs, topic, ids = campaign_studio
    ledger = DiscoveryCampaigns(almanacs)
    first = ledger.record("studio", "project", _request(),
                          authorized=True, topic=topic)
    with pytest.raises(ValueError, match="CAS parent"):
        ledger.record("studio", "project", _request(include_rights=True),
                      authorized=True, topic=topic)
    with pytest.raises(ValueError, match="CAS parent"):
        ledger.record("studio", "project", _request(include_rights=True),
                      authorized=True, topic=topic,
                      expected_parent="f"*64)
    second = ledger.record(
        "studio", "project", _request(include_rights=True), authorized=True,
        topic=topic, expected_parent=first["digest"])
    assert second["revision"] == 1
    assert second["discovery_gaps"] == ["rights"]
    view = ledger.inspect("studio", "project", authorized=True)
    assert view["revision_count"] == 2
    assert view["parent_digest"] == first["digest"]
    assert view["gap_delta_since_previous"]["rights"] == 0
    assert view["plan"]["uncovered_axes"] == ["rights"]
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_discovery_campaigns WHERE owner='studio'"
    ).fetchone()[0] == 2


def test_change_of_source_digest_marks_recorded_proposal_stale(campaign_studio):
    store, almanacs, topic, ids = campaign_studio
    ledger = DiscoveryCampaigns(almanacs)
    ledger.record("studio", "drift", _request(), authorized=True, topic=topic)
    before = ledger.inspect("studio", "drift", authorized=True)
    sid = before["plan"]["selected"][0]["source_id"]
    body = json.loads(store.db.execute(
        "SELECT body FROM dragon_almanac_sources WHERE owner='studio' AND source=?",
        (sid,)).fetchone()[0])
    body["discoveries"][0]["headers"].append("Changed observed title")
    store.db.execute(
        "UPDATE dragon_almanac_sources SET body=?,digest=? "
        "WHERE owner='studio' AND source=?",
        (canonical_json(body), canonical_digest(body), sid))
    store.db.commit()
    after = ledger.inspect("studio", "drift", authorized=True)
    assert not after["source_dependencies_current"]
    assert after["stale_source_ids"] == [sid]
    assert after["training_authorized"] is False


def test_campaign_integrity_rejects_forged_history_without_partial_revision(campaign_studio):
    store, almanacs, topic, ids = campaign_studio
    ledger = DiscoveryCampaigns(almanacs)
    ledger.record("studio", "tamper", _request(), authorized=True, topic=topic)
    store.db.execute(
        "UPDATE dragon_discovery_campaigns SET body='{}' "
        "WHERE owner='studio' AND campaign='tamper'")
    store.db.commit()
    with pytest.raises(ValueError, match="lineage"):
        ledger.inspect("studio", "tamper", authorized=True)
    with pytest.raises(ValueError, match="lineage"):
        ledger.record("studio", "tamper", _request(include_rights=True),
                      authorized=True, topic=topic)
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_discovery_campaigns"
    ).fetchone()[0] == 1


def test_campaigns_isolate_owners_and_validate_cas(campaign_studio):
    _, almanacs, topic, ids = campaign_studio
    ledger = DiscoveryCampaigns(almanacs)
    ledger.record("studio", "private-plan", _request(),
                  authorized=True, topic=topic)
    with pytest.raises(PermissionError):
        ledger.inspect("studio", "private-plan", authorized=False)
    with pytest.raises(ValueError, match="unknown owner campaign"):
        ledger.inspect("other", "private-plan", authorized=True)
    with pytest.raises(ValueError, match="unknown owner topic"):
        ledger.record("other", "private-plan", _request(),
                      authorized=True, topic=topic)
    with pytest.raises(ValueError, match="expected"):
        ledger.record("studio", "other-plan", _request(), authorized=True,
                      topic=topic, expected_parent="bad parent")


def test_campaign_policy_stage_progress_invalidates_old_proposal(campaign_studio):
    store, almanacs, topic, ids = campaign_studio
    ledger = DiscoveryCampaigns(almanacs)
    ledger.record("studio", "stage-fence", _request(),
                  authorized=True, topic=topic)
    first = ledger.inspect("studio", "stage-fence", authorized=True)
    sid = first["plan"]["selected"][0]["source_id"]
    store.db.execute(
        """UPDATE dragon_almanac_jobs SET stage=1,state='pending'
           WHERE owner='studio' AND source=?""", (sid,))
    store.db.commit()
    stale = ledger.inspect("studio", "stage-fence", authorized=True)
    assert stale["source_dependencies_current"] is False
    assert stale["stale_source_ids"] == [sid]
    assert stale["memory_promotion_authorized"] is False


def test_campaign_rejects_planned_url_that_differs_from_canonical_store(campaign_studio):
    _, almanacs, topic, ids = campaign_studio
    ledger = DiscoveryCampaigns(almanacs)
    original = ledger.portfolio.build
    def forged(owner, request, *, authorized, topic=None):
        result = original(owner, request, authorized=authorized, topic=topic)
        from copy import deepcopy
        changed = deepcopy(result)
        changed["selected"][0]["url"] = "https://attacker.example/not-the-source"
        return changed
    ledger.portfolio.build = forged
    with pytest.raises(ValueError, match="URL differs"):
        ledger.record("studio", "url-bound", _request(),
                      authorized=True, topic=topic)
    assert ledger.db.execute(
        "SELECT COUNT(*) FROM dragon_discovery_campaigns"
    ).fetchone()[0] == 0
