"""Incremental Dragon discovery facets: pagination, indexing and isolation."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.contracts import canonical_json, canonical_digest
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_discovery_facets import DiscoveryFacetIndex
from skeleton.ai.game_builder.dragon_discovery_mission import (
    MissionSourceScout, SourceMission,
)
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore


@pytest.fixture
def indexed_studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path / "facet.sqlite") as store:
        almanacs = DragonAlmanacs(store)
        topic = almanacs.ensure_topic(
            "studio", ("Sources", "Game Boy", "Original platformers"),
            authorized=True,
        )
        rows = []
        for i in range(60):
            part = "platforming-physics" if i == 59 else "other-subject"
            url = canonical_source_url(
                f"https://ref{i:04d}.example/{part}-{i:03d}")
            sid = "source-" + sha256(url.encode("utf-8")).hexdigest()
            body = {
                "source_id": sid, "url": url, "kind": "web_candidate",
                "rights": "not_assessed", "training_authorized": False,
                "discoveries": [
                    {"catalog_id": "archive", "line": i+1,
                     "headers": ["Physics" if i == 59 else "Graphics"]},
                ],
            }
            store.db.execute(
                "INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
                ("studio", sid, canonical_json(body), canonical_digest(body)))
            store.db.execute(
                "INSERT INTO dragon_almanac_members VALUES(?,?,?)",
                ("studio", topic, sid))
            rows.append((sid, url))
        SequentialAlmanacWorker(almanacs).seed("studio", authorized=True)
        store.db.commit()
        yield store, almanacs, topic, rows


def _populate(index, owner="studio", page=13):
    cursor = None
    receipts = []
    for i in range(100):
        result = index.refresh(owner, authorized=True, limit=page,
                               after_source=cursor)
        receipts.append(result)
        cursor = result["next_source"]
        if cursor is None:
            return receipts
    raise AssertionError("pagination never completed")


def test_resumable_index_reaches_matching_sources_outside_sha_prefix(indexed_studio):
    store, almanacs, topic, rows = indexed_studio
    scout = MissionSourceScout(almanacs)
    index = DiscoveryFacetIndex(almanacs)
    before = index.health("studio", authorized=True)
    assert before["policy_stage_sources"] == 60
    assert before["source_digest_current_indexed"] == 0
    cursor_pages = _populate(index)
    assert len(cursor_pages) > 2
    assert sum(x["processed"] for x in cursor_pages) == 60
    assert index.health("studio", authorized=True)["coverage_complete"]
    target = next(sid for sid,url in rows if "platforming-physics" in url)
    result = scout.propose(
        "studio", SourceMission("platforming physics", limit=1, scan_budget=1),
        authorized=True, topic=topic, indexed=True)
    assert [x["source_id"] for x in result["selection"]] == [target]
    assert result["index_health"]["coverage_complete"] is True
    assert result["scanned"] == 1
    assert result["queue_modified"] is False
    assert store.db.execute("SELECT COUNT(*) FROM dragon_almanac_jobs "
                            "WHERE state='pending'").fetchone()[0] == 60
    assert sum(x["updated"] for x in _populate(index)) == 0


def test_partial_index_honestly_discloses_missing_coverage(indexed_studio):
    _, almanacs, topic, rows = indexed_studio
    index = DiscoveryFacetIndex(almanacs)
    first = index.refresh("studio", authorized=True, limit=4)
    assert first["next_source"]
    result = MissionSourceScout(almanacs).propose(
        "studio", SourceMission("graphics", limit=2, scan_budget=3),
        authorized=True, topic=topic, indexed=True)
    assert result["indexed_search"] is True
    assert result["index_health"]["unindexed_or_changed"] == 56
    assert result["scan_truncated"] is True
    assert result["ranking_scope"] == "discovery_metadata_only_not_verified_content"


def test_source_digest_drift_requires_refresh_before_index_match(indexed_studio):
    store, almanacs, _, rows = indexed_studio
    index = DiscoveryFacetIndex(almanacs)
    _populate(index)
    target, url = next((sid, url) for sid,url in rows
                       if "platforming-physics" in url)
    record = json.loads(store.db.execute(
        "SELECT body FROM dragon_almanac_sources WHERE owner='studio' AND source=?",
        (target,)).fetchone()[0])
    record["discoveries"][0]["headers"] = ["Physics", "Collision", "Game Boy"]
    store.db.execute(
        """UPDATE dragon_almanac_sources SET body=?,digest=?
           WHERE owner='studio' AND source=?""",
        (canonical_json(record), canonical_digest(record), target))
    store.db.commit()
    health = index.health("studio", authorized=True)
    assert health["unindexed_or_changed"] == 1
    missing = MissionSourceScout(almanacs).propose(
        "studio", SourceMission("platforming physics", limit=5),
        authorized=True, indexed=True)
    assert target not in {x["source_id"] for x in missing["selection"]}
    _populate(index)
    # Re-indexing metadata alone must NOT repair the fenced policy-input
    # contract. An authenticated independent stage must reconcile that digest.
    assert index.health("studio", authorized=True)["stale_job_inputs"] == 1
    blocked = MissionSourceScout(almanacs).propose(
        "studio", SourceMission("collision physics", limit=5),
        authorized=True, indexed=True)
    assert target not in {x["source_id"] for x in blocked["selection"]}
    store.db.execute(
        "UPDATE dragon_almanac_jobs SET input_digest=? "
        "WHERE owner='studio' AND source=? AND stage=0",
        (canonical_digest(record), target))
    store.db.commit()
    restored = MissionSourceScout(almanacs).propose(
        "studio", SourceMission("collision physics", limit=5),
        authorized=True, indexed=True)
    assert target in {x["source_id"] for x in restored["selection"]}
    assert index.health("studio", authorized=True)["coverage_complete"]


def test_corrupt_source_rolls_back_entire_refresh_page(indexed_studio):
    store, almanacs, _, rows = indexed_studio
    index = DiscoveryFacetIndex(almanacs)
    sid = sorted(sid for sid,_ in rows)[0]
    store.db.execute(
        "UPDATE dragon_almanac_sources SET digest=? "
        "WHERE owner='studio' AND source=?", ("f" * 64, sid))
    store.db.commit()
    with pytest.raises(ValueError, match="corrupt canonical"):
        index.refresh("studio", authorized=True, limit=20)
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_discovery_facet_records"
    ).fetchone()[0] == 0


def test_facet_index_is_owner_isolated_and_bounded(indexed_studio):
    store, almanacs, topic, rows = indexed_studio
    index = DiscoveryFacetIndex(almanacs)
    with pytest.raises(PermissionError):
        index.refresh("studio", authorized=False)
    with pytest.raises(ValueError):
        index.refresh("studio", authorized=True, limit=True)
    with pytest.raises(ValueError):
        index.refresh("studio", authorized=True, limit=1001)
    result = index.refresh("other", authorized=True)
    assert result["processed"] == 0
    assert index.health("other", authorized=True)["policy_stage_sources"] == 0
    with pytest.raises(ValueError, match="unknown owner topic"):
        index.matching_rows("other", frozenset({"platforming"}),
                            authorized=True, limit=10, topic=topic)
    with pytest.raises(ValueError):
        index.matching_rows("studio", frozenset(), authorized=True, limit=10)
    assert store.db.execute("SELECT COUNT(*) FROM dragon_discovery_facet_terms"
                            " WHERE owner='other'").fetchone()[0] == 0


def test_receipt_header_tokens_are_indexed_without_knowledge_approval(indexed_studio):
    store, almanacs, _, rows = indexed_studio
    index = DiscoveryFacetIndex(almanacs)
    sid, url = rows[0]
    origin = {"repository": "archive/gb-dev", "headers": [
        "Deterministic raycast renderer"]}
    candidate = {
        "url": url, "source_id": sid,
        "discoveries": [origin],
    }
    claim = {
        "normalized_source_id": sid, "normalized_url": url,
        "candidate": candidate, "supplement_digest": "a" * 64,
        "authority": "unreviewed_discovery_only",
    }
    store.db.execute(
        "INSERT INTO dragon_almanac_supplement_receipts_v2 VALUES(?,?,?,?,?,?)",
        ("studio", sid, sid, "a" * 64,
         canonical_json(claim), canonical_digest(claim)))
    store.db.commit()
    _populate(index)
    result = MissionSourceScout(almanacs).propose(
        "studio", SourceMission("raycast renderer", limit=5),
        authorized=True, indexed=True)
    assert sid in {x["source_id"] for x in result["selection"]}
    assert all(x["training_authorized"] is False for x in result["selection"])
    assert all(x["network_authorized"] is False for x in result["selection"])


def test_weighted_index_prefers_goal_over_generic_era_metadata(indexed_studio):
    _, almanacs, _, rows = indexed_studio
    index = DiscoveryFacetIndex(almanacs)
    _populate(index)
    # Query weights are explicit and the fetch is advisory; a broad era token
    # cannot evict the only exact high-value objective from a tiny scan budget.
    result = MissionSourceScout(almanacs).propose(
        "studio", SourceMission("platforming physics", genre="graphics",
                                 limit=1, scan_budget=1),
        authorized=True, indexed=True)
    assert len(result["selection"]) == 1
    assert "platforming-physics" in result["selection"][0]["url"]
    with pytest.raises(ValueError, match="term weights"):
        index.matching_rows("studio", frozenset({"physics"}), authorized=True,
                            limit=3, weights={"physics": True})
    with pytest.raises(ValueError, match="term weights"):
        index.matching_rows("studio", frozenset({"physics"}), authorized=True,
                            limit=3, weights={"unrelated": 12})
