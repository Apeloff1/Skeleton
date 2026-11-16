"""Physical canonical structural graph reservation and replay, on fixture storage."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier,Lock
from unittest import TestCase
from unittest.mock import patch

from core import dragon_graph_structural as structural
from core.dragon_game_corpus import CatalogueHeld,digest
from core.dragon_graph_authority import GraphHeld,LANES,lane,provision,qualify
from core.dragon_hoarder_bulk import owner_key
from core.dragon_lead_graph import LeadGraph,lead_id,_schema_row,ZERO
from core.dragon_release_queue import ReleaseQueue

OWNER={"tenant_id":"structural-fixture","owner_id":"one"}
OTHER={"tenant_id":"structural-fixture","owner_id":"two"}


class StructuralWriterTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.base=self.root/"corpus.sqlite"
        self.base.touch(mode=0o600)
        self.paths=tuple(self.root/("lane-"+str(i)+".sqlite") for i in range(LANES))
        self.graph=LeadGraph(self.base);self.owner=owner_key(OWNER)
        for p in (patch("core.dragon_lead_graph.MIN_RESERVE",0),
                  patch.dict(os.environ,{"SKL_DRAGON_CANONICAL_GRAPH_REQUIRED":"",
                     "SKL_DRAGON_LEAD_INDEX_ROOT":"","SKL_DRAGON_LEAD_EDGE_ROOT":""})):
            p.start();self.addCleanup(p.stop)
        self.graph.configure(OWNER,enabled=True,acknowledged=True)
        self.graph.configure(OTHER,enabled=True,acknowledged=True)
        self.queue=ReleaseQueue(self.base)
        with self.queue._db():pass
        # Use valid catalogue jobs inserted as settled source fixtures. No
        # remote fetch or fake source grant participates in these tests.
        provision(self.base,self.paths,offline_acknowledged=True)

    def source(self,index):
        for appid in range(100,index*100+10000):
            url="https://store.steampowered.com/app/"+str(appid)+"/"
            if lane(lead_id(url))==index:return str(appid),url
        raise AssertionError("fixture lane unavailable")

    def queued(self,index,tag,scope=OWNER,*,valid=True):
        owner=owner_key(scope);appid,url=self.source(index)
        job=digest(["job",owner,tag]);batch=digest(["batch",owner,tag])
        item={"namespace":"steam","external_id":appid,"title":"Fixture "+appid,
              "stage":"released","source":url,"kind":"storefront" if valid else "invalid-kind",
              "event_key":tag,"language":"en","version":None,"released_on":None}
        with self.queue._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO release_imports VALUES(?,?,?,?,?)",(owner,batch,"a"*64,1,1))
            db.execute("""INSERT INTO release_jobs(owner,id,batch,scope_json,payload,state,due)
                       VALUES(?,?,?,?,?,'done',1)""",(owner,job,batch,json.dumps(scope,sort_keys=True),json.dumps(item,sort_keys=True)))
            db.execute("INSERT INTO lead_release_outbox VALUES(?,?,1,'queued')",(owner,job))
            db.execute("COMMIT")
        return job,lead_id(url)

    def jobs(self):
        with self.queue._db() as db:
            return {r["id"]:r["state"] for r in db.execute("SELECT id,state FROM lead_release_outbox")}

    def test_parallel_structural_lane_commits_and_exact_settlement(self):
        j1,n1=self.queued(1,"a");j2,n2=self.queued(7,"b")
        barrier=Barrier(2,timeout=5);actual=structural._write_lane
        entered=[];lock=Lock()
        @contextmanager
        def overlap(*args,**kwargs):
            with actual(*args,**kwargs) as db:
                with lock:entered.append(args[2])
                barrier.wait()
                yield db
        with patch.object(structural,"_write_lane",overlap):
            result=self.graph.catalogue_pulse()
        self.assertEqual(set(entered),{1,7})
        self.assertEqual(result["processed"],2)
        self.assertEqual(result["physical_lanes"],2)
        self.assertEqual(self.jobs(),{j1:"done",j2:"done"})
        self.assertEqual(self.graph.status(OWNER)["nodes"],2)
        self.assertEqual(self.graph.status(OWNER)["edges"],2)
        self.assertEqual({r["id"] for r in self.graph.page(OWNER)["leads"]},{n1,n2})
        self.assertEqual(structural.status(self.base)["state"],"idle")
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])
        self.assertEqual(self.graph.catalogue_pulse()["processed"],0)

    def test_partial_commit_is_invisible_and_recovered(self):
        j1,n1=self.queued(2,"a");j2,n2=self.queued(8,"b")
        plan,witness=structural.reserve(self.base,"catalogue");seq=plan["sequence"]
        first=structural.apply_lane(self.base,seq,witness,2)
        self.assertFalse(first["replayed"])
        self.assertTrue(structural.apply_lane(self.base,seq,witness,2)["replayed"])
        self.assertEqual(self.jobs(),{j1:"queued",j2:"queued"})
        with self.assertRaises(CatalogueHeld):self.graph.page(OWNER)
        with self.assertRaises(CatalogueHeld):self.graph.status(OWNER)
        with self.assertRaises(CatalogueHeld):self.graph.review(OWNER,n1,decision="held",reason="fixture",operation="hold")
        with self.assertRaises(GraphHeld):structural.settle(self.base,seq,witness)
        with sqlite3.connect(self.paths[2]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM nodes WHERE id=?",(n1,)).fetchone()[0],1)
        with sqlite3.connect(self.base) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM lead_node_directory").fetchone()[0],0)
        result=structural.recover(self.base)
        self.assertEqual(result["processed"],2)
        self.assertTrue(any(r["lane"]==2 and r["replayed"] for r in result["lane_receipts"]))
        self.assertEqual(self.jobs(),{j1:"done",j2:"done"})
        self.assertTrue(structural.settle(self.base,seq,witness)["replayed"])
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_same_node_distinct_evidence_and_exact_replay(self):
        j1,n1=self.queued(4,"one");j2,n2=self.queued(4,"two")
        self.assertEqual(n1,n2)
        result=self.graph.catalogue_pulse()
        self.assertEqual(result["processed"],2)
        self.assertEqual(self.graph.status(OWNER)["nodes"],1)
        self.assertEqual(self.graph.status(OWNER)["edges"],2)
        item=self.graph.page(OWNER)["leads"][0]
        self.assertEqual(item["observations"],2)
        self.assertEqual(len(self.graph.edges(OWNER,n1,direction="parents")["edges"]),2)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_owner_quota_and_invalid_source_do_not_consume_partial_rows(self):
        a,_=self.queued(0,"allow");b,_=self.queued(1,"quota");bad,_=self.queued(2,"invalid",valid=False)
        with patch("core.dragon_lead_graph.MAX_NODES",1):
            result=self.graph.catalogue_pulse()
        self.assertEqual(result["processed"],1)
        self.assertEqual(result["held"],2)
        self.assertEqual(self.jobs()[bad],"held")
        self.assertEqual(self.graph.status(OWNER)["nodes"],1)
        self.assertEqual(self.graph.status(OWNER)["edges"],1)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_missing_lane_holds_reservation_without_recreation(self):
        j,_=self.queued(3,"missing")
        plan,witness=structural.reserve(self.base,"catalogue")
        self.paths[3].unlink()
        with self.assertRaises(CatalogueHeld):structural.recover(self.base)
        self.assertEqual(structural.status(self.base)["state"],"pending")
        self.assertFalse(self.paths[3].exists())
        self.assertEqual(self.jobs()[j],"queued")

    def test_expansion_creates_child_edges_on_independent_shards(self):
        job,parent=self.queued(5,"steam")
        self.assertEqual(self.graph.catalogue_pulse()["processed"],1)
        result=self.graph.expansion_pulse()
        self.assertGreaterEqual(result["processed"],1)
        self.assertGreater(self.graph.status(OWNER)["nodes"],1)
        children=self.graph.edges(OWNER,parent)["edges"]
        self.assertTrue(children)
        self.assertTrue(all(r["parent"]==parent and r["snapshot"] is None for r in children))
        self.assertEqual(self.graph.page(OTHER)["leads"],[])
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_root_policy_mutation_guard_and_nonadmitting_recovery(self):
        self.queued(6,"held")
        self.assertEqual(structural.recover(self.base)["processed"],0)
        plan,witness=structural.reserve(self.base,"catalogue")
        with sqlite3.connect(self.base) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE lead_owner SET nodes=nodes+1")
        self.assertEqual(structural.status(self.base)["state"],"pending")
        self.assertTrue(structural.recover(self.base)["independent_structural_writers"])

    def test_modified_plan_or_lane_receipt_fails_closed(self):
        self.queued(1,"tamper")
        plan,witness=structural.reserve(self.base,"catalogue")
        with sqlite3.connect(self.base) as db:
            db.execute("UPDATE dragon_graph_structural SET plan=plan||' '")
        with self.assertRaises(CatalogueHeld):structural.recover(self.base)
        self.assertEqual(structural.status(self.base)["state"],"pending")
        self.assertEqual(self.graph.authority_mode(),True)


    def test_bootstrap_inventory_parallel_cursor_and_recovery(self):
        rows=[]
        for index in (1,3,5,7,9):
            appid,url=self.source(index)
            rows.append((url,"Seed Fixture "+appid,"storefront","steam:"+appid,"seed","rev",appid))
        revision=digest(rows)
        # Select one enabled owner deterministically; both owners retain
        # independent bootstrap cursors, so disable the second fixture.
        self.graph.configure(OTHER,enabled=False,acknowledged=True)
        with patch("core.dragon_lead_graph.bootstrap_inventory",return_value=(revision,rows)):
            plan,witness=structural.reserve(self.base,"bootstrap")
            self.assertEqual(plan["bootstrap"]["cursor"],5)
            self.assertEqual(len(plan["lanes"]),5)
            structural.apply_lane(self.base,plan["sequence"],witness,1)
            with self.assertRaises(CatalogueHeld):self.graph.page(OWNER)
            result=structural.recover(self.base)
            self.assertEqual(result["processed"],5)
            self.assertTrue(result["bootstrap_complete"])
            state=self.graph.status(OWNER)
            self.assertEqual(state["bootstrap_cursor"],5)
            self.assertEqual(state["nodes"],5)
            self.assertEqual(state["edges"],5)
            self.assertEqual(self.graph.bootstrap_pulse()["processed"],0)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])
