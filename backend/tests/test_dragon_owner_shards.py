"""Physical owner partitions: no live network, no production capacity claims."""
from __future__ import annotations

from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from core.dragon_game_corpus import GameCorpus
from core.dragon_hoarder_bulk import BulkArchive,GIB,Volume,StorageHeld,owner_key
from core.dragon_hoarder_manifests import ManifestArchive
from core.dragon_lead_graph import LeadGraph
from core.dragon_manifest_shards import ShardedManifestArchive
from core.dragon_owner_shards import LANES,ShardHeld,next_path,owner_path,provision,shard_paths
from core.dragon_release_queue import ReleaseQueue
from core.dragon_world_discovery import WorldDiscovery


def scope_for(lane):
    for n in range(10000):
        scope={"tenant_id":"fixture","owner_id":"owner-"+str(n)}
        if int(owner_key(scope)[:16],16)%LANES==lane:return scope
    raise AssertionError("fixture lane not found")


def seed(corpus,scope,title):
    return corpus.observe(scope,namespace="developer",external_id="fixture",
        title=title,source="https://example.org/fixture",kind="storefront",
        language="en",stage="released",event_key="initial",version="1",released_on=None)


class OwnerPartitionTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.paths=tuple(self.root/("corpus-"+str(i)+".sqlite") for i in range(LANES))
        self.base=self.paths[0]
        self.base.touch(mode=0o600)

    def provision(self):
        return provision(self.base,"corpus",self.paths,offline_acknowledged=True)

    def test_explicit_provision_and_legacy_default(self):
        self.assertEqual(owner_path(self.base,"corpus",scope_for(7)),self.base)
        with self.assertRaises(ShardHeld):
            provision(self.base,"corpus",self.paths)
        self.assertTrue(all(not p.exists() for p in self.paths[1:]))
        self.assertEqual(self.provision()["shards"],10)
        self.assertEqual(shard_paths(self.base,"corpus"),self.paths)
        with self.assertRaises(ShardHeld):self.provision()

    def test_existing_corpus_and_lead_owner_pin_new_owner_distribute(self):
        old=scope_for(7)
        graph_only=scope_for(6)
        seed(GameCorpus(self.base),old,"Original")
        with patch("core.dragon_lead_graph.MIN_RESERVE",0):
            LeadGraph(self.base).configure(graph_only,enabled=True,acknowledged=True)
        self.provision()
        self.assertEqual(owner_path(self.base,"corpus",old),self.base)
        self.assertEqual(owner_path(self.base,"corpus",graph_only),self.base)
        for lane in (1,2,3,4,5,8,9):
            other=scope_for(lane)
            path=owner_path(self.base,"corpus",other)
            self.assertEqual(path,self.paths[lane])
            seed(GameCorpus(path),other,"Isolated "+str(lane))
            self.assertEqual(owner_path(self.base,"corpus",other),path)
            with GameCorpus(path)._db() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM games WHERE owner=?",(owner_key(old),)).fetchone()[0],0)
        with GameCorpus(self.base)._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM games").fetchone()[0],1)

    def test_concurrent_route_publication(self):
        self.provision()
        scope=scope_for(4)
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths=list(pool.map(lambda _:owner_path(self.base,"corpus",scope),range(16)))
        self.assertEqual(set(paths),{self.paths[4]})
        with sqlite3.connect(self.base) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM dragon_shard_routes").fetchone()[0],1)

    def test_missing_shard_no_fallback_and_maintenance_rotates(self):
        self.provision()
        scope=scope_for(4)
        self.assertEqual(owner_path(self.base,"corpus",scope),self.paths[4])
        self.paths[4].unlink()
        with self.assertRaises(FileNotFoundError):owner_path(self.base,"corpus",scope)
        for i in range(4):self.assertEqual(next_path(self.base,"corpus","lead"),self.paths[i])
        with self.assertRaises(FileNotFoundError):next_path(self.base,"corpus","lead")
        self.assertEqual(next_path(self.base,"corpus","lead"),self.paths[5])
        self.assertFalse(self.paths[4].exists())

    def test_wrong_lane_identity_rejected_and_required_mode(self):
        with patch.dict(os.environ,{"SKL_DRAGON_CORPUS_SHARDS_REQUIRED":"1"}):
            with self.assertRaises(ShardHeld):owner_path(self.base,"corpus",scope_for(1))
        self.provision()
        with sqlite3.connect(self.paths[2]) as db:
            db.execute("UPDATE dragon_shard_identity SET lane=3")
        with self.assertRaises(ShardHeld):owner_path(self.base,"corpus",scope_for(2))

    def test_world_subscription_keeps_global_origin_coordinator(self):
        self.provision()
        scope=scope_for(5)
        world=WorldDiscovery(self.base,owner_route=lambda owner:owner_path(self.base,"corpus",owner))
        world.configure(scope,url="https://example.org/feed",adapter="manifest",
            interval_seconds=3600,grant_seconds=86400,rights_acknowledged=True)
        self.assertEqual(owner_path(self.base,"corpus",scope),self.paths[5])
        self.assertEqual(len(world.status(scope)["subscriptions"]),1)
        with GameCorpus(self.paths[5])._db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='world_subscriptions'").fetchone())
        # A second owner on the same hostname cannot lease while the first
        # origin lease is active, despite different corpus shards.
        second=scope_for(3)
        world.configure(second,url="https://example.org/other",adapter="manifest",
            interval_seconds=3600,grant_seconds=86400,rights_acknowledged=True)
        self.assertIsNotNone(world._claim())
        self.assertIsNone(world._claim())

    def test_release_and_lead_share_exact_owner_database(self):
        self.provision()
        scope=scope_for(8)
        path=owner_path(self.base,"corpus",scope)
        with patch("core.dragon_lead_graph.MIN_RESERVE",0):
            LeadGraph(path).configure(scope,enabled=True,acknowledged=True)
        with ReleaseQueue(path)._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM lead_owner WHERE owner=?",(owner_key(scope),)).fetchone()[0],1)
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='lead_release_outbox'").fetchone())


