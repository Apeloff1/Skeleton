"""Version-qualified MMO graph and patch comparison regression suite."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock,patch
import hashlib
import json

from core.dragon_game_corpus import CatalogueHeld
from core.dragon_game_datasets import DatasetShard,chain_step,ZERO
from core.dragon_dataset_explorer import DatasetExplorer

SCOPE={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}
GAME="a"*64
SOURCE="b"*64


def row(key,value,*edges):
    return {"_key":key,"value":value,"_relations":[{"kind":kind,"target":target} for kind,target in edges]}


class DatasetExplorerTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name).resolve()
        root.chmod(0o700)
        self.root=root
        self.shard=DatasetShard(SCOPE,GAME,create=True,root=root)
        self.explorer=DatasetExplorer(SCOPE,GAME,shard=self.shard)
        self.corpus=Mock()
        self.corpus.capture_plan.return_value={"crawl_authorized":False}

    def version(self,label,records,*,dataset="ships",source=SOURCE,seal=True):
        raw="\n".join(json.dumps(r,sort_keys=True) for r in records).encode()
        chain=chain_step(ZERO,hashlib.sha256(raw).hexdigest(),0,len(records))
        v=self.shard.begin(dataset=dataset,source=source,observation_digest="c"*64,label=label,
            expected_rows=len(records),expected_chain=chain,grant_seconds=3600,rights_acknowledged=True,corpus=self.corpus)
        self.shard.append(v["id"],0,raw)
        if seal:self.shard.seal(v["id"])
        return v["id"]

    def test_cycle_safe_graph_and_unresolved_targets(self):
        v=self.version("Release",[
            row("ship/frigate",100,("requires","skill/piloting"),("market","region/unknown")),
            row("skill/piloting",50,("unlocks","ship/frigate")),
            row("station/one",1,("sells","ship/frigate"))])
        graph=self.explorer.graph(v,"ship/frigate",max_depth=4)
        self.assertEqual(len(graph["nodes"]),4)
        self.assertEqual(len(graph["edges"]),4)
        self.assertEqual(graph["unresolved_nodes"],1)
        self.assertFalse(graph["training_allowed"])
        shallow=self.explorer.graph(v,"ship/frigate",direction="out",max_depth=1,node_limit=2)
        self.assertTrue(shallow["truncated"])
        self.assertLessEqual(len(shallow["nodes"]),2)
        self.assertEqual(self.explorer.graph(v,"ship/frigate",max_depth=0)["edges"],[])
        self.assertEqual(self.explorer.record(v,"ship/frigate")["record"]["value"],100)

    def test_ordered_comparison_through_unchanged_pages(self):
        a=self.version("Before",[row("1",1),row("2",2),row("3",3),row("4",4)])
        b=self.version("After",[row("1",1),row("2",20),row("4",4),row("5",5)])
        cursor=None;seen=[];counts={"added":0,"removed":0,"changed":0,"unchanged":0}
        while True:
            page=self.explorer.compare(a,b,after=cursor,limit=1)
            self.assertEqual(page["scanned"],1)
            seen.extend(page["changes"])
            for k,value in page["window_counts"].items():counts[k]+=value
            cursor=page["next_cursor"]
            if cursor is None:break
        self.assertEqual([x["key"] for x in seen],["2","3","5"])
        self.assertEqual(counts,{"added":1,"removed":1,"changed":1,"unchanged":2})
        detail=self.explorer.compare_record(a,b,"2")
        self.assertEqual(detail["before"]["record"]["value"],2)
        self.assertEqual(detail["after"]["record"]["value"],20)
        self.assertEqual(detail["fields"],[{"field":"value","change":"changed"}])

    def test_namespace_authority_and_seal(self):
        a=self.version("A",[row("1",1)])
        b=self.version("B",[row("1",2)],dataset="skills")
        pending=self.version("Pending",[row("1",3)],seal=False)
        with self.assertRaises(ValueError):self.explorer.compare(a,b)
        with self.assertRaises(LookupError):self.explorer.record(pending,"1")
        other=DatasetExplorer(OTHER,GAME,shard=DatasetShard(OTHER,GAME,root=self.root,create=True))
        with self.assertRaises(LookupError):other.graph(a,"1")
        self.shard.revoke(a)
        with self.assertRaises(LookupError):self.explorer.record(a,"1")

    def test_corrupt_row_held_before_publication(self):
        a=self.version("A",[row("1",1)])
        b=self.version("B",[row("1",2)])
        with self.shard._db() as db:
            db.execute("UPDATE dataset_records SET data_json='{}' WHERE owner=? AND game=? AND version=?",
                       (self.shard.owner,GAME,b))
        with self.assertRaises(CatalogueHeld):self.explorer.compare(a,b)
        with self.assertRaises(CatalogueHeld):self.explorer.graph(b,"1")
