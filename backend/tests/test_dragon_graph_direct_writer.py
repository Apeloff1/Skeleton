"""Canonical local writer regressions; fixtures only, never production hardware."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase
from unittest.mock import patch

from core import dragon_graph_direct_writer as direct
from core.dragon_game_corpus import CatalogueHeld
from core.dragon_graph_authority import LANES,lane,provision,qualify
from core.dragon_hoarder_bulk import owner_key
from core.dragon_lead_graph import LeadGraph,_schema_row,ZERO,lead_id

SCOPE={"tenant_id":"direct","owner_id":"writer"}
OTHER={"tenant_id":"direct","owner_id":"other"}


class DirectReviewTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.base=self.root/"corpus.sqlite"
        self.base.touch(mode=0o600)
        self.paths=tuple(self.root/("lane-"+str(i)+".sqlite") for i in range(LANES))
        self.graph=LeadGraph(self.base)
        for p in (patch("core.dragon_lead_graph.MIN_RESERVE",0),
                  patch.dict(os.environ,{"SKL_DRAGON_CANONICAL_GRAPH_REQUIRED":"","SKL_DRAGON_LEAD_INDEX_ROOT":"","SKL_DRAGON_LEAD_EDGE_ROOT":""})):
            p.start();self.addCleanup(p.stop)
        self.graph.configure(SCOPE,enabled=True,acknowledged=True)
        self.graph.configure(OTHER,enabled=True,acknowledged=True)
        self.ids=[self.seed(i) for i in range(LANES)]

    def seed(self,index):
        for n in range(10000):
            url="https://example.org/lead/"+str(index)+"/"+str(n)
            if lane(lead_id(url))==index:break
        else:raise AssertionError("fixture lane missing")
        with self.graph._db() as db:
            db.execute("BEGIN IMMEDIATE")
            identifier=self.graph._add(db,owner_key(SCOPE),_schema_row(url,"Fixture "+str(index),"storefront","fixture"),
                parent=ZERO,relation="seed",witness="a"*64,now=1)
            db.execute("COMMIT")
        return identifier

    def activate(self):
        provision(self.base,self.paths,offline_acknowledged=True)

    def item(self,index,operation="hold",decision="held"):
        return {"lead":self.ids[index],"operation":operation,"decision":decision,"reason":"fixture","interval_seconds":900}

    def root_sequence(self):
        with sqlite3.connect(self.base) as db:
            return db.execute("SELECT commit_sequence FROM dragon_graph_authority").fetchone()[0]

    def test_two_distinct_authoritative_lane_writers_overlap(self):
        self.activate()
        self.assertEqual(self.graph.status(SCOPE)["independent_review_writers"],10)
        root_sequence=self.root_sequence()
        barrier=Barrier(2,timeout=4);actual=direct._lane_db
        @contextmanager
        def overlap(*args,**kwargs):
            with actual(*args,**kwargs) as db:
                # Both SQLite BEGIN IMMEDIATE statements have succeeded on
                # different canonical databases before either may commit.
                barrier.wait()
                yield db
        with patch.object(direct,"_lane_db",overlap):
            with ThreadPoolExecutor(max_workers=2) as workers:
                a=workers.submit(self.graph.review,SCOPE,**self.item(1))
                b=workers.submit(self.graph.review,SCOPE,**self.item(7))
                receipts=[a.result(timeout=10),b.result(timeout=10)]
        self.assertEqual({r["writer_lane"] for r in receipts},{1,7})
        self.assertTrue(all(r["independent_writer"] and not r["replayed"] for r in receipts))
        self.assertEqual(self.root_sequence(),root_sequence)
        for i in (1,7):
            with sqlite3.connect(self.paths[i]) as db:
                self.assertEqual(db.execute("SELECT state FROM nodes WHERE id=?",(self.ids[i],)).fetchone()[0],"held")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM review_events").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT revision FROM writer_state").fetchone()[0],1)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_legacy_replay_and_new_local_conflict(self):
        original=self.graph.review(SCOPE,**self.item(2))
        self.assertNotIn("writer_lane",original)
        self.activate()
        before=self.graph.review(SCOPE,**self.item(2))
        self.assertTrue(before["replayed"])
        self.assertEqual(before["lane_revision"],0)
        changed=self.graph.review(SCOPE,**self.item(2,operation="second",decision="candidate"))
        self.assertEqual(changed["lane_revision"],1)
        self.assertTrue(self.graph.review(SCOPE,**self.item(2,operation="second",decision="candidate"))["replayed"])
        with self.assertRaises(CatalogueHeld):self.graph.review(SCOPE,**self.item(2,operation="second",decision="retired"))
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_batch_order_partial_results_and_replay(self):
        self.activate()
        items=[self.item(6),self.item(1),self.item(6,"return","candidate"),self.item(9),
               {**self.item(0),"lead":"f"*64}]
        results=self.graph.review_batch(SCOPE,items=items)
        self.assertFalse(results["atomic_batch"])
        self.assertEqual([r["index"] for r in results["results"]],list(range(len(items))))
        self.assertEqual([r["state"] for r in results["results"]],["committed"]*4+["missing"])
        self.assertEqual(results["results"][2]["lane_revision"],2)
        replay=self.graph.review_batch(SCOPE,items=items)
        self.assertTrue(all(r["replayed"] for r in replay["results"][:4]))
        with self.assertRaises(ValueError):self.graph.review_batch(SCOPE,items=[items[0],items[0]])
        self.assertIn(self.ids[6],{r["id"] for r in self.graph.page(SCOPE,state="candidate",limit=100)["leads"]})

    def test_policy_disabled_and_cross_owner_held(self):
        self.activate()
        with self.assertRaises(LookupError):self.graph.review(OTHER,**self.item(5))
        self.graph.configure(SCOPE,enabled=False,acknowledged=True)
        with self.assertRaises(CatalogueHeld):self.graph.review(SCOPE,**self.item(5))
        with sqlite3.connect(self.paths[5]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM review_events").fetchone()[0],0)

    def test_missing_lane_never_falls_back(self):
        self.activate()
        self.paths[4].unlink()
        with self.assertRaises(CatalogueHeld):self.graph.review(SCOPE,**self.item(4))
        self.assertFalse(self.paths[4].exists())
        with sqlite3.connect(self.base) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM lead_review_events").fetchone()[0],0)

    def test_local_fault_rolls_back_canonical_state_and_receipt(self):
        self.activate()
        actual=direct._lane_db
        @contextmanager
        def fault(*args,**kwargs):
            with actual(*args,**kwargs) as db:
                yield db
                raise RuntimeError("fixture before commit")
        with patch.object(direct,"_lane_db",fault):
            with self.assertRaises(RuntimeError):self.graph.review(SCOPE,**self.item(3))
        with sqlite3.connect(self.paths[3]) as db:
            self.assertEqual(db.execute("SELECT state FROM nodes WHERE id=?",(self.ids[3],)).fetchone()[0],"candidate")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM review_events").fetchone()[0],0)
        self.assertFalse(self.graph.review(SCOPE,**self.item(3))["replayed"])

    def test_install_idempotence_and_audited_local_counts(self):
        self.activate()
        self.assertTrue(direct.install(self.base,offline_acknowledged=True)["replayed"])
        self.graph.review(SCOPE,**self.item(1))
        with sqlite3.connect(self.paths[1]) as db:
            db.execute("UPDATE review_counts SET total=total+1")
        from core.dragon_graph_authority import GraphHeld
        with self.assertRaises(GraphHeld):qualify(self.base,full=True)
