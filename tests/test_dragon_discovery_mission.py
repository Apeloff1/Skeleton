"""Mission-driven source scouting is metadata-only, owner-isolated and bounded."""
from __future__ import annotations

from hashlib import sha256
import sqlite3

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_almanac_sequence import SequentialAlmanacWorker
from skeleton.ai.game_builder.dragon_discovery_mission import MissionSourceScout, SourceMission
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore


@pytest.fixture
def studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path / "mission.sqlite") as store:
        a = DragonAlmanacs(store)
        topic = a.ensure_topic(
            "studio", ("Sources", "Handheld", "Original homebrew"), authorized=True)
        entries = [
            ("https://alpha.example/gb-gameboy-physics", "web_candidate",
             ("Game Boy", "Handheld", "Collision")),
            ("https://alpha.example/gb-gameboy-input", "web_candidate",
             ("Game Boy", "Handheld", "Input")),
            ("https://beta.example/gameboy-gameplay", "web_candidate",
             ("Game Boy", "Controls", "Gameplay")),
            ("https://gamma.example/rom-bios-dumps-gameboy", "web_candidate",
             ("Game Boy", "ROM", "Game preservation")),
            ("https://delta.example/visual-video-gameboy", "video_candidate",
             ("Game Boy", "Visual examples")),
            ("https://unrelated.example/gardening", "web_candidate",
             ("Gardening", "Composting")),
        ]
        for url, kind, headers in entries:
            url = canonical_source_url(url)
            source_id = "source-" + sha256(url.encode()).hexdigest()
            body = {
                "source_id": source_id, "url": url, "kind": kind,
                "rights": "not_assessed", "training_authorized": False,
                "discoveries": [{"catalog_id": "handheld",
                                 "line": 1, "headers": list(headers)}],
            }
            store.db.execute(
                "INSERT INTO dragon_almanac_sources VALUES(?,?,?,?)",
                ("studio", source_id, canonical_json(body), canonical_digest(body)))
            store.db.execute(
                "INSERT OR IGNORE INTO dragon_almanac_members VALUES(?,?,?)",
                ("studio", topic, source_id))
        SequentialAlmanacWorker(a).seed("studio", authorized=True)
        store.db.commit()
        yield store, a, topic


def test_relevance_ranking_and_metadata_scope(studio):
    store, a, topic = studio
    m = SourceMission("gameboy input controls", platform="gameboy",
                      genre="gameplay", era="handheld", limit=4)
    scout = MissionSourceScout(a)
    first = scout.propose("studio", m, authorized=True, topic=topic)
    repeat = scout.propose("studio", m, authorized=True, topic=topic)
    assert first == repeat
    assert first["selection"]
    assert "input" in first["selection"][0]["url"] or (
        first["selection"][0]["factors"]["goal_overlap"] >= 1 / 3)
    assert all(x["policy_state"] == "pending" for x in first["selection"])
    assert all(x["training_authorized"] is False and
               x["network_authorized"] is False for x in first["selection"])
    assert first["queue_modified"] is False
    assert first["host_diversity_is_not_independence"] is True
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_jobs WHERE state='pending'"
    ).fetchone()[0] == 6


def test_host_diversity_and_rights_risk_are_explainable(studio):
    _, a, _ = studio
    result = MissionSourceScout(a).propose(
        "studio", SourceMission("gameboy", platform="gameboy", limit=5),
        authorized=True)
    hosts = [x["host"] for x in result["selection"]]
    assert hosts[:4] == list(dict.fromkeys(hosts[:4]))
    assert any(x["needs_manual_rights_review"] and "rom" in
               x["rights_risk_tokens"] for x in result["selection"])
    assert all(x["training_authorized"] is False for x in result["selection"])


def test_no_inventory_or_rights_grant_leak_between_owners(studio):
    _, a, topic = studio
    scout = MissionSourceScout(a)
    with pytest.raises(PermissionError):
        scout.propose("studio", SourceMission("gameboy"), authorized=False)
    with pytest.raises(ValueError, match="unknown owner topic"):
        scout.propose("other", SourceMission("gameboy"),
                      authorized=True, topic=topic)
    other = scout.propose("other", SourceMission("gameboy"), authorized=True)
    assert other["selection"] == [] and other["scanned"] == 0


def test_budget_types_and_partial_inventory_honestly_reported(studio):
    _, a, _ = studio
    with pytest.raises(ValueError):
        SourceMission("great", limit=True)
    with pytest.raises(ValueError):
        SourceMission("great", scan_budget=0)
    with pytest.raises(ValueError):
        SourceMission("great", platform="console\ncommand")
    with pytest.raises(ValueError):
        SourceMission("great", prefer_video=1)
    result = MissionSourceScout(a).propose(
        "studio", SourceMission("gameboy", limit=1, scan_budget=2),
        authorized=True)
    assert result["scan_truncated"] is True
    assert result["scanned"] == 2
    assert len(result["selection"]) <= 1
    assert result["ranking_scope"] == "discovery_metadata_only_not_verified_content"


def test_forged_canonical_source_fails_closed(studio):
    store, a, _ = studio
    row = store.db.execute(
        "SELECT source FROM dragon_almanac_sources WHERE owner='studio' ORDER BY source LIMIT 1"
    ).fetchone()
    store.db.execute(
        "UPDATE dragon_almanac_sources SET digest=? WHERE owner='studio' AND source=?",
        ("f" * 64, row[0]))
    store.db.commit()
    with pytest.raises(ValueError, match="corrupt source identity"):
        MissionSourceScout(a).propose(
            "studio", SourceMission("gameboy"), authorized=True)


def test_provenance_digest_tampering_fails_closed(studio):
    store, a, _ = studio
    scout = MissionSourceScout(a)
    raw = store.db.execute(
        "SELECT source,body FROM dragon_almanac_sources WHERE owner='studio'"
        " ORDER BY source LIMIT 1"
    ).fetchone()
    sid, body_raw = raw
    url = __import__("json").loads(body_raw)["url"]
    candidate = {"url": url, "source_id": sid,
                 "discoveries": [{"headers": ["Game Boy"]}]}
    claim = {"candidate": candidate, "normalized_source_id": sid,
             "normalized_url": url, "authority": "unreviewed_discovery_only"}
    store.db.execute(
        "INSERT INTO dragon_almanac_supplement_receipts_v2 VALUES(?,?,?,?,?,?)",
        ("studio", sid, sid, "a" * 64, canonical_json(claim), "f" * 64))
    store.db.commit()
    with pytest.raises(ValueError, match="invalid catalog provenance"):
        scout.propose("studio", SourceMission("gameboy"), authorized=True)


def test_baseline_without_optional_supplements_is_supported(studio):
    _, a, _ = studio
    result = MissionSourceScout(a).propose(
        "studio", SourceMission("gameboy", prefer_video=True), authorized=True)
    assert result["selection"]
    assert result["eligible_metadata_matches"] > 0
    assert result["unmatched_goal_terms_in_scanned_corpus"] == []
