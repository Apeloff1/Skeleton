"""Storage-bound semantic posting generations; no external model or Mongo required."""
from types import SimpleNamespace
from unittest import TestCase,IsolatedAsyncioTestCase
from bson import Binary

from core import dragon_posting_lineage as lineage


class LineageTests(TestCase):
    def fixture(self):
        return SimpleNamespace(database={"dragon_current_full_vector_postings":"old-current","dragon_full_vector_postings":"old-archive"},
            sessions=object(),_cutover_requested=True,_cutover_active=True,
            _derived_database={"dragon_current_full_vector_postings":"new-current","dragon_full_vector_postings":"new-archive"},
            _derived_epochs={"current":"a"*64,"archive":"b"*64})

    def test_no_legacy_postings_after_cutover(self):
        app=self.fixture()
        self.assertEqual(lineage.collection(app,"current"),"new-current")
        self.assertEqual(lineage.collection(app,"archive"),"new-archive")
        app._cutover_active=False
        with self.assertRaises(ValueError):lineage.collection(app,"current")
        app._cutover_requested=False
        self.assertEqual(lineage.collection(app,"current"),"old-current")

    def test_epoch_rebuild_claim_is_bounded_and_replay_safe(self):
        app=self.fixture();field="deep_full_due"
        self.assertIn({field+"_storage_epoch":{"$ne":"b"*64}},lineage.due_predicate(app,"archive",field,10))
        old={field:999999}
        self.assertEqual(lineage.claim_filter(app,"archive",field,old),{field+"_storage_epoch":{"$exists":False}})
        self.assertEqual(lineage.claim_update(app,"archive",field,"deep_full_state",100,old),
                         {"$set":{field:100,field+"_storage_epoch":"b"*64},"$unset":{"deep_full_state":""}})
        current={field:100,field+"_storage_epoch":"b"*64}
        self.assertNotIn("$unset",lineage.claim_update(app,"archive",field,"deep_full_state",200,current))
        self.assertEqual(lineage.state_filter(app,"archive",field),{field+"_storage_epoch":"b"*64})
        first=lineage.generation(app,"archive","legacy")
        self.assertEqual(first,lineage.generation(app,"archive","legacy"))
        app._derived_epochs["archive"]="c"*64
        self.assertNotEqual(first,lineage.generation(app,"archive","legacy"))

    def test_legacy_generation_unchanged(self):
        app=SimpleNamespace()
        self.assertEqual(lineage.generation(app,"archive","legacy"),"legacy")
        self.assertEqual(lineage.state_filter(app,"archive","due"),{})
        self.assertEqual(lineage.claim_update(app,"archive","due","state",12,{}),{"$set":{"due":12}})


class Target:
    def __init__(self):self.ids={};self.next=1
    async def command(self,cmd):
        name=cmd["filter"]["name"]
        rows=[] if name not in self.ids else [{"name":name,"type":"collection","options":{},
               "info":{"uuid":Binary(self.ids[name].to_bytes(16,"big"))}}]
        return {"cursor":{"firstBatch":rows}}
    async def create_collection(self,name):
        self.ids[name]=self.next;self.next+=1


class LineageIdentityTests(IsolatedAsyncioTestCase):
    async def test_recreated_collection_rotates_only_its_generation(self):
        target=Target()
        original=await lineage.prepare(target,"a"*64)
        self.assertEqual(await lineage.prepare(target,"a"*64),original)
        del target.ids[lineage.NAMES["current"]]
        changed=await lineage.prepare(target,"a"*64)
        self.assertEqual(original["archive"],changed["archive"])
        self.assertNotEqual(original["current"],changed["current"])
