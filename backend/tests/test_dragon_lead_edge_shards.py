"""Physical edge stores: exact replay, bounded traversal and canonical fallback."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from core.dragon_hoarder_bulk import owner_key
from core.dragon_lead_graph import LeadGraph,_schema_row,ZERO
from core.dragon_lead_edge_shards import enroll,pulse,LANES

SCOPE={"tenant_id":"edge-fixture","owner_id":"one"}
OTHER={"tenant_id":"edge-fixture","owner_id":"two"}


class EdgePartitionTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.edge_root=self.root/"edges";self.edge_root.mkdir(mode=0o700)
        for patcher in (patch.dict(os.environ,{"SKL_DRAGON_LEAD_EDGE_ROOT":str(self.edge_root)}),
                        patch("core.dragon_lead_graph.MIN_RESERVE",0)):
            patcher.start();self.addCleanup(patcher.stop)
        self.graph=LeadGraph(self.root/"corpus.sqlite")
        self.graph.configure(SCOPE,enabled=True,acknowledged=True)
        self.owner=owner_key(SCOPE)
        self.parent=self.add(0,parent=ZERO)

    def add(self,number,*,parent=None,now=1,witness="a"*64):
        if parent is None:parent=self.parent
        with self.graph._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=_schema_row("https://example.org/game/"+str(number),"Fixture "+str(number),"storefront","fixture")
            result=self.graph._add(db,self.owner,row,parent=parent,relation="seed",witness=witness,now=now)
            db.execute("COMMIT")
            return result

    def pulses(self,count=3):
        for _ in range(count*LANES):
            with self.graph._db() as db:db.execute("UPDATE lead_edge_enrollment SET due=0")
            pulse(self.graph)

    def test_ten_files_and_exact_paged_bidirectional_traversal(self):
        children=[self.add(i) for i in range(1,40)]
        receipt=enroll(self.graph,SCOPE,acknowledged=True)
        self.assertFalse(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
        self.pulses()
        directory=self.edge_root/("edges-"+self.owner+"-"+receipt["epoch"])
        self.assertEqual(len(list(directory.glob("edge-*.sqlite3"))),10)
        result=self.graph.edges(SCOPE,self.parent,limit=7)
        self.assertTrue(result["physical_edge_shards_used"])
        with patch.dict(os.environ,{"SKL_DRAGON_LEAD_EDGE_ROOT":""}):
            baseline=self.graph.edges(SCOPE,self.parent,limit=7)
        self.assertEqual(result["edges"],baseline["edges"])
        self.assertEqual(result["next_cursor"],baseline["next_cursor"])
        seen=[];cursor=None
        while True:
            page=self.graph.edges(SCOPE,self.parent,after=cursor,limit=7)
            self.assertTrue(page["physical_edge_shards_used"])
            seen.extend(r["child"] for r in page["edges"])
            cursor=page["next_cursor"]
            if cursor is None:break
        self.assertEqual(set(seen),set(children))
        self.assertEqual(len(seen),len(children))
        parents=self.graph.edges(SCOPE,children[0],direction="parents")
        self.assertTrue(parents["physical_edge_shards_used"])
        self.assertEqual(parents["edges"][0]["parent"],self.parent)
        with self.assertRaises(LookupError):self.graph.edges(OTHER,self.parent)

    def test_delta_replay_and_exact_last_seen(self):
        child=self.add(1)
        enroll(self.graph,SCOPE,acknowledged=True)
        self.pulses()
        first=self.graph.edges(SCOPE,self.parent)["edges"][0]
        self.add(1,now=900)
        self.assertFalse(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
        self.pulses()
        second=self.graph.edges(SCOPE,self.parent)
        self.assertTrue(second["physical_edge_shards_used"])
        self.assertEqual(second["edges"][0]["id"],first["id"])
        self.assertEqual(second["edges"][0]["last_seen"],900)
        self.assertEqual(second["edges"][0]["child"],child)
        new=self.add(2)
        self.assertFalse(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
        self.pulses()
        self.assertIn(new,{r["child"] for r in self.graph.edges(SCOPE,self.parent)["edges"]})

    def test_missing_partition_rebuild_and_epoch_reset(self):
        self.add(1)
        receipt=enroll(self.graph,SCOPE,acknowledged=True)
        self.pulses()
        p=self.edge_root/("edges-"+self.owner+"-"+receipt["epoch"])/"edge-3.sqlite3"
        p.unlink()
        self.assertFalse(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
        self.pulses()
        self.assertTrue(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
        other=enroll(self.graph,SCOPE,acknowledged=True,reset=True)
        self.assertNotEqual(receipt["epoch"],other["epoch"])
        self.assertFalse(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
        self.pulses()
        self.assertTrue(self.graph.edges(SCOPE,self.parent)["physical_edge_shards_used"])
