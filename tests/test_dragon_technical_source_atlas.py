"""Dragon technical sources: actual owner-scoped queue and metadata regressions."""
from __future__ import annotations

from hashlib import sha256

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_technical_source_atlas import (
    CATALOG, CATALOG_DIGEST, DragonTechnicalSources,
)
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore


@pytest.fixture
def studio(tmp_path):
    with ReviewedKnowledgeStore(tmp_path/"technical-sources.sqlite") as store:
        yield store, DragonTechnicalSources(DragonAlmanacs(store))


def test_atlas_covers_more_than_raw_engine_links():
    assert len(CATALOG)>=50
    assert len({x["slug"] for x in CATALOG})==len(CATALOG)
    assert len({x["url"] for x in CATALOG})==len(CATALOG)
    assert len({x["family"] for x in CATALOG})>=10
    assert len(CATALOG_DIGEST)==64
    assert all(x["training_authorized"] is False and
               x["crawler_authorized"] is False and
               x["availability"]=="not_checked" for x in CATALOG)


def test_import_creates_real_stage_zero_jobs_and_is_idempotent(studio):
    store,atlas=studio
    first=atlas.import_catalog("studio",authorized=True,recorded_at=1791800000)
    assert first["new_source_metadata"]==len(CATALOG)
    assert first["new_policy_stage_jobs"]==len(CATALOG)
    assert first["new_editorial_events"]==len(CATALOG)
    assert first["network_requests"]==first["approved_knowledge_added"]==0
    assert store.db.execute(
        "SELECT COUNT(*) FROM dragon_almanac_jobs WHERE owner=? AND stage=0 AND state='pending'",
        ("studio",)).fetchone()[0]==len(CATALOG)
    again=atlas.import_catalog("studio",authorized=True,recorded_at=1791800009)
    assert again["new_source_metadata"]==0
    assert again["new_policy_stage_jobs"]==0
    assert again["new_editorial_events"]==0


def test_research_selection_is_deterministic_task_aware_and_adjacency_safe(studio):
    _,atlas=studio
    atlas.import_catalog("studio",authorized=True,recorded_at=1791800000)
    one=atlas.plan("studio","gameboy retro rom errors",authorized=True,limit=30)
    assert one==atlas.plan("studio","gameboy retro rom errors",
                            authorized=True,limit=30)
    assert one["selected"]
    assert any(hit["family"]=="homebrew" for hit in one["selected"])
    assert any(hit["family"]=="coding" for hit in one["selected"])
    assert len({hit["source_id"] for hit in one["selected"]})==len(one["selected"])
    assert all(hit["page_freshness"]=="unknown" and
               hit["crawler_authorized"] is False and
               hit["training_authorized"] is False for hit in one["selected"])
    no_adj=atlas.plan("studio","crawler",authorized=True)
    assert not no_adj["selected"] or all(
        hit["score"]>0 for hit in no_adj["selected"])


def test_cross_owner_no_leakage_or_unauthorized_operation(studio):
    _,atlas=studio
    atlas.import_catalog("owner-a",authorized=True,recorded_at=1791800000)
    sid="source-"+sha256(CATALOG[0]["url"].encode()).hexdigest()
    assert atlas.plan("owner-b","gameboy",authorized=True)["selected"]==[]
    assert atlas.history("owner-b",sid,authorized=True)["events"]==[]
    assert len(atlas.history("owner-a",sid,authorized=True)["events"])==1
    with pytest.raises(PermissionError):
        atlas.import_catalog("owner-b",authorized=False,recorded_at=1791800000)
    with pytest.raises(PermissionError):
        atlas.plan("owner-a","gameboy",authorized=False)


def test_tampering_and_stale_input_cannot_enter_research_plan(studio):
    store,atlas=studio
    atlas.import_catalog("studio",authorized=True,recorded_at=1791800000)
    seed=next(x for x in CATALOG if x["slug"]=="pandocs")
    sid="source-"+sha256(seed["url"].encode()).hexdigest()
    store.db.execute("UPDATE dragon_technical_source_events_v1 SET body='{}' "
                     "WHERE owner=? AND source=?",("studio",sid))
    with pytest.raises(ValueError,match="integrity"):
        atlas.plan("studio","gameboy",authorized=True)
    with pytest.raises(ValueError,match="integrity"):
        atlas.import_catalog("studio",authorized=True,recorded_at=1791800010)


def test_preserves_existing_source_identity_and_policy_digest(studio):
    store,atlas=studio
    atlas.import_catalog("studio",authorized=True,recorded_at=1791800000)
    sid="source-"+sha256(CATALOG[0]["url"].encode()).hexdigest()
    before=store.db.execute(
        "SELECT digest FROM dragon_almanac_sources WHERE owner=? AND source=?",
        ("studio",sid)).fetchone()[0]
    atlas.import_catalog("studio",authorized=True,recorded_at=1791800001)
    afterwards=store.db.execute(
        "SELECT j.input_digest,s.digest FROM dragon_almanac_jobs j "
        "JOIN dragon_almanac_sources s ON s.owner=j.owner AND s.source=j.source "
        "WHERE j.owner=? AND j.source=?",("studio",sid)).fetchone()
    assert afterwards==(before,before)


def test_bounds_and_source_event_digest(studio):
    _,atlas=studio
    for options in ({"limit":0},{"max_per_host":0},{"include_adjacent":1}):
        with pytest.raises(ValueError):
            atlas.plan("studio","gameboy",authorized=True,**options)
    with pytest.raises(ValueError):
        atlas.plan("studio","bad\ninjection",authorized=True)
    with pytest.raises(ValueError):
        atlas.import_catalog("studio",authorized=True,recorded_at=-1)
    with pytest.raises(ValueError):
        atlas.history("studio","source-bad",authorized=True)
    atlas.import_catalog("studio",authorized=True,recorded_at=1791800000)
    sid="source-"+sha256(CATALOG[0]["url"].encode()).hexdigest()
    event=atlas.history("studio",sid,authorized=True)["events"][0]
    assert event["digest"]==canonical_digest(
        {k:v for k,v in event.items() if k!="digest"})
    assert event["improvements"][0].startswith("(")
