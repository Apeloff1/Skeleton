"""Derived graph relocation: old bytes preserved; new epochs verified before use."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import os
import sqlite3

from core.dragon_lead_graph import LeadGraph,_schema_row,ZERO
from core.dragon_hoarder_bulk import owner_key
from core.dragon_graph_deployment import DeploymentHeld
from core import dragon_lead_index_shards as nodes
from core import dragon_lead_edge_shards as edges
from core import dragon_projection_relocation as move

ONE={"tenant_id":"projection-fixture","owner_id":"one"}
TWO={"tenant_id":"projection-fixture","owner_id":"two"}


class ProjectionMigrationTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.old_nodes=self.root/"old-nodes";self.old_edges=self.root/"old-edges"
        self.new_nodes=self.root/"new-nodes";self.new_edges=self.root/"new-edges"
        for p in (self.old_nodes,self.old_edges,self.new_nodes,self.new_edges):p.mkdir(mode=0o700)
        env={"SKL_DRAGON_LEAD_INDEX_ROOT":str(self.old_nodes),"SKL_DRAGON_LEAD_EDGE_ROOT":str(self.old_edges),
             "SKL_DRAGON_CANONICAL_GRAPH_REQUIRED":""}
        for patcher in (patch.dict(os.environ,env),patch("core.dragon_lead_graph.MIN_RESERVE",0)):
            patcher.start();self.addCleanup(patcher.stop)
        self.graph=LeadGraph(self.root/"corpus.sqlite")
        for scope in (ONE,TWO):
            self.graph.configure(scope,enabled=True,acknowledged=True)
        self.parent=self.add(ONE,0,ZERO)
        self.child=self.add(ONE,1,self.parent)
        self.other=self.add(TWO,2,ZERO)

    def add(self,scope,index,parent):
        with self.graph._db() as db:
            db.execute("BEGIN IMMEDIATE")
            identifier=self.graph._add(db,owner_key(scope),
                 _schema_row("https://example.org/game/"+str(index),"Fixture Game "+str(index),"storefront","fixture"),
                 parent=parent,relation="seed",witness="a"*64,now=1)
            db.execute("COMMIT")
            return identifier

    def pump(self,module,kind,rounds=4):
        table=move.KINDS[kind][0]
        for _ in range(rounds*nodes.LANES*2):
            with self.graph._db() as db:db.execute("UPDATE "+table+" SET due=0 WHERE owner=(SELECT owner FROM "+table+" ORDER BY due,owner LIMIT 1)")
            # Force deterministic fair fixture cycling by advancing real due
            # times for the previously selected lane owner.
            with self.graph._db() as db:db.execute("UPDATE "+table+" SET due=0")
            # One owner per fixture pump after switching environment; explicit
            # selection below avoids depending on wall-clock seconds.
            for scope in (ONE,TWO):
                owner=owner_key(scope)
                with self.graph._db() as db:db.execute("UPDATE "+table+" SET due=CASE WHEN owner=? THEN 0 ELSE 9223372036854775807 END",(owner,))
                module.pulse(self.graph)
        with self.graph._db() as db:db.execute("UPDATE "+table+" SET due=0")

    def test_bounded_node_rotation_preserves_old_files_and_exact_lookup(self):
        old={}
        for scope in (ONE,TWO):old[owner_key(scope)]=nodes.enroll(self.graph,scope,acknowledged=True)["epoch"]
        self.pump(nodes,"nodes",rounds=1)
        self.assertTrue(self.graph.page(ONE,q="Fixture")["physical_search_shards_used"])
        before=list(self.old_nodes.rglob("*.sqlite3"))
        self.assertEqual(len(before),20)
        with self.assertRaises(DeploymentHeld):move.begin(self.graph,"nodes",self.new_nodes)
        plan=move.begin(self.graph,"nodes",self.new_nodes,offline_acknowledged=True)
        self.assertFalse(self.graph.page(ONE,q="Fixture")["physical_search_shards_used"])
        first=move.advance(self.graph,"nodes",self.new_nodes,limit=1)
        self.assertEqual(first["phase"],"resetting")
        self.assertEqual(first["owners_rotated_total"],1)
        self.assertTrue(move.begin(self.graph,"nodes",self.new_nodes,offline_acknowledged=True)["replayed"])
        with self.assertRaises(nodes.IndexHeld):nodes.pulse(self.graph)
        with patch.dict(os.environ,{"SKL_DRAGON_LEAD_INDEX_ROOT":str(self.new_nodes)}):
            second=nodes.pulse(self.graph)
            self.assertEqual(second["phase"],"rebuilding")
            self.assertEqual(second["operation"],plan["operation"])
            self.assertEqual(second["owners_rotated_total"],2)
            self.assertFalse(self.graph.page(ONE,q="Fixture")["physical_search_shards_used"])
            self.pump(nodes,"nodes",rounds=1)
            result=move.audit(self.graph,"nodes",ONE)
            self.assertEqual(result["rows"],2)
            self.assertNotEqual(result["epoch"],old[owner_key(ONE)])
            self.assertTrue(self.graph.page(ONE,q="Fixture")["physical_search_shards_used"])
        self.assertTrue(all(p.exists() for p in before))
        self.assertFalse(self.graph.page(ONE,q="Fixture")["physical_search_shards_used"])

    def test_edge_rebuild_and_tampered_projection_detected(self):
        for scope in (ONE,TWO):edges.enroll(self.graph,scope,acknowledged=True)
        move.begin(self.graph,"edges",self.new_edges,offline_acknowledged=True)
        with patch.dict(os.environ,{"SKL_DRAGON_LEAD_EDGE_ROOT":str(self.new_edges)}):
            edges.pulse(self.graph)
            self.pump(edges,"edges",rounds=1)
            witness=move.audit(self.graph,"edges",ONE)
            self.assertEqual(witness["rows"],2)
            self.assertTrue(self.graph.edges(ONE,self.parent)["physical_edge_shards_used"])
            directory=self.new_edges/("edges-"+owner_key(ONE)+"-"+witness["epoch"])
            for path in directory.glob("edge-*.sqlite3"):
                with sqlite3.connect(path) as db:
                    if db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]:
                        db.execute("DELETE FROM edges");break
            with self.assertRaises(DeploymentHeld):move.audit(self.graph,"edges",ONE)

    def test_old_root_and_replaced_directory_hold(self):
        nodes.enroll(self.graph,ONE,acknowledged=True)
        move.begin(self.graph,"nodes",self.new_nodes,offline_acknowledged=True)
        self.new_nodes.rename(self.root/"moved")
        self.new_nodes.mkdir(mode=0o700)
        with self.assertRaises(DeploymentHeld):
            move.advance(self.graph,"nodes",self.new_nodes)
        self.assertFalse(self.graph.page(ONE,q="Fixture")["physical_search_shards_used"])