class ManifestPartitionTests(TestCase):
    def test_legacy_owner_pin_owner_dedup_and_tombstone_restart(self):
        disk=namedtuple("Disk","total used free")
        with TemporaryDirectory() as d,patch("core.dragon_hoarder_bulk.shutil.disk_usage",return_value=disk(10*GIB,0,10*GIB)):
            root=Path(d).resolve()
            volume=Volume("primary",root,2*GIB)
            bulk=BulkArchive((volume,))
            paths=tuple(root/("manifests-"+str(i)+".db") for i in range(LANES))
            base=paths[0]
            old=scope_for(3);new=scope_for(4)
            raw=b"identical owner deduplication bytes"
            expected=hashlib.sha256(raw).hexdigest()
            def put(archive,scope,operation):
                mid=archive.begin(scope,logical_key="fixture",operation=operation,
                    expected_hash=expected,expected_bytes=len(raw))["manifest"]
                archive.append(scope,mid,0,raw)
                archive.seal(scope,mid)
                return mid
            original=ManifestArchive(base,bulk)
            legacy=put(original,old,"old")
            provision(base,"manifest",paths,offline_acknowledged=True)
            archive=ShardedManifestArchive(base,bulk)
            self.assertEqual(archive.read_chunk(old,legacy,0),raw)
            first=put(archive,new,"new-first")
            second=put(archive,new,"new-second")
            self.assertEqual(owner_path(base,"manifest",new),paths[4])
            self.assertEqual(archive.usage(new)["unique_chunks"],1)
            with self.assertRaises(StorageHeld):archive.read_chunk(old,first,0)
            archive.abort(new,first)
            archive.collect_manifest(new,first)
            self.assertEqual(archive.read_chunk(new,second,0),raw)
            reopened=ShardedManifestArchive(base,bulk)
            self.assertEqual(reopened.read_chunk(new,second,0),raw)
            reopened.abort(new,second)
            reopened.collect_manifest(new,second)
            self.assertEqual(reopened.usage(new)["unique_chunks"],0)
            self.assertEqual(reopened.read_chunk(old,legacy,0),raw)
            self.assertEqual(reopened.ledger_paths(),paths)
