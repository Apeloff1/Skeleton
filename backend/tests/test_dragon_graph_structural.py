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


    def snapshot_fixture(self,projection="locator",expected=2):
        import time
        sid=digest(["snapshot",projection,expected])
        with self.graph._db() as db:
            db.execute("BEGIN IMMEDIATE")
            parent=self.graph._add(db,self.owner,_schema_row("https://example.org/datasets/"+projection,
                "Dataset fixture","dataset_manifest","fixture"),parent=ZERO,
                relation="dataset_target",witness="a"*64,now=1)
            db.execute("""INSERT INTO lead_snapshots(owner,id,root,target_id,registry_revision,projection,source_sha,
                rights_ref,expected_rows,chain,state,expires_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'open',?,?)""",
                (self.owner,sid,parent,"fixture","b"*64,projection,"c"*64,"fixture-rights",
                 expected,ZERO,int(time.time())+3600,1))
            db.execute("UPDATE lead_owner SET snapshots=snapshots+1 WHERE owner=?",(self.owner,))
            db.execute("COMMIT")
        return sid,parent

    def snapshot_page(self,lanes=(1,7)):
        import hashlib
        rows=[]
        for index in lanes:
            appid,url=self.source(index)
            rows.append({"url":url,"title":"Snapshot "+appid,"kind":"storefront","subject":"steam:"+appid})
        raw="\n".join(json.dumps(row,sort_keys=True) for row in rows).encode()
        return {"ordinal":0,"raw":raw,"sha256":hashlib.sha256(raw).hexdigest(),"previous_chain":ZERO}

    def test_snapshot_page_parallel_publication_and_replay(self):
        sid,parent=self.snapshot_fixture()
        page=self.snapshot_page()
        item,prior=structural.reserve_snapshot(self.base,OWNER,sid,**page)
        self.assertIsNone(prior)
        plan,witness=item
        self.assertEqual(set(plan["lanes"]),{"1","7"})
        structural.apply_lane(self.base,plan["sequence"],witness,1)
        with self.assertRaises(CatalogueHeld):self.graph.page(OWNER)
        with sqlite3.connect(self.base) as db:
            self.assertEqual(db.execute("SELECT rows,next_page FROM lead_snapshots WHERE id=?",(sid,)).fetchone(),(0,0))
        value=structural.recover(self.base)
        self.assertEqual(value["rows"],2)
        self.assertEqual(self.graph.snapshot(OWNER,sid)["rows"],2)
        self.assertTrue(self.graph.append(OWNER,sid,**page)["replayed"])
        result=self.graph.seal(OWNER,sid,value["chain"])
        self.assertEqual(result["state"],"sealed")
        edges=self.graph.edges(OWNER,parent)["edges"]
        self.assertEqual(len(edges),2)
        self.assertTrue(all(e["snapshot"]==sid for e in edges))
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_revoke_after_first_lane_compensates_exact_prestate(self):
        sid,parent=self.snapshot_fixture()
        page=self.snapshot_page()
        # An existing node must survive compensation with its exact
        # pre-reservation observation count and last_seen.
        _,url=self.source(1)
        with self.graph._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.graph._add(db,self.owner,_schema_row(url,"Existing fixture","storefront","existing"),
                           parent=ZERO,relation="seed",witness="d"*64,now=1)
            db.execute("COMMIT")
        before=self.graph.page(OWNER)
        (plan,witness),_=structural.reserve_snapshot(self.base,OWNER,sid,**page)
        structural.apply_lane(self.base,plan["sequence"],witness,1)
        self.assertTrue(self.graph.revoke(OWNER,sid)["revoked"])
        result=structural.recover(self.base)
        self.assertTrue(result["aborted"])
        self.assertEqual(self.graph.page(OWNER)["leads"],before["leads"])
        self.assertEqual(self.graph.snapshot(OWNER,sid)["rows"],0)
        self.assertEqual(self.graph.snapshot(OWNER,sid)["state"],"revoked")
        self.assertEqual(self.graph.edges(OWNER,parent)["edges"],[])
        with self.assertRaises(CatalogueHeld):self.graph.append(OWNER,sid,**page)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_expiration_after_all_committed_lanes_removes_only_new_rows(self):
        sid,parent=self.snapshot_fixture()
        page=self.snapshot_page()
        (plan,witness),_=structural.reserve_snapshot(self.base,OWNER,sid,**page)
        for index in plan["lanes"]:structural.apply_lane(self.base,plan["sequence"],witness,int(index))
        with sqlite3.connect(self.base) as db:db.execute("UPDATE lead_snapshots SET expires_at=0 WHERE id=?",(sid,))
        self.assertTrue(structural.recover(self.base)["aborted"])
        self.assertEqual(self.graph.status(OWNER)["nodes"],1)
        self.assertEqual(self.graph.snapshot(OWNER,sid)["rows"],0)
        self.assertEqual(self.graph.edges(OWNER,parent)["edges"],[])
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_feed_batch_custody_and_cross_lane_replay(self):
        app1,_=self.source(1);app7,_=self.source(7)
        raw=json.dumps({"applist":{"apps":[{"appid":int(app1),"name":"A"},{"appid":int(app7),"name":"B"}]}}).encode()
        receipt=self.queue.enqueue(OWNER,raw=raw,adapter="steam",operation="feed-fixture")
        args={"url":"https://example.org/feed","raw":raw,"adapter":"steam","options":{},
              "subscription_id":"e"*64,"batch_id":receipt["batch_id"]}
        with self.assertRaises(CatalogueHeld):self.graph.feed_page(OTHER,**args)
        value=self.graph.feed_page(OWNER,**args)
        self.assertEqual(value["proposals"],2)
        self.assertTrue(value["independent_structural_writers"])
        before=self.graph.status(OWNER)
        self.assertTrue(self.graph.feed_page(OWNER,**args)["replayed"])
        self.assertEqual(self.graph.status(OWNER)["edges"],before["edges"])
        with self.assertRaises(CatalogueHeld):
            self.graph.feed_page(OWNER,**{**args,"subscription_id":"f"*64})
        feed=lead_id(args["url"])
        self.assertEqual(len(self.graph.edges(OWNER,feed)["edges"]),2)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_snapshot_expansion_uses_grant_and_lane_settlement(self):
        sid,parent=self.snapshot_fixture()
        children=self.snapshot_page()
        result=self.graph.append(OWNER,sid,**children)
        appid,url=self.source(1);child=lead_id(url)
        job=digest(["snapshot-expansion",sid,child])
        with self.graph._db() as db:
            db.execute("INSERT INTO lead_expand_jobs VALUES(?,?,?,?,?,?,'queued',?,?)",
                       (self.owner,job,child,appid,"Snapshot expansion","b"*64,1,sid))
        result=self.graph.expansion_pulse()
        self.assertTrue(result["independent_structural_writers"])
        self.assertEqual(result["processed"],1)
        self.assertTrue(all(e["snapshot"]==sid for e in self.graph.edges(OWNER,child)["edges"]))
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])


    def test_multi_batch_distinct_owners_overlap_and_reverse_settlement(self):
        from core.dragon_graph_multi_batch import install
        from concurrent.futures import ThreadPoolExecutor
        install(self.base,offline_acknowledged=True)
        j1,n1=self.queued(1,"multi-a",OWNER)
        j2,n2=self.queued(7,"multi-b",OTHER)
        first=structural.reserve(self.base,"catalogue")
        second=structural.reserve(self.base,"catalogue")
        self.assertNotEqual(first[0]["jobs"][0]["owner"],second[0]["jobs"][0]["owner"])
        self.assertEqual(len(structural.status(self.base)["pending_batches"]),2)
        self.assertIsNone(structural.reserve(self.base,"catalogue"))
        barrier=Barrier(2,timeout=5);actual=structural._write_lane
        @contextmanager
        def overlap(*args,**kwargs):
            with actual(*args,**kwargs) as db:
                barrier.wait()
                yield db
        def apply(item):
            plan,witness=item
            return structural.apply_lane(self.base,plan["sequence"],witness,int(next(iter(plan["lanes"]))))
        with patch.object(structural,"_write_lane",overlap):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(apply,(first,second)))
        self.assertEqual({r["lane"] for r in results},{1,7})
        plan,witness=second
        self.assertEqual(structural.settle(self.base,plan["sequence"],witness)["processed"],1)
        self.assertEqual(structural.status(self.base)["state"],"pending")
        with self.assertRaises(CatalogueHeld):self.graph.page(OWNER)
        self.assertTrue(structural.settle(self.base,plan["sequence"],witness)["replayed"])
        plan,witness=first
        self.assertEqual(structural.settle(self.base,plan["sequence"],witness)["processed"],1)
        self.assertEqual(self.jobs(),{j1:"done",j2:"done"})
        self.assertEqual({r["id"] for r in self.graph.page(OWNER)["leads"]},{n1})
        self.assertEqual({r["id"] for r in self.graph.page(OTHER)["leads"]},{n2})
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_multi_batch_shared_lane_receipts_survive_out_of_order_replay(self):
        from core.dragon_graph_multi_batch import install
        install(self.base,offline_acknowledged=True)
        self.queued(4,"shared-a",OWNER);self.queued(4,"shared-b",OTHER)
        first=structural.reserve(self.base,"catalogue");second=structural.reserve(self.base,"catalogue")
        for plan,witness in (second,first):
            self.assertFalse(structural.apply_lane(self.base,plan["sequence"],witness,4)["replayed"])
        with sqlite3.connect(self.paths[4]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM structural_receipts").fetchone()[0],2)
        for plan,witness in (first,second):
            self.assertTrue(structural.apply_lane(self.base,plan["sequence"],witness,4)["replayed"])
        plan,witness=second
        structural.settle(self.base,plan["sequence"],witness)
        with sqlite3.connect(self.paths[4]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM structural_receipts").fetchone()[0],1)
        result=structural.recover(self.base)
        self.assertEqual(result["processed"],1)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_multi_batch_owner_exclusivity_and_pending_limit(self):
        from core.dragon_graph_multi_batch import install,MAX_PENDING
        install(self.base,offline_acknowledged=True)
        scopes=[OWNER,OTHER]+[{"tenant_id":"structural-fixture","owner_id":"extra-"+str(i)} for i in range(3)]
        for scope in scopes[2:]:self.graph.configure(scope,enabled=True,acknowledged=True)
        for i,scope in enumerate(scopes):
            self.queued(i,"limit-"+str(i),scope)
        plans=[structural.reserve(self.base,"catalogue") for _ in range(MAX_PENDING)]
        self.assertEqual(len({p[0]["jobs"][0]["owner"] for p in plans}),MAX_PENDING)
        self.assertIsNone(structural.reserve(self.base,"catalogue"))
        result=structural.recover(self.base)
        self.assertEqual(result["processed"],MAX_PENDING)
        self.assertEqual(structural.status(self.base)["state"],"idle")
        self.assertEqual(structural.pulse(self.base,"catalogue")["processed"],1)
        self.assertEqual(set(self.jobs().values()),{"done"})
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_multi_batch_revocation_does_not_undo_other_owner(self):
        from core.dragon_graph_multi_batch import install
        sid,parent=self.snapshot_fixture()
        page=self.snapshot_page()
        self.queued(1,"other-grant",OTHER)
        install(self.base,offline_acknowledged=True)
        snapshot,prior=structural.reserve_snapshot(self.base,OWNER,sid,**page)
        self.assertIsNone(prior)
        other=structural.reserve(self.base,"catalogue")
        plan,witness=snapshot
        structural.apply_lane(self.base,plan["sequence"],witness,1)
        p2,w2=other
        structural.apply_lane(self.base,p2["sequence"],w2,1)
        self.assertTrue(self.graph.revoke(OWNER,sid)["revoked"])
        self.assertTrue(structural.settle(self.base,plan["sequence"],witness)["aborted"])
        self.assertEqual(structural.status(self.base)["state"],"pending")
        structural.settle(self.base,p2["sequence"],w2)
        self.assertEqual(self.graph.snapshot(OWNER,sid)["rows"],0)
        self.assertEqual(self.graph.edges(OWNER,parent)["edges"],[])
        self.assertEqual(len(self.graph.page(OTHER)["leads"]),1)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_multi_batch_scheduler_uses_one_lane_pool(self):
        from core.dragon_graph_multi_batch import install
        install(self.base,offline_acknowledged=True)
        self.queued(1,"scheduler-a",OWNER);self.queued(7,"scheduler-b",OTHER)
        with patch("core.dragon_lead_graph.bootstrap_inventory",return_value=("a"*64,())):
            with self.graph._db() as db:
                db.execute("UPDATE lead_owner SET bootstrap_revision=?,bootstrapped=1",("a"*64,))
            result=structural.pulse_many(self.base)
        self.assertTrue(result["parallel_batch_scheduler"])
        self.assertEqual(result["admitted_batches"],2)
        self.assertEqual(result["processed"],2)
        self.assertEqual(result["held_batches"],0)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_multi_upgrade_requires_idle_and_receipt_audit(self):
        from core.dragon_graph_multi_batch import install
        self.queued(3,"legacy")
        structural.reserve(self.base,"catalogue")
        with self.assertRaises(GraphHeld):install(self.base,offline_acknowledged=True)
        structural.recover(self.base)
        with self.assertRaises(GraphHeld):install(self.base)
        install(self.base,offline_acknowledged=True)
        self.assertTrue(install(self.base,offline_acknowledged=True)["replayed"])
        with sqlite3.connect(self.paths[3]) as db:
            db.execute("INSERT INTO structural_receipts VALUES(?,?,?)",(999,"a"*64,"b"*64))
        with self.assertRaises(GraphHeld):qualify(self.base,full=True)
