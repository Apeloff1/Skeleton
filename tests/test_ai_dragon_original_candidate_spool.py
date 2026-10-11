"""Actual bounded SQLite original-game candidate batch work, no fake completions."""
from __future__ import annotations
import json,sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_original_candidate_spool import (
    SCHEMA,MAX_BATCH,materialize_batch,audit_batch,
)
from skeleton.ai.webcrawler.dragon_original_mechanic_forge import (
    FULL_BINARY_PROFILE_COUNT,
)


def test_real_candidate_batch_persists_actual_dual_gameplay_receipts_and_replays(tmp_path):
    dbpath=tmp_path/"original-candidates.sqlite"
    with sqlite3.connect(dbpath) as db:
        result=materialize_batch(
            db,start=200,count=4,routes=2,steps=12,branch_seed=1977)
        assert result["schema"]==SCHEMA
        assert result["requested"]==4
        assert result["new_original_playable_prototypes"]==4
        assert result["independently_verified_existing_prototypes"]==0
        assert result["database_total_materialized"]==4
        assert result["genuinely_finished_licensed_games"]==0
        assert len(result["content_chain_sha256"])==64
        examined=audit_batch(
            db,start=200,count=4,branch_seed=1977)
        assert examined["verified"]==4
        assert examined["all_actual_original_gameplay_replayed"]
    with sqlite3.connect(dbpath) as again:
        repeated=materialize_batch(
            again,start=200,count=4,routes=2,steps=12,branch_seed=1977)
        assert repeated["new_original_playable_prototypes"]==0
        assert repeated["independently_verified_existing_prototypes"]==4
        assert repeated["database_total_materialized"]==4
        assert repeated["content_chain_sha256"]==result["content_chain_sha256"]


def test_atomic_spooling_keeps_original_game_addresses_non_overlapping():
    with sqlite3.connect(":memory:") as db:
        first=materialize_batch(db,start=31,count=3,routes=1,steps=12)
        second=materialize_batch(db,start=34,count=3,routes=1,steps=12)
        assert first["new_original_playable_prototypes"]==3
        assert second["new_original_playable_prototypes"]==3
        assert second["database_total_materialized"]==6
        row=db.execute(
            "SELECT original_nucleus FROM dragon_original_candidate_v1 "
            "ORDER BY original_nucleus"
        ).fetchall()
        assert row==[(31,),(32,),(33,),(34,),(35,),(36,)]
        assert audit_batch(db,start=31,count=6)["verified"]==6


def test_game_candidate_spool_fails_closed_on_tampered_local_gameplay_receipt():
    with sqlite3.connect(":memory:") as db:
        materialize_batch(db,start=77,count=1)
        db.execute(
            "UPDATE dragon_original_candidate_v1 SET source_receipt=? "
            "WHERE original_nucleus=77",
            ('{"original_nucleus":77,"independently_published":true}',))
        db.commit()
        with pytest.raises(PermissionError):
            audit_batch(db,start=77,count=1)
        with pytest.raises(PermissionError):
            materialize_batch(db,start=77,count=1)


def test_candidate_spooling_cannot_silently_overwrite_different_seed_or_crossover():
    with sqlite3.connect(":memory:") as db:
        materialize_batch(db,start=100,count=2,branch_seed=1)
        with pytest.raises(PermissionError):
            materialize_batch(db,start=100,count=2,branch_seed=2)
        with pytest.raises(PermissionError):
            materialize_batch(db,start=100,count=2,steps=15,branch_seed=1)
        assert db.execute(
            "SELECT COUNT(*) FROM dragon_original_candidate_v1"
        ).fetchone()[0]==2


def test_original_spool_rollback_preserves_entire_batch_on_conflicting_candidate():
    with sqlite3.connect(":memory:") as db:
        materialize_batch(db,start=9,count=1,branch_seed=0)
        before=db.execute(
            "SELECT COUNT(*) FROM dragon_original_candidate_v1"
        ).fetchone()[0]
        with pytest.raises(PermissionError):
            materialize_batch(db,start=8,count=2,branch_seed=5)
        assert db.execute(
            "SELECT COUNT(*) FROM dragon_original_candidate_v1"
        ).fetchone()[0]==before
        assert db.execute(
            "SELECT original_nucleus FROM dragon_original_candidate_v1"
        ).fetchall()==[(9,)]


@pytest.mark.parametrize("bad",[
    {"start":-1},{"start":FULL_BINARY_PROFILE_COUNT},
    {"start":FULL_BINARY_PROFILE_COUNT-1,"count":2},
    {"start":True},{"count":0},{"count":MAX_BATCH+1},
    {"routes":0},{"routes":5},{"steps":3},{"steps":25},
    {"branch_seed":-1},{"branch_seed":2**32},
])
def test_prototype_production_rejects_unbounded_cpu_memory_and_bad_indexes(bad):
    with sqlite3.connect(":memory:") as db:
        with pytest.raises(ValueError):
            materialize_batch(db,**{**{"start":0,"count":1},**bad})


def test_source_candidates_are_unpublished_even_when_they_are_playable():
    with sqlite3.connect(":memory:") as db:
        materialize_batch(db,start=0,count=1,routes=2,steps=12)
        row=db.execute(
            "SELECT candidate_status,source_receipt FROM "
            "dragon_original_candidate_v1 WHERE original_nucleus=0"
        ).fetchone()
        assert row[0]=="source_playable_only"
        parsed=json.loads(row[1])
        assert not parsed["native_binary_built"]
        assert not parsed["independently_published"]
        assert parsed["release_blockers"]
