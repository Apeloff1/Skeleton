"""Exact indexed source identity and bounded large-corpus navigation fixtures.

All generated fixture locators remain in temporary SQLite files. They are
not real-world source-count evidence and never reach a network transport.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.source_catalogue_index import (
    DB_NAME, MAX_LANE, MAX_REPRESENTATIVES, MAX_SEED_SCAN, MAX_SOURCES,
    MAX_TERMS, TARGET, IndexedCatalogue, build_index,
)
from skeleton.ai.webcrawler.source_navigation import (
    INDEX_ENV, REGISTRY_PATH, SCHEMA, catalogue, objective,
    packaged_catalogue_bytes, rank_sources, source_record,
)
from skeleton.ai.webcrawler.operations import implementation_digest


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def row(name,url,family="engine-tools",tags="game tools rendering documentation"):
    return {"name":name,"url":url,"family":family,"kind":"documentation","tags":tags}


def spec(path,rows,number=1):
    h=hashlib.sha256()
    with path.open("wb") as f:
        for record in rows:
            data=json.dumps(record,ensure_ascii=True,separators=(",",":")).encode()+b"\n"
            h.update(data)
            f.write(data)
    return {"path":str(path),"sha256":h.hexdigest(),
            "publisher":f"https://example.org/reviewed-export-{number}/",
            "rights_reference":"synthetic fixture only; no external access"}


class IndexTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.base=self.root/"base.json"
        self.rows=[
            row("Fixture origin","https://example.org/"),
            row("Fixture project","https://github.com/Fixture-Lab/Dragon/"),
            row("MarioWiki","https://www.mariowiki.com/","game-worlds","game wiki walkthrough"),
        ]
        self.raw=json.dumps({"schema":SCHEMA,"revision":"2026-11-17",
            "status":"candidate_registry_not_access_verified","sources":self.rows}).encode()
        self.base.write_bytes(self.raw)
        self.out=self.root/"generation"

    def build(self,rows,*,minimum=1,other=None):
        exports=[spec(self.root/"export.jsonl",rows)]
        if other is not None:
            exports.append(spec(self.root/"second.jsonl",other,2))
        return build_index(self.base,exports,self.out,base_sha256=sha(self.raw),minimum=minimum)

    def open(self):
        return IndexedCatalogue(self.out/"dragon_source_catalogue.index.json",base_path=self.base)

    def test_exact_identity_and_cross_export_witnesses(self):
        first=row("Xenolith terrain editor","https://example.org/terrain/",
                  "game-worlds","xenolith labyrinth level editor")
        second=row("Independent export","https://example.net/tools/")
        alias=dict(self.rows[1],url="https://github.com/fixture-lab/dragon/")
        receipt=self.build([first,first,alias],other=[first,second],minimum=5)
        self.assertEqual(receipt["sources"],5)
        self.assertEqual(receipt["exports"][0]["duplicate"],1)
        self.assertEqual(receipt["exports"][0]["conflict"],1)
        self.assertEqual(receipt["exports"][1]["duplicate"],1)
        self.assertFalse(receipt["network_authorized"])
        self.assertFalse(receipt["rights_verified"])
        registry=self.open()
        self.assertEqual(len(registry.rows),5)
        self.assertEqual(registry.match("https://example.org/terrain/manual/").name,first["name"])
        self.assertEqual(registry.match("https://github.com/fixture-lab/dragon/issues").id,
                         source_record(self.rows[1]).id)
        self.assertEqual(registry.match("https://example.org/terrain-other/").name,"Fixture origin")
        self.assertIsNone(registry.match("https://example.org.evil.net/terrain/"))
        self.assertIsNone(registry.match("https://user@example.org/terrain/"))
        self.assertIsNone(registry.match("https://example.org:8443/terrain/"))
        self.assertIsNone(registry.match("http://example.org/terrain/"))
        self.assertEqual(registry.by_id.get(source_record(first).id).name,first["name"])
        with registry.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM witnesses").fetchone()[0],7)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM sources")
        p=rank_sources("xenolith labyrinth terrain",limit=4,registry=registry)
        self.assertTrue(p["rank_search_is_bounded"])
        self.assertIn(source_record(first).id,{r["source_id"] for r in p["sources"]})
        self.assertTrue(all(not r["network_authorized"] for r in p["sources"]))
        self.assertFalse(p["source_rights_granted"])

    def test_compound_publisher_alias_survives_index(self):
        self.build([row("Other title","https://example.net/manual/")])
        p=rank_sources("Super Mario Nintendo historical games",limit=3,registry=self.open())
        self.assertIn("www.mariowiki.com",{r["host"] for r in p["sources"]})

    def test_minimum_and_digest_fail_without_publish(self):
        entry=row("Fixture","https://example.net/project/")
        with self.assertRaisesRegex(ValueError,"minimum populated"):
            self.build([entry],minimum=12)
        self.assertFalse((self.out/DB_NAME).exists())
        pin=spec(self.root/"wrong.jsonl",[entry])
        pin["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"export digest"):
            build_index(self.base,[pin],self.out,base_sha256=sha(self.raw),minimum=1)
        self.assertFalse((self.out/"dragon_source_catalogue.index.json").exists())
        self.assertFalse(list(self.out.glob(".dragon-index-*")))

    def test_malformed_and_private_locators_rejected(self):
        for bad in ("https://host.internal/resource/","https://example.org/?key=abc",
                    "https://user@example.org/","https://127.0.0.1/","file:///etc/passwd",
                    "https://example.org/../resource/"):
            with self.subTest(url=bad):
                with self.assertRaises(ValueError):
                    self.build([row("Bad",bad)])
                self.assertFalse((self.out/DB_NAME).exists())

    def test_pinned_reader_rejects_mutation_and_sidecars(self):
        self.build([row("Fixture","https://example.net/project/")])
        reg=self.open()
        self.assertGreater(reg.summary()["sources"],3)
        sidecar=self.out/(DB_NAME+"-wal")
        sidecar.write_bytes(b"not a journal")
        with self.assertRaises(ValueError):
            reg.summary()
        sidecar.unlink()
        with (self.out/DB_NAME).open("ab") as f:
            f.write(b"tamper")
        with self.assertRaises(ValueError):
            reg.match("https://example.net/project/")
        with self.assertRaises(ValueError):
            self.open()

    def test_packaged_shards_and_checkpoint_generation_pin(self):
        with patch.dict(os.environ,{INDEX_ENV:""},clear=False):
            with self.assertRaises(ValueError):
                catalogue()
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop(INDEX_ENV,None)
            package=packaged_catalogue_bytes()
            count=len(json.loads(package)["sources"])
            self.assertGreaterEqual(count,6599)
            self.assertEqual(catalogue().summary()["sources"],count)
            self.assertGreaterEqual(catalogue().summary()["hosts"],1379)
            before=implementation_digest()
            exports=[spec(self.root/"activation.jsonl",
                [row("Indexed activation fixture","https://example.net/activation/")])]
            build_index(REGISTRY_PATH,exports,self.out,base_sha256=sha(package),minimum=count+1)
            with patch.dict(os.environ,{INDEX_ENV:str(self.out/"dragon_source_catalogue.index.json")}):
                self.assertEqual(catalogue().summary()["sources"],count+1)
                self.assertNotEqual(implementation_digest(),before)
                self.assertFalse(catalogue().summary()["network_authorized"])
            self.assertEqual(implementation_digest(),before)


class HundredfoldPhysicalFixture(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("SKL_DRAGON_SOURCE_INDEX_SCALE")=="389400",
                         "explicit physical hundredfold fixture job")
    def test_actual_disk_generation_at_389400_candidates(self):
        self.assertEqual(TARGET,389400)
        self.assertGreaterEqual(MAX_SOURCES,TARGET)
        package=packaged_catalogue_bytes()
        prior=len(json.loads(package)["sources"])
        remaining=TARGET-prior
        self.assertGreater(remaining,0)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def rows():
                for n in range(remaining):
                    special=n==remaining-1
                    yield row("Xenolith Labyrinth Navigation" if special else f"Synthetic library {n}",
                              f"https://github.com/dragon-index-fixture/project-{n}/",
                              "game-worlds" if special else "engine-tools",
                              "xenolith labyrinth navigation" if special else "fixture game tooling")
            pin=spec(root/"fixture.jsonl",rows())
            start=time.perf_counter()
            manifest=build_index(REGISTRY_PATH,[pin],root/"generation",
                                 base_sha256=sha(package),minimum=TARGET)
            build_seconds=time.perf_counter()-start
            self.assertEqual(manifest["sources"],TARGET)
            self.assertTrue(manifest["target_reached"])
            start=time.perf_counter()
            reg=IndexedCatalogue(root/"generation"/"dragon_source_catalogue.index.json")
            opened_seconds=time.perf_counter()-start
            self.assertEqual(reg.summary()["sources"],TARGET)
            task=objective("xenolith labyrinth navigation")
            start=time.perf_counter()
            candidates=list(reg.candidate_rows(task,None,set()))
            read_seconds=time.perf_counter()-start
            self.assertLessEqual(len(candidates),MAX_SEED_SCAN+MAX_TERMS*MAX_LANE+10*MAX_REPRESENTATIVES)
            target=reg.match(f"https://github.com/dragon-index-fixture/project-{remaining-1}/docs")
            self.assertIsNotNone(target)
            self.assertIn(target.id,{s.id for s in candidates})
            result=rank_sources("xenolith labyrinth navigation",limit=48,registry=reg)
            self.assertIn(target.id,{s["source_id"] for s in result["sources"]})
            self.assertGreater(result["distinct_hosts"],1)
            self.assertFalse(result["network_authorized"])
            print("DRAGON_SOURCE_INDEX_SCALE_RECEIPT",json.dumps({
                "synthetic_fixture_sources":TARGET,"packaged_seed_sources":prior,
                "file_bytes":manifest["file_bytes"],"build_seconds":round(build_seconds,3),
                "verified_open_seconds":round(opened_seconds,3),"candidate_seconds":round(read_seconds,3),
                "scored_candidate_bound":len(candidates),"network_authorized":False,
                "production_population_verified":False,"production_device_verified":False,
            },sort_keys=True))


if __name__=="__main__":
    unittest.main()
