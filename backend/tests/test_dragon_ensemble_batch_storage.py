"""Real trained ensemble execution and actual batched archive I/O tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from core.dragon_hoarder_bulk import BulkArchive,Volume,StorageHeld,GIB
from core.dragon_hoarder_manifests import ManifestArchive,BLOCK
from core.dragon_content_chunks import lengths,split
from core.dragon_archive_migration import compact_pair
from core.dragon_chunk_qualification import fixture
from skeleton.ai.webcrawler.dragon_specialist import DragonSpecialist
from skeleton.ai.webcrawler.navigation_semantics import digest,tournament,semantic_features

SCOPE={"tenant_id":"test","owner_id":"archive-v2"}
OTHER={"tenant_id":"test","owner_id":"foreign"}
ROOT=Path(__file__).resolve().parents[2]
WEIGHT=ROOT/"skeleton/ai/webcrawler/models/dragon_navigation_ranker.v2.json"


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.primary=self.store("primary")
        self.backup=self.store("backup")

    def store(self,name):
        path=self.path/name
        path.mkdir(mode=0o700,exist_ok=True)
        vol=path/"volume";vol.mkdir(mode=0o700,exist_ok=True)
        return ManifestArchive(path/"manifests.sqlite3",BulkArchive((Volume(name,vol,GIB),)))

    def start(self,store,raw,operation,adaptive=True):
        layout=lengths(raw) if adaptive else None
        kwargs={"chunk_lengths":layout} if layout is not None else {}
        begun=store.begin(SCOPE,logical_key="archive",operation=operation,
            expected_hash=hashlib.sha256(raw).hexdigest(),expected_bytes=len(raw),**kwargs)
        parts=list(split(raw,layout) if layout is not None else (raw[i:i+BLOCK] for i in range(0,len(raw),BLOCK)))
        return begun["manifest"],parts

    def test_batched_volume_dedup_and_owner_boundary(self):
        raw=fixture(21,0,512*1024)
        chunks=[raw[:64000],raw[:64000],raw[64000:128000]]
        result=self.primary.bulk.put_many("primary",SCOPE,chunks)
        self.assertEqual(result[0],result[1])
        self.assertEqual(self.primary.bulk.read_many(SCOPE,result),chunks)
        self.assertRaises(StorageHeld,self.primary.bulk.read_many,OTHER,result)
        with self.primary.bulk._db(self.primary.bulk.volumes["primary"]) as db:
            self.assertEqual(db.execute("SELECT objects FROM usage").fetchone()[0],2)

    def test_volume_failure_rolls_back_transaction(self):
        raw=fixture(22,0,512*1024)
        fresh=raw[:64000]
        corrupt=raw[64000:128000]
        self.primary.bulk.put("primary",SCOPE,corrupt)
        with self.primary.bulk._db(self.primary.bulk.volumes["primary"]) as db:
            db.execute("UPDATE objects SET payload=zeroblob(compressed_bytes) WHERE digest=?",(hashlib.sha256(corrupt).hexdigest(),))
        with self.assertRaises(StorageHeld):
            self.primary.bulk.put_many("primary",SCOPE,[fresh,corrupt])
        self.assertIsNone(self.primary.bulk.lookup("primary",SCOPE,hashlib.sha256(fresh).hexdigest()))

    def test_batch_replay_and_coherent_document_read(self):
        raw=fixture(23,0,1024*1024)
        mid,parts=self.start(self.primary,raw,"restart")
        original=self.primary.bulk.put_many
        def fail_after_commit(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError("interrupted after volume commit")
        with patch.object(self.primary.bulk,"put_many",side_effect=fail_after_commit):
            with self.assertRaises(RuntimeError):self.primary.append_many(SCOPE,mid,0,parts)
        self.primary=self.store("primary")
        self.primary.append_many(SCOPE,mid,0,parts)
        self.primary.seal(SCOPE,mid)
        self.assertEqual(self.primary.read_document(SCOPE,mid),raw)
        with self.assertRaises(StorageHeld):self.primary.read_document(SCOPE,mid,maximum_bytes=len(raw)-1)
        with self.assertRaises(StorageHeld):self.primary.read_document(OTHER,mid)

    def test_two_plane_mixed_layout_restart(self):
        raw=fixture(24,0,1024*1024)
        mid,parts=self.start(self.primary,raw,"dual",adaptive=False)
        other,second=self.start(self.backup,raw,"dual",adaptive=False)
        self.assertEqual(mid,other)
        for store,items in ((self.primary,parts),(self.backup,second)):
            store.append_many(SCOPE,mid,0,items);store.seal(SCOPE,mid)
        mark={"manifest":mid,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"qualification_digest":"a"*64}
        # Physical fixture stores are distinct files but not independently
        # qualified devices. Only the source topology gate is stubbed.
        with patch.object(self.primary,"migrate_content_defined",side_effect=StorageHeld("interrupted after backup")):
            with self.assertRaises(StorageHeld):compact_pair(self.primary,self.backup,SCOPE,mark,raw)
        self.assertEqual(self.primary.read_document(SCOPE,mid),raw)
        self.assertEqual(self.backup.read_document(SCOPE,mid),raw)
        result=compact_pair(self.primary,self.backup,SCOPE,mark,raw)
        self.assertTrue(result["backup"]["replayed"])
        self.assertTrue(result["primary"]["switched"])
        self.assertTrue(result["both_payloads_readback_verified"])

    def test_batch_workload_observed_rates(self):
        raw=fixture(25,0,2*1024*1024)
        mid,parts=self.start(self.primary,raw,"batch")
        t=time.perf_counter()
        self.primary.append_many(SCOPE,mid,0,parts)
        self.primary.seal(SCOPE,mid)
        written=time.perf_counter()-t
        t=time.perf_counter()
        self.assertEqual(self.primary.read_document(SCOPE,mid),raw)
        read=time.perf_counter()-t
        print("DRAGON_BATCH_PHYSICAL_RECEIPT "+json.dumps({"bytes":len(raw),"chunks":len(parts),
            "write_seconds":written,"read_seconds":read,"device":self.path.stat().st_dev,
            "production_qualified":False},sort_keys=True))


class EnsembleTests(unittest.TestCase):
    def setUp(self):
        raw=WEIGHT.read_bytes()
        self.pin=hashlib.sha256(raw).hexdigest()
        self.model=DragonSpecialist.from_bytes(raw,self.pin)

    def packet(self):
        terms=[["flight","navigation"],["flight","manual"],["garden","soil"],["aerodynamics","training"],
               ["aircraft","propulsion"],["market","price"],["navigation","route"],["flight","landing"]]
        rows=[{"id":hashlib.sha256(str(i).encode()).hexdigest(),"terms":ts,"depth":i%3,"attempts":i%2,
               "semantic":round(semantic_features("flight navigation","https://fixture.example/"+"/".join(ts))["score"]*1000)}
              for i,ts in enumerate(terms)]
        body={"snapshot_digest":"a"*64,"as_of":1700000000,"objective":["flight","navigation"],"candidates":rows}
        return {**body,"packet_digest":digest(body)}

    def test_real_ensemble_executes_bounded_lookahead(self):
        packet=self.packet();first=list(range(8,0,-1))
        rank,receipt=self.model.rank(packet,first)
        self.assertEqual(sorted(rank),list(range(1,9)))
        self.assertEqual(receipt["member_count"],3)
        self.assertEqual(receipt["model_digest"],self.pin)
        self.assertLessEqual(receipt["planner"]["numeric_evaluations"],receipt["planner"]["evaluation_limit"])
        self.assertEqual(receipt["output_digest"],digest(rank))
        self.assertEqual(receipt["execution_receipt_digest"],digest({k:v for k,v in receipt.items() if k!="execution_receipt_digest"}))
        self.assertEqual(self.model.rank(packet,first),(rank,receipt))
        self.assertFalse(receipt["confidence_is_calibrated_probability"])

    def test_ensemble_tensor_tamper_and_model_pin(self):
        value=json.loads(WEIGHT.read_bytes())
        value["members"][0]["input"][0].pop()
        raw=json.dumps(value).encode()
        with self.assertRaises(ValueError):DragonSpecialist.from_bytes(raw,hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):DragonSpecialist.from_bytes(WEIGHT.read_bytes(),"f"*64)

    def test_strong_candidate_outranks_unrelated_retries(self):
        relevant=self.model.score([.9,.9,.9,.8,.7,0,0,.5,.8,.8])
        weak=self.model.score([.1,.1,.1,.1,.9,1,1,.9,.8,.1])
        self.assertGreater(relevant,weak)


if __name__=="__main__":unittest.main()
