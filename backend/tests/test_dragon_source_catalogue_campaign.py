"""Multi-publisher source campaign qualification, no network side effects."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.webcrawler.source_catalogue_campaign import SCHEMA,run_campaign
from skeleton.ai.webcrawler.source_catalogue_index import IndexedCatalogue
from skeleton.ai.webcrawler.source_navigation import SCHEMA as CATALOGUE_SCHEMA,rank_sources


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CampaignTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.inputs=self.root/"inputs"
        self.inputs.mkdir()
        self.work=self.root/"work"
        self.base=self.root/"base.json"
        self.base.write_bytes(json.dumps({
            "schema":CATALOGUE_SCHEMA,"revision":"2026-11-17",
            "status":"candidate_registry_not_access_verified",
            "sources":[{"name":"Fixture original publisher","url":"https://example.org/",
                        "family":"game-discovery","kind":"reference","tags":"fixture game"}],
        }).encode())
        self.plan_path=self.root/"plan.json"
        self.first=self.inputs/"one.csv"
        self.second=self.inputs/"two.csv"
        self.first.write_text("name,url\nFixture one,https://example.org/one\nFixture two,https://example.org/two\n")
        self.second.write_text("name,url\nFixture two,https://example.org/two\nFixture three,https://example.net/three\n")
        self.plan={"schema":SCHEMA,"minimum_sources":4,"base_sha256":sha(self.base.read_bytes()),
                   "exports":[self.export("first",self.first),self.export("second",self.second)]}

    def export(self,id,path):
        return {"id":id,"file":path.name,"sha256":sha(path.read_bytes()),
                "mode":"explicit-csv","publisher":"https://example.org/fixtures/",
                "rights_reference":"Synthetic fixture only; no network."}

    def publish_plan(self):
        raw=json.dumps(self.plan,sort_keys=True).encode()
        self.plan_path.write_bytes(raw)
        return sha(raw)

    def run_plan(self,pin=None):
        if pin is None:pin=self.publish_plan()
        return run_campaign(self.plan_path,plan_sha256=pin,input_root=self.inputs,
                            work_dir=self.work,base_path=self.base)

    def test_real_index_deduplication_and_idempotent_resume(self):
        pin=self.publish_plan()
        first=self.run_plan(pin)
        self.assertEqual(first["sources"],4)
        self.assertEqual(first["hosts"],2)
        self.assertEqual(first["normalized_exports"][1]["candidate_rows"],2)
        self.assertFalse(first["network_authorized"])
        self.assertFalse(first["target_389400_reached"])
        db=self.work/"index"/"dragon_source_catalogue.sqlite3"
        before=db.stat().st_mtime_ns
        self.assertEqual(self.run_plan(pin),first)
        self.assertEqual(db.stat().st_mtime_ns,before)
        registry=IndexedCatalogue(self.work/"index"/"dragon_source_catalogue.index.json",base_path=self.base)
        result=rank_sources("Fixture three",limit=4,registry=registry)
        self.assertIn("https://example.net/three",{r["url"] for r in result["sources"]})
        self.assertTrue(result["catalogue"]["indexed_generation"])

    def test_wrong_plan_digest_prevents_preparation(self):
        self.publish_plan()
        with self.assertRaisesRegex(ValueError,"plan digest"):
            self.run_plan("0"*64)
        self.assertFalse(self.work.exists())

    def test_minimum_holds_but_normalizations_survive(self):
        self.plan["minimum_sources"]=5
        pin=self.publish_plan()
        with self.assertRaisesRegex(ValueError,"minimum populated"):
            self.run_plan(pin)
        self.assertTrue((self.work/"normalized"/"first.jsonl").exists())
        self.assertFalse((self.work/"index"/"dragon_source_catalogue.index.json").exists())
        self.assertFalse((self.work/"campaign-receipt.json").exists())
        with self.assertRaisesRegex(ValueError,"minimum populated"):
            self.run_plan(pin)

    def test_changed_input_after_completed_receipt_fails(self):
        pin=self.publish_plan()
        self.run_plan(pin)
        self.second.write_text("name,url\nOther,https://example.net/other\n")
        with self.assertRaisesRegex(ValueError,"bytes or export receipt changed"):
            self.run_plan(pin)

    def test_changed_plan_cannot_reuse_directory(self):
        self.run_plan()
        self.plan["minimum_sources"]=3
        with self.assertRaisesRegex(ValueError,"different plan"):
            self.run_plan()

    def test_traversal_and_duplicate_identity_rejected(self):
        self.plan["exports"][0]["file"]="../base.json"
        with self.assertRaisesRegex(ValueError,"path component"):
            self.run_plan()
        self.plan["exports"][0]["file"]="one.csv"
        self.plan["exports"][1]["id"]="first"
        with self.assertRaisesRegex(ValueError,"duplicate identity"):
            self.run_plan()

    def test_orphan_generation_holds(self):
        self.work.mkdir()
        (self.work/"index").mkdir()
        (self.work/"index"/"dragon_source_catalogue.sqlite3").write_bytes(b"orphan")
        with self.assertRaisesRegex(ValueError,"publication incomplete"):
            self.run_plan()
        self.assertEqual((self.work/"index"/"dragon_source_catalogue.sqlite3").read_bytes(),b"orphan")

    def test_corrupted_normalized_bytes_hold(self):
        pin=self.publish_plan()
        self.run_plan(pin)
        path=self.work/"normalized"/"first.jsonl"
        path.write_bytes(path.read_bytes()+b"\n")
        with self.assertRaisesRegex(ValueError,"bytes or export receipt changed"):
            self.run_plan(pin)


if __name__=="__main__":
    unittest.main()
