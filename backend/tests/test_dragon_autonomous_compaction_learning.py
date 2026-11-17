"""Focused source and physical fixture qualification; not live model/device evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from core import dragon_autonomous_discourse as discourse
from core.dragon_content_chunks import lengths,split,encode_layout,decode_layout
from core.dragon_chunk_qualification import qualify
from core.dragon_hoarder_bulk import BulkArchive,Volume,StorageHeld,GIB
from core.dragon_hoarder_manifests import ManifestArchive
from core.dragon_navigation_learning import calibrate,dense_scores
from skeleton.ai.webcrawler.navigation_semantics import digest,make_advice

SCOPE={"owner_id":"owner","tenant_id":"tenant"}
OTHER={"owner_id":"foreign","tenant_id":"tenant"}


class ChunkTests(unittest.TestCase):
    def test_layout_and_tamper(self):
        raw=hashlib.shake_256(b"fixture").digest(900000)
        layout=lengths(raw)
        self.assertEqual(b"".join(split(raw,layout)),raw)
        data,proof=encode_layout(layout,len(raw))
        self.assertEqual(decode_layout(data,proof,len(raw)),layout)
        with self.assertRaises(ValueError):decode_layout(data,"f"*64,len(raw))
        with self.assertRaises(ValueError):encode_layout([len(raw)],len(raw))

    def test_existing_fixed_manifest_replays_and_cdc_cannot_change_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);vol=root/"volume";vol.mkdir(mode=0o700)
            store=ManifestArchive(root/"manifest.sqlite3",BulkArchive((Volume("test",vol,GIB),)))
            raw=hashlib.shake_256(b"raw").digest(900000)
            kw=dict(logical_key="one",operation="first",expected_hash=hashlib.sha256(raw).hexdigest(),expected_bytes=len(raw))
            first=store.begin(SCOPE,**kw)
            self.assertNotIn("chunk_lengths",store.begin(SCOPE,**kw,chunk_lengths=lengths(raw),allow_legacy=True))
            with self.assertRaises(StorageHeld):store.begin(SCOPE,**kw,chunk_lengths=lengths(raw))
            store.append(SCOPE,first["manifest"],0,raw)
            self.assertEqual(store.seal(SCOPE,first["manifest"])["sha256"],kw["expected_hash"])
            self.assertEqual(store.read_chunk(SCOPE,first["manifest"],0),raw)
            kw["operation"]="second"
            mid=store.begin(SCOPE,**kw,chunk_lengths=lengths(raw))
            first_part=next(split(raw,mid["chunk_lengths"]))
            store.append(SCOPE,mid["manifest"],0,first_part)
            with self.assertRaises(StorageHeld):store.seal(SCOPE,mid["manifest"])
            with self.assertRaises(StorageHeld):store.read_chunk(OTHER,mid["manifest"],0)
            for i,part in enumerate(split(raw,mid["chunk_lengths"])):
                store.append(SCOPE,mid["manifest"],i,part)
            self.assertEqual(store.seal(SCOPE,mid["manifest"])["sha256"],kw["expected_hash"])
            self.assertEqual(b"".join(store.read_chunk(SCOPE,mid["manifest"],i) for i in range(len(mid["chunk_lengths"]))),raw)
            with store._write() as db:
                db.execute("UPDATE manifest_layouts SET witness=? WHERE manifest=?",("f"*64,mid["manifest"]))
            with self.assertRaises(StorageHeld):store.read_chunk(SCOPE,mid["manifest"],0)

    def test_measured_physical_compaction(self):
        families=int(os.getenv("SKL_DRAGON_CHUNK_FIXTURE_FAMILIES","4"))
        with tempfile.TemporaryDirectory() as folder:
            receipt=qualify(folder,families=families,revisions=3,size=512*1024,scratch_acknowledged=True)
        self.assertGreater(receipt["compressed_payload_bytes_saved"],0)
        self.assertTrue(receipt["content_defined"]["restart_readback_verified"])
        self.assertTrue(receipt["content_defined"]["reference_collection_verified"])
        self.assertTrue(receipt["scratch_cleanup_verified"])
        self.assertFalse(receipt["production_workload_verified"])
        print("DRAGON_PHYSICAL_CHUNK_RECEIPT "+json.dumps(receipt,sort_keys=True))


class LearningTests(unittest.TestCase):
    def test_fit_operational_labels_and_heldout_gate(self):
        rows=[]
        for i in range(80):
            good=i%2==0
            rows.append({"id":f"{i:08x}"+"a"*56,
                "url":f"https://example.com/"+("flight/navigation/manual" if good else "gardening/soil")+f"/{i}",
                "lineage":1. if good else 0.,"feedback":{"phases":{"captured" if good else "error":8}}})
        scores,receipt=calibrate(rows,"flight navigation manual")
        self.assertEqual(receipt["status"],"heldout_improvement")
        self.assertLess(receipt["holdout_log_loss"],receipt["baseline_log_loss"])
        self.assertGreater(scores[rows[0]["id"]],scores[rows[1]["id"]])
        self.assertFalse(receipt["persisted"])
        scores,receipt=calibrate(rows[:2],"flight navigation")
        self.assertEqual(scores,{})
        self.assertEqual(receipt["status"],"insufficient_outcomes")

    def test_dense_contract_fixture_no_source_body_or_query_string(self):
        class FakeEncoder:
            dimensions=32
            identity="d"*64
            def __init__(self):self.seen=[]
            def encode(self,texts):
                self.seen.extend(texts)
                return [[1. if i==(0 if "flight" in t else 1) else 0. for i in range(32)] for t in texts]
        model=FakeEncoder()
        rows=[{"id":"a"*64,"url":"https://example.com/flight?token=secret"},
              {"id":"b"*64,"url":"https://example.com/garden"},
              {"id":"c"*64,"url":"https://example.com/flight"}]
        scores,receipt=dense_scores("flight",rows,model=model)
        self.assertGreater(scores["a"*64],scores["b"*64])
        self.assertEqual(scores["a"*64],scores["c"*64])
        self.assertEqual(receipt["unique_locator_representations"],2)
        self.assertTrue(all("secret" not in text and "https://" not in text for text in model.seen))


class DiscourseTests(unittest.TestCase):
    def test_owner_pinned_config_and_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/"token"
            token.write_text("x"*48)
            token.chmod(0o600)
            conf={"owner_digest":discourse.owner_binding(SCOPE),"port":8765,
                "token_file":str(token),"model_digest":"c"*64}
            packet={"snapshot_digest":"a"*64,"as_of":int(time.time()),"objective":["flight"],
                "candidates":[{"id":"b"*64,"terms":["flight"],"depth":0,"attempts":0,"semantic":1000}]}
            packet["packet_digest"]=digest(packet)
            advice=make_advice(packet,[1],[1])
            receipts=[{"role":role,"stage":"final","group_digest":packet["packet_digest"],"session_id":role,
                "execution_receipt_digest":"e"*64,"output_digest":"f"*64} for role in ("jeeves","dragon")]
            reply={"model_digest":"c"*64,"network_authorized":False,"single_local_model_two_roles":True,
                "candidate_count":1,"advice":advice,"role_receipts":receipts}
            class Response:
                status=200
                def read(self,maximum):return json.dumps(reply).encode()
            class Transport:
                def __init__(self,host,port,timeout):
                    if (host,port)!=("127.0.0.1",8765):raise AssertionError("non-loopback")
                def request(self,method,path,body,headers):
                    if path!="/v1/dragon/navigation-discourse":raise AssertionError("route")
                def getresponse(self):return Response()
                def close(self):pass
            with patch.dict(os.environ,{"SKL_DRAGON_AUTONOMOUS_DISCOURSE_JSON":json.dumps(conf)}),patch.object(discourse.http.client,"HTTPConnection",Transport):
                with self.assertRaises(discourse.DiscourseHeld):discourse.config(OTHER)
                result=discourse.advise(SCOPE,packet,grant_deadline=time.time()+90)
                self.assertEqual(result["advice"],advice)
                self.assertEqual(result["role_calls"],2)
                self.assertEqual(result["receipt"],digest({k:v for k,v in result.items() if k!="receipt"}))
                reply["model_digest"]="9"*64
                with self.assertRaises(discourse.DiscourseHeld):discourse.advise(SCOPE,packet,grant_deadline=time.time()+90)


if __name__=="__main__":unittest.main()
