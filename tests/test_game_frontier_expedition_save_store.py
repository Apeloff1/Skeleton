"""Real game session crash, save, resume, CAS and tamper acceptance."""
import json
import sqlite3
from pathlib import Path
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionAction, ExpeditionEpisode
from skeleton.jeeves.game_frontier_expedition_save_store import (
    ExpeditionSaveError, ExpeditionSaveConflict, ExpeditionSaveStore,
)
from tests.test_game_frontier_expedition import world,player


def sources():
    return world(),player(flags=("glider",))


def test_restart_restores_full_gameplay_state_and_continues(tmp_path:Path):
    w,p=sources()
    path=tmp_path/"expedition.sqlite"
    with ExpeditionSaveStore(path) as store:
        first=ExpeditionEpisode(w,p)
        checkpoint=store.save("longform:001",first)
        assert checkpoint.generation==1
        first.step(ExpeditionAction("travel","launch"))
        updated=store.save(
            "longform:001",first,expected_generation=checkpoint.generation)
        assert updated.generation==2
        assert len(store.history("longform:001"))==2
    with ExpeditionSaveStore(path) as resumed:
        record=resumed.load("longform:001",w,p)
        assert record.generation==2
        assert record.episode.position=="cliff"
        record.episode.step(ExpeditionAction("travel","bridge"))
        next_record=resumed.save(
            "longform:001",record.episode,expected_generation=record.generation)
        assert next_record.generation==3
        assert next_record.episode.inventory=={"artifact"}
        assert next_record.episode.snapshot()["receipts"][:1]==first.receipts


def test_same_game_save_is_idempotent_across_retries(tmp_path):
    w,p=sources()
    with ExpeditionSaveStore(tmp_path/"save.sqlite") as store:
        ep=ExpeditionEpisode(w,p)
        first=store.save("run",ep)
        replay=store.save("run",ep)
        assert first.receipt==replay.receipt
        assert replay.generation==1
        assert len(store.history("run"))==1


def test_stale_writer_cannot_overwrite_changed_save(tmp_path):
    path=tmp_path/"conflict.sqlite"
    w,p=sources()
    with ExpeditionSaveStore(path) as a, ExpeditionSaveStore(path) as b:
        one=a.save("run",ExpeditionEpisode(w,p))
        same=b.load("run",w,p)
        updated=one.episode
        updated.step(ExpeditionAction("travel","launch"))
        a.save("run",updated,expected_generation=1)
        same.episode.step(ExpeditionAction("inspect"))
        with pytest.raises(ExpeditionSaveConflict,match="advanced"):
            b.save("run",same.episode,expected_generation=same.generation)
        assert b.load("run",w,p).episode.position=="cliff"


def test_cannot_rewind_previous_checkpoint_history(tmp_path):
    w,p=sources()
    with ExpeditionSaveStore(tmp_path/"rewind.sqlite") as store:
        ep=ExpeditionEpisode(w,p)
        store.save("run",ep)
        ep.step(ExpeditionAction("travel","launch"))
        store.save("run",ep,expected_generation=1)
        with pytest.raises(ExpeditionSaveConflict,match="rewind"):
            store.save("run",ExpeditionEpisode(w,p),expected_generation=2)


def test_wrong_source_and_player_cannot_be_reused(tmp_path):
    w,p=sources()
    with ExpeditionSaveStore(tmp_path/"source.sqlite") as store:
        store.save("run",ExpeditionEpisode(w,p))
        other=world()
        from dataclasses import replace
        other=replace(other,source_digest="e"*64)
        with pytest.raises(ExpeditionSaveError,match="another world"):
            store.load("run",other,p)
        with pytest.raises(ExpeditionSaveError,match="replay failed"):
            store.load("run",w,player(flags=("glider","extra")))


def test_tampered_history_and_game_snapshot_fail_before_replay(tmp_path):
    w,p=sources()
    with ExpeditionSaveStore(tmp_path/"tamper.sqlite") as store:
        store.save("run",ExpeditionEpisode(w,p))
        store._db.execute(
            "UPDATE expedition_save_history SET receipt_digest=?",
            ("0"*64,))
        with pytest.raises(ExpeditionSaveError,match="altered"):
            store.load("run",w,p)
    with ExpeditionSaveStore(tmp_path/"bytes.sqlite") as store:
        store.save("run",ExpeditionEpisode(w,p))
        store._db.execute(
            "UPDATE expedition_save SET payload=?",(b'{"forged":true}',))
        with pytest.raises(ExpeditionSaveError,match="integrity"):
            store.load("run",w,p)


def test_deleted_generation_and_rolledback_head_detected(tmp_path):
    w,p=sources()
    with ExpeditionSaveStore(tmp_path/"history.sqlite") as store:
        ep=ExpeditionEpisode(w,p)
        store.save("run",ep)
        ep.step(ExpeditionAction("travel","launch"))
        store.save("run",ep,expected_generation=1)
        store._db.execute(
            "DELETE FROM expedition_save_history WHERE generation=1")
        with pytest.raises(ExpeditionSaveError,match="truncated"):
            store.history("run")
    with ExpeditionSaveStore(tmp_path/"rollback.sqlite") as store:
        ep=ExpeditionEpisode(w,p)
        store.save("run",ep)
        ep.step(ExpeditionAction("travel","launch"))
        store.save("run",ep,expected_generation=1)
        store._db.execute("UPDATE expedition_save SET generation=1")
        with pytest.raises(ExpeditionSaveError,match="head differs"):
            store.load("run",w,p)


@pytest.mark.parametrize("key",("", "../escape", "bad space",None))
def test_invalid_run_identifiers_are_refused(tmp_path,key):
    w,p=sources()
    with ExpeditionSaveStore(tmp_path/"bad.sqlite") as store:
        with pytest.raises(ExpeditionSaveError,match="identity"):
            store.save(key,ExpeditionEpisode(w,p))


def test_closed_store_cannot_reopen_without_explicit_new_connection(tmp_path):
    w,p=sources()
    store=ExpeditionSaveStore(tmp_path/"closed.sqlite")
    store.close()
    with pytest.raises(ExpeditionSaveError,match="closed"):
        store.save("run",ExpeditionEpisode(w,p))


def test_missing_run_load_never_creates_a_fake_game(tmp_path):
    w,p=sources()
    with ExpeditionSaveStore(tmp_path/"missing.sqlite") as store:
        assert store.load("missing",w,p) is None
        assert store.history("missing")==()
