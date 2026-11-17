"""Real disk migration and independent trained weight execution regressions."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.dragon_hoarder_bulk import BulkArchive,Volume,StorageHeld,GIB
from core.dragon_hoarder_manifests import ManifestArchive,BLOCK
from core import dragon_archive_migration as migration
from core.dragon_chunk_qualification import fixture
from skeleton.ai.webcrawler.dragon_specialist import DragonSpecialist
from skeleton.ai.webcrawler.navigation_semantics import digest,tournament

SCOPE={"tenant_id":"test","owner_id":"migration"}
OTHER={"tenant_id":"test","owner_id":"foreign"}
ROOT=Path(__file__).resolve().parents[2]
WEIGHTS=ROOT/"skeleton/ai/webcrawler/models/dragon_navigation_ranker.v1.json"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        volume=self.root/"volume";volume.mkdir(mode=0o700)
        self.spec=Volume("test",volume,GIB)
        self.store=self.reopen()

    def reopen(self):
        return ManifestArchive(self.root/"manifest.sqlite3",BulkArchive((self.spec,)))

    def fixed(self,raw,operation):
        row=self.store.begin(SCOPE,logical_key="legacy",operation=operation,
            expected_hash=hashlib.sha256(raw).hexdigest(),expected_bytes=len(raw))
        mid=row["manifest"]
        for i in range(0,len(raw),BLOCK):
            self.store.append(SCOPE,mid,i//BLOCK,raw[i:i+BLOCK])
        self.store.seal(SCOPE,mid)
        return mid

    def read(self,mid):
        with self.store._write() as db:
            row=self.store._manifest(db,migration.owner_key(SCOPE),mid,{"sealed"})
            return migration._read_locked(self.store,db,SCOPE,row)

    def test_staged_crash_reopen_atomic_switch_and_replay(self):
        raw=fixture(42,0,512*1024)
        mid=self.fixed(raw,"first")
        with patch.object(migration,"_switch",side_effect=RuntimeError("simulated interruption")):
            with self.assertRaises(RuntimeError):
                self.store.migrate_content_defined(SCOPE,mid,raw)
        self.store=self.reopen()
        self.assertEqual(self.store.read_chunk(SCOPE,mid,0),raw)
        result=self.store.migrate_content_defined(SCOPE,mid,raw)
        self.assertTrue(result["switched"])
        self.assertEqual(result["manifest"],mid)
        self.assertTrue(result["readback_verified"])
        self.assertEqual(self.read(mid),raw)
        self.assertTrue(self.store.migrate_content_defined(SCOPE,mid,raw)["replayed"])
        with self.assertRaises(StorageHeld):
            self.store.migrate_content_defined(OTHER,mid,raw)

    def test_revocation_during_staging_cleans_both_layouts(self):
        raw=fixture(43,0,512*1024)
        mid=self.fixed(raw,"first")
        with patch.object(migration,"_switch",side_effect=RuntimeError("simulated interruption")):
            with self.assertRaises(RuntimeError):
                self.store.migrate_content_defined(SCOPE,mid,raw)
        self.assertTrue(self.store.abort(SCOPE,mid))
        self.assertEqual(self.store.collect_manifest(SCOPE,mid,limit=128)["remaining"],0)
        self.assertEqual(self.store.usage(SCOPE)["unique_chunks"],0)
        with self.assertRaises(StorageHeld):
            self.store.migrate_content_defined(SCOPE,mid,raw)

    def test_real_existing_revision_compaction(self):
        a,b=fixture(44,0,1024*1024),fixture(44,1,1024*1024)
        first,second=self.fixed(a,"first"),self.fixed(b,"second")
        old=self.store.usage(SCOPE)["unique_compressed_bytes"]
        with self.assertRaises(StorageHeld):
            self.store.migrate_content_defined(SCOPE,first,b)
        self.store.migrate_content_defined(SCOPE,first,a)
        self.store.migrate_content_defined(SCOPE,second,b)
        self.assertLess(self.store.usage(SCOPE)["unique_compressed_bytes"],old)
        self.store=self.reopen()
        self.assertEqual(self.read(first),a);self.assertEqual(self.read(second),b)
        self.store.abort(SCOPE,first)
        self.store.collect_manifest(SCOPE,first,limit=128)
        self.assertEqual(self.read(second),b)


class SpecialistTests(unittest.TestCase):
    def setUp(self):
        self.raw=WEIGHTS.read_bytes()
        self.pin=hashlib.sha256(self.raw).hexdigest()
        self.model=DragonSpecialist.from_bytes(self.raw,self.pin)

    def packet(self):
        rows=[{"id":hashlib.sha256(str(i).encode()).hexdigest(),
            "terms":["flight","navigation"] if i%2==0 else ["soil","garden"],
            "depth":i%4,"attempts":i%3,"semantic":900 if i%2==0 else 100} for i in range(48)]
        value={"snapshot_digest":"a"*64,"as_of":1700000000,"objective":["flight","navigation"],"candidates":rows}
        return {**value,"packet_digest":digest(value)}

    def test_weight_pin_and_numeric_inference(self):
        with self.assertRaises(ValueError):DragonSpecialist.from_bytes(self.raw,"f"*64)
        suited=self.model.score([.9,.9,.9,.8,.7,0,0,.9,.8,.8])
        weak=self.model.score([.1,.1,.1,.1,.2,1,1,.1,.2,.1])
        self.assertGreater(suited,weak)
        self.assertNotEqual(suited,weak)

    def test_independent_specialist_executes_all_nine_matches(self):
        proof=[]
        def execute(group,role,first,stage):
            if role=="jeeves":return list(range(1,len(group["candidates"])+1))
            rank,receipt=self.model.rank(group,first)
            self.assertEqual(receipt["model_digest"],self.pin)
            self.assertEqual(receipt["output_digest"],digest(rank))
            self.assertEqual(receipt["execution_receipt_digest"],digest({k:v for k,v in receipt.items() if k!="execution_receipt_digest"}))
            proof.append(receipt)
            return rank
        value=self.packet()
        result=tournament(value,execute)
        self.assertEqual(len(proof),9)
        self.assertEqual(result["packet_digest"],value["packet_digest"])
        self.assertTrue(result["dragon_rank"])


if __name__=="__main__":unittest.main()
