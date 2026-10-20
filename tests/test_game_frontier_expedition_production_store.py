"""Game production journal restart, source revalidation and tampering tests."""
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_session import (
    ProductionInput,ProductionSession,
)
from skeleton.jeeves.game_frontier_expedition_production_store import (
    ProductionSessionStore,ProductionSessionConflict,
)
from tests.test_game_frontier_production_seven import sources


def initial():
    w,p,s,q=sources()
    return w,p,s,q,ProductionSession(w,p,s,q)


def test_production_sqlite_session_restores_canon_quests_and_real_game_events(tmp_path):
    w,p,s,q,session=initial()
    path=tmp_path/"production.sqlite"
    with ProductionSessionStore(path) as store:
        first=store.save("longform",session)
        assert first[0]==1
        session.submit(ProductionInput("dialogue",scene_id="departure",choice_id="chart"))
        second=store.save("longform",session,expected_version=first[0])
        assert second[0]==2
        session.submit(ProductionInput("gameplay","travel","launch_updraft"))
        third=store.save("longform",session,expected_version=second[0])
        assert third[0]==3
    with ProductionSessionStore(path) as store:
        generation,loaded,receipt=store.load("longform",w,p,s,q)
        assert generation==3 and receipt==third[1]
        assert loaded.game.position==w.waypoints[1].waypoint_id
        assert loaded.story.flags=={"map_promised"}
        assert loaded.quests.progress["chart_the_islands"]==2
        assert len(loaded.events)==2
        assert len(store.history("longform"))==3
        loaded.submit(ProductionInput("dialogue",scene_id="threshold",choice_id="remember"))
        v4=store.save("longform",loaded,expected_version=3)
        assert v4[0]==4
    with ProductionSessionStore(path) as store:
        final=store.load("longform",w,p,s,q)
        assert len(final[1].story.moments)==2
        assert final[1].story.flags=={"map_promised","memory_kept"}
        assert final[0]==4


def test_production_save_idempotency_does_not_forge_new_game_generations(tmp_path):
    w,p,s,q,session=initial()
    with ProductionSessionStore(tmp_path/"idem.sqlite") as store:
        first=store.save("same",session)
        second=store.save("same",session)
        assert first==second
        assert len(store.history("same"))==1


def test_production_stale_writer_and_rewind_are_rejected(tmp_path):
    path=tmp_path/"conflict.sqlite"
    w,p,s,q,session=initial()
    with ProductionSessionStore(path) as store:
        store.save("run",session)
        stale=ProductionSession.restore(w,p,s,q,session.snapshot())
        session.submit(ProductionInput("dialogue",scene_id="departure",choice_id="chart"))
        store.save("run",session,expected_version=1)
        stale.submit(ProductionInput("dialogue",scene_id="departure",choice_id="rescue"))
        with pytest.raises(ProductionSessionConflict,match="advanced"):
            store.save("run",stale,expected_version=1)
        with pytest.raises(ProductionSessionConflict,match="rewind"):
            store.save("run",ProductionSession(w,p,s,q),expected_version=2)


def test_production_foreign_canon_and_world_are_not_accepted(tmp_path):
    w,p,s,q,session=initial()
    with ProductionSessionStore(tmp_path/"scope.sqlite") as store:
        store.save("run",session)
        other_w,other_p,other_s,other_q=sources(seed=18)
        with pytest.raises(ExpeditionError,match="foreign source"):
            store.load("run",other_w,other_p,other_s,other_q)


def test_production_tamper_history_and_json_root_prevent_resumption(tmp_path):
    w,p,s,q,session=initial()
    with ProductionSessionStore(tmp_path/"tamper.sqlite") as store:
        store.save("run",session)
        store._db.execute(
            "UPDATE production_history SET receipt=? WHERE run_id=?",
            ("0"*64,"run"))
        with pytest.raises(ExpeditionError,match="receipt was altered"):
            store.load("run",w,p,s,q)
    with ProductionSessionStore(tmp_path/"bytes.sqlite") as store:
        store.save("run",session)
        store._db.execute(
            "UPDATE production_head SET payload=? WHERE run_id=?",
            (b'{"fabricated":true}',"run"))
        with pytest.raises(ExpeditionError,match="bytes were altered"):
            store.load("run",w,p,s,q)


def test_production_store_closed_and_malformed_run_ids_fail_closed(tmp_path):
    w,p,s,q,session=initial()
    store=ProductionSessionStore(tmp_path/"closed.sqlite")
    with pytest.raises(ExpeditionError,match="run id"):
        store.save("../run",session)
    store.close()
    with pytest.raises(ExpeditionError,match="closed"):
        store.save("run",session)


def test_production_missing_checkpoint_never_creates_a_fake_lore_session(tmp_path):
    w,p,s,q,_=initial()
    with ProductionSessionStore(tmp_path/"absent.sqlite") as store:
        assert store.load("missing",w,p,s,q) is None
        assert store.history("missing")==()
