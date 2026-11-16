"""Mongo relocation fixtures; real-server integration is explicitly opt-in."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,IsolatedAsyncioTestCase,skipUnless
from unittest.mock import patch
from uuid import uuid4

from bson import BSON,Binary
from bson.raw_bson import RawBSONDocument
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from core import dragon_mongo_relocation as move
from core import dragon_mongo_cutover as cutover
from core.dragon_graph_deployment import _json,_new_json


class RawCollection:
    def __init__(self):self.docs={}

    def insert_one(self,doc):
        if doc["_id"] in self.docs:raise DuplicateKeyError("fixture duplicate")
        self.docs[doc["_id"]]=doc

    def find_one(self,query):return self.docs.get(query["_id"])


def receipt():
    source={n:{"uuid":str(i+1)*32,"index_sha":"a"*64,
               "data":{"documents":0,"bytes":0,"sha256":"b"*64}}
            for i,n in enumerate(move.COLLECTIONS)}
    target={n:str(i+3)*32 for i,n in enumerate(move.COLLECTIONS)}
    value={"version":1,"source_db":"old_db","target_db":"new_db","source":source,
           "target":target,"verified":True}
    return {**value,"receipt_sha":hashlib.sha256(_json(value)).hexdigest(),
            "source_retained":True,"live_cutover_executed":False}


class RelocationUnitTests(TestCase):
    def test_raw_bson_replay_and_conflicting_bytes(self):
        store=RawCollection()
        doc=RawBSONDocument(BSON.encode({"_id":"one","value":Binary(b"bytes"),"version":7}))
        move._put_exact(store,doc)
        move._put_exact(store,doc)
        self.assertEqual(store.docs["one"].raw,doc.raw)
        conflict=RawBSONDocument(BSON.encode({"_id":"one","value":Binary(b"other"),"version":7}))
        with self.assertRaises(move.RelocationHeld):move._put_exact(store,conflict)
        self.assertEqual(store.docs["one"].raw,doc.raw)

    def test_receipt_requires_explicit_switch_and_exact_hash(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/"receipt.json"
            value=receipt()
            _new_json(path,value)
            env={"SKL_DRAGON_MONGO_CUTOVER":"1","SKL_DRAGON_MONGO_CUTOVER_RECEIPT":str(path),
                 "SKL_DRAGON_TARGET_MONGO_DB":"new_db","SKL_DRAGON_TARGET_MONGO_URL":"mongodb://127.0.0.1:27017"}
            with patch.dict(os.environ,env,clear=True):
                self.assertTrue(cutover.requested())
                self.assertEqual(cutover.load_receipt("old_db"),value)
                with self.assertRaises(move.RelocationHeld):cutover.load_receipt("other_db")
                os.environ["SKL_DRAGON_MONGO_CUTOVER"]="0"
                with self.assertRaises(move.RelocationHeld):cutover.load_receipt("old_db")
                os.environ["SKL_DRAGON_MONGO_CUTOVER"]="1"
                path.unlink()
                value["receipt_sha"]="f"*64
                _new_json(path,value)
                with self.assertRaises(move.RelocationHeld):cutover.load_receipt("old_db")

    def test_no_location_alias_or_unsupported_ids(self):
        for value in ("admin","local","config","a/b","",None):
            with self.assertRaises(move.RelocationHeld):move._name(value)
        for value in (None,0,"","\x00","x"*2049):
            with self.assertRaises(move.RelocationHeld):move._id(value)


class FakeJournal:
    def __init__(self,value):self.value=value
    async def find_one(self,*args,**kwargs):return self.value


class FakeTarget:
    name="new_db"

    def __init__(self,value):
        self.value=value
        self.journal={"phase":"verified","receipt_sha":value["receipt_sha"],
                      "source_db":value["source_db"],"target_db":value["target_db"],
                      "source":value["source"],"target":dict(value["target"])}
        self.uuids=dict(value["target"])

    def __getitem__(self,key):return FakeJournal(self.journal)

    async def command(self,cmd,*args,**kwargs):
        if cmd=="hello":return {"isWritablePrimary":True}
        if cmd=="ping":return {"ok":1}
        name=cmd["filter"]["name"]
        return {"cursor":{"firstBatch":[{"name":name,"type":"collection","options":{},
                  "info":{"uuid":Binary(bytes.fromhex(self.uuids[name]))}}]}}


class RemoteCutoverTests(IsolatedAsyncioTestCase):
    async def test_remote_journal_and_uuid_fence(self):
        value=receipt();target=FakeTarget(value)
        self.assertTrue(await cutover.verify_remote(target,value))
        target.journal["phase"]="copying"
        with self.assertRaises(move.RelocationHeld):await cutover.verify_remote(target,value)
        target.journal["phase"]="verified"
        target.uuids[move.COLLECTIONS[0]]="f"*32
        with self.assertRaises(move.RelocationHeld):await cutover.verify_remote(target,value)


@skipUnless(os.getenv("SKL_DRAGON_RELOCATION_TEST_MONGO_URL"),"requires disposable local Mongo fixture")
class MongoIntegrationTests(TestCase):
    def setUp(self):
        # Unique database names are generated internally; never use the
        # configured application DB or its collection names directly.
        uri=os.environ["SKL_DRAGON_RELOCATION_TEST_MONGO_URL"]
        self.client=MongoClient(uri,serverSelectionTimeoutMS=5000,w="majority",journal=True)
        token=uuid4().hex
        self.source=self.client["dragon_fixture_src_"+token]
        self.target=self.client["dragon_fixture_dst_"+token]
        self.addCleanup(self.client.close)
        self.addCleanup(self.client.drop_database,self.source.name)
        self.addCleanup(self.client.drop_database,self.target.name)
        for name in move.COLLECTIONS:
            self.source.create_collection(name)
            self.source[name].create_index([("tenant_id",1),("owner_id",1)])
            self.source[name].insert_many([{"_id":str(i).zfill(4),"tenant_id":"fixture","owner_id":"fixture",
                "version":i,"snapshot":{"raw":Binary(bytes([i%256]))},"status":"deleted" if i%2 else "completed"}
                for i in range(145)])

    def copy_all(self):
        move.prepare(self.source,self.target,offline_acknowledged=True)
        for _ in range(10):
            result=move.copy_pulse(self.source,self.target,batches=1,offline_acknowledged=True)
            if result["ready_for_verify"]:return
        self.fail("bounded copy never completed")

    def test_live_bson_indexes_and_restart(self):
        move.prepare(self.source,self.target,offline_acknowledged=True)
        first=move.copy_pulse(self.source,self.target,batches=1,offline_acknowledged=True)
        self.assertEqual(first["copied"],128)
        self.copy_all()
        result=move.verify(self.source,self.target,offline_acknowledged=True)
        self.assertTrue(result["verified"])
        for name in move.COLLECTIONS:
            self.assertEqual(move.fingerprint(move._raw(self.source,name)),move.fingerprint(move._raw(self.target,name)))
            self.assertEqual(self.source[name].count_documents({}),145)
        self.assertEqual(move.verify(self.source,self.target,offline_acknowledged=True),result)

    def test_source_drift_blocks_cutover(self):
        self.copy_all()
        self.source[move.COLLECTIONS[0]].update_one({"_id":"0000"},{"$set":{"version":999}})
        with self.assertRaises(move.RelocationHeld):move.verify(self.source,self.target,offline_acknowledged=True)
        self.assertEqual(move._state(self.target)["phase"],"copying")

    def test_target_extra_document_blocks_cutover(self):
        self.copy_all()
        self.target[move.COLLECTIONS[0]].insert_one({"_id":"unexpected"})
        with self.assertRaises(move.RelocationHeld):move.verify(self.source,self.target,offline_acknowledged=True)
        self.assertEqual(move._state(self.target)["phase"],"copying")
