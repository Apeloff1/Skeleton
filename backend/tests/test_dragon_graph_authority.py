"""Canonical physical graph fixtures (not production device qualification)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from core.dragon_game_corpus import GameCorpus,CatalogueHeld
from core.dragon_graph_authority import GraphHeld,LANES,lane,provision,qualify,write_probe,pending_probes,recover_probe
from core.dragon_hoarder_bulk import owner_key
from core.dragon_lead_graph import LeadGraph,_schema_row,ZERO,lead_id
from core.dragon_release_queue import ReleaseQueue

SCOPE={"tenant_id":"canonical-fixture","owner_id":"one"}
OTHER={"tenant_id":"canonical-fixture","owner_id":"two"}


class CanonicalGraphTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.base=self.root/"corpus.sqlite"
        self.base.touch(mode=0o600)
        self.paths=tuple(self.root/("physical-"+str(i)+".sqlite") for i in range(LANES))
        self.graph=LeadGraph(self.base)
        p=patch("core.dragon_lead_graph.MIN_RESERVE",0)
        p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{"SKL_DRAGON_CANONICAL_GRAPH_REQUIRED":"",
              "SKL_DRAGON_LEAD_EDGE_ROOT":"","SKL_DRAGON_LEAD_INDEX_ROOT":""})
        p.start();self.addCleanup(p.stop)
        self.graph.configure(SCOPE,enabled=True,acknowledged=True)
        self.graph.configure(OTHER,enabled=True,acknowledged=True)
        self.parent=self.add(0,parent=ZERO)

    def add(self,number,*,scope=SCOPE,parent=None,now=1):
        if parent is None:parent=self.parent
        with LeadGraph(self.base)._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row=_schema_row("https://example.org/game/"+str(number),"Fixture "+str(number),"storefront","fixture")
                result=self.graph._add(db,owner_key(scope),row,parent=parent,relation="seed",witness="a"*64,now=now)
                db.execute("COMMIT");return result
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def provision(self):
        return provision(self.base,self.paths,offline_acknowledged=True)

    def page(self,scope=SCOPE,**kwargs):
        all_rows=[];after=None
        while True:
            value=self.graph.page(scope,limit=7,after=after,**kwargs)
            all_rows.extend(value["leads"]);after=value["next_cursor"]
            if after is None:return all_rows

    def edge_page(self):
        all_rows=[];after=None
        while True:
            value=self.graph.edges(SCOPE,self.parent,limit=7,after=after)
            all_rows.extend(value["edges"]);after=value["next_cursor"]
            if after is None:return all_rows

    def test_migrate_exact_rootless_graph_and_cross_lane_reads(self):
        for i in range(1,61):self.add(i)
        self.add(1,scope=OTHER,parent=ZERO)
        before=self.page(q="Fixture");edges=self.edge_page()
        self.graph.review(SCOPE,before[0]["id"],decision="held",reason="fixture",operation="hold")
        before=self.page(q="Fixture");held=self.page(q="Fixture",state="held")
        receipt=self.provision()
        self.assertEqual(receipt["physical_lanes"],10)
        self.assertEqual(receipt["nodes"],62)
        self.assertEqual(self.page(q="Fixture"),before)
        self.assertEqual(self.page(q="Fixture",state="held"),held)
        self.assertEqual(self.edge_page(),edges)
        self.assertTrue(self.graph.page(SCOPE,q="Fixture")["physical_search_shards_used"])
        self.assertTrue(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
        self.assertTrue(self.graph.status(SCOPE)["physical_graph_sharding"])
        with sqlite3.connect(self.base) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0],"delete")
            for table in ("lead_nodes","lead_edges","lead_fts"):
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM lead_node_directory").fetchone()[0],62)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM lead_node_directory WHERE title<>''").fetchone()[0],0)
        for i,path in enumerate(self.paths):
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0],"delete")
                self.assertTrue(all(lane(r[0])==i for r in db.execute("SELECT id FROM nodes")))
                self.assertTrue(all(lane(r[0])==i for r in db.execute("SELECT child FROM edges")))
        self.assertEqual(len(self.page(OTHER,q="Fixture")),1)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_write_replay_review_and_commit_fence(self):
        self.provision()
        child=self.add(1);self.add(1,now=100)
        edge=self.graph.edges(SCOPE,self.parent)["edges"][0]
        self.assertEqual(edge["last_seen"],100)
        self.assertEqual(edge["child"],child)
        node=next(r for r in self.page() if r["id"]==child)
        self.assertEqual(node["observations"],1)
        self.assertEqual(node["last_seen"],100)
        self.graph.review(SCOPE,child,decision="held",reason="fixture",operation="hold")
        self.assertIn(child,{r["id"] for r in self.page(state="held")})
        self.assertNotIn(child,{r["id"] for r in self.page()})
        self.assertEqual(self.graph.edges(SCOPE,child,direction="parents")["edges"][0]["parent"],self.parent)
        with sqlite3.connect(self.base) as db:
            self.assertGreater(db.execute("SELECT commit_sequence FROM dragon_graph_authority").fetchone()[0],0)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_failure_rolls_back_root_and_shard_writes(self):
        self.provision()
        before=self.graph.status(SCOPE)
        identifier=lead_id("https://example.org/game/99")
        with patch("core.dragon_graph_authority.insert_edge",side_effect=RuntimeError("fault after physical node")):
            with self.assertRaises(RuntimeError):self.add(99)
        self.assertEqual(self.graph.status(SCOPE)["nodes"],before["nodes"])
        with sqlite3.connect(self.base) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM lead_node_directory WHERE id=?",(identifier,)).fetchone())
            self.assertEqual(db.execute("SELECT commit_sequence FROM dragon_graph_authority").fetchone()[0],0)
        with sqlite3.connect(self.paths[lane(identifier)]) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM nodes WHERE id=?",(identifier,)).fetchone())
        self.assertEqual(self.add(99),identifier)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_failed_offline_migration_never_publishes_topology(self):
        self.add(1);before=self.page()
        with patch("core.dragon_graph_authority._verify_directory",side_effect=GraphHeld("injected migration failure")):
            with self.assertRaises(GraphHeld):self.provision()
        self.assertFalse(self.graph.authority_mode())
        self.assertEqual(self.page(),before)
        with sqlite3.connect(self.base) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='dragon_graph_authority'").fetchone())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM lead_nodes").fetchone()[0],2)

    def test_missing_shard_holds_without_fallback(self):
        self.provision()
        self.paths[3].unlink()
        with self.assertRaises(CatalogueHeld):self.graph.page(SCOPE,q="Fixture")
        with self.assertRaises(CatalogueHeld):self.add(3)
        self.assertFalse(self.paths[3].exists())

    def test_wrong_journal_cannot_be_silently_changed(self):
        self.provision()
        with sqlite3.connect(self.paths[1]) as db:db.execute("PRAGMA journal_mode=WAL").fetchall()
        with self.assertRaises(CatalogueHeld):self.graph.page(SCOPE,q="Fixture")
        with sqlite3.connect(self.paths[1]) as db:self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0],"wal")
        with sqlite3.connect(self.base) as db:db.execute("PRAGMA journal_mode=WAL").fetchall()
        with self.assertRaises(CatalogueHeld):self.graph.status(SCOPE)

    def test_corpus_release_queue_and_graph_share_root_journal(self):
        self.provision()
        with GameCorpus(self.base)._db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0],"delete")
        with ReleaseQueue(self.base)._db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0],"delete")
        self.assertEqual(len(self.graph.page(SCOPE)["leads"]),1)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_concurrent_writers_do_not_overcount_or_duplicate(self):
        self.provision()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(self.add,[1,2,3,1,4,2,5,5,6,2]))
        self.assertEqual(len(set(results)),6)
        self.assertEqual(self.graph.status(SCOPE)["nodes"],7)
        self.assertEqual(self.graph.status(SCOPE)["edges"],7)
        self.assertTrue(qualify(self.base,full=True)["full_integrity_audit"])

    def test_device_probe_commit_reopen_and_recovery(self):
        self.provision()
        with self.assertRaises(GraphHeld):write_probe(self.base,bytes_per_lane=4096)
        with patch("core.dragon_graph_authority.recover_probe",side_effect=RuntimeError("stop after commit")):
            with self.assertRaises(RuntimeError):write_probe(self.base,bytes_per_lane=4096,acknowledged=True)
        pending=pending_probes(self.base)["pending_probe_ids"]
        self.assertEqual(len(pending),1)
        receipt=recover_probe(self.base,pending[0])
        self.assertEqual(receipt["verified_bytes"],4096*10)
        self.assertTrue(receipt["cleanup_verified"])
        self.assertFalse(receipt["capacity_verified"])
        self.assertEqual(pending_probes(self.base)["pending_probe_ids"],[])
        self.assertTrue(write_probe(self.base,bytes_per_lane=4096,acknowledged=True)["readback_verified"])

    def test_require_topology_without_provision_fails_closed(self):
        with patch.dict(os.environ,{"SKL_DRAGON_CANONICAL_GRAPH_REQUIRED":"1"}):
            with self.assertRaises(CatalogueHeld):self.graph.status(SCOPE)
