"""Focused regression suite for bulk storage and game catalogue."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import collections
import os
import sqlite3

from core.dragon_game_corpus import CatalogueHeld, GameCorpus
from core.dragon_hoarder_bulk import BulkArchive, GIB, StorageHeld, Volume

SCOPE = {"tenant_id":"tenant-1","owner_id":"owner-1"}
OTHER = {"tenant_id":"tenant-1","owner_id":"owner-2"}


class GameCorpusTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "catalogue.sqlite"
        self.corpus = GameCorpus(self.path)
        self.event = dict(namespace="steam",external_id="123",title="Example Game",
                          stage="announced",source="https://example.org/wiki",
                          kind="official_wiki",language="en",event_key="first",
                          version=None,released_on=None)

    def observe(self, **changes):
        return self.corpus.observe(SCOPE,**{**self.event,**changes})

    def test_release_and_distinct_historical_revisions(self):
        original = self.observe()
        with patch("core.dragon_game_corpus.time.time",return_value=2000000000):
            new = self.observe(event_key="release",stage="released",
                               version="1.0",released_on="2033-01-01",title="Example Deluxe")
        self.assertEqual(original["game_id"],new["game_id"])
        self.assertEqual(self.corpus.search(SCOPE,"Deluxe")["games"][0]["game_id"],new["game_id"])
        sources = self.corpus.sources(SCOPE,new["game_id"])["sources"]
        self.assertEqual(sources[0]["latest_observation"]["stage"],"released")
        page = self.corpus.history(SCOPE,new["game_id"],limit=1)
        self.assertEqual(page["observations"][0]["payload"]["version"],"1.0")
        older = self.corpus.history(SCOPE,new["game_id"],before=page["next_cursor"])
        self.assertEqual(older["observations"][0]["payload"]["stage"],"announced")
        self.assertFalse(new["crawl_authorized"])
        self.assertFalse(new["wiki_approved"])

    def test_replay_cannot_replace_history_or_postpone_watch(self):
        original = self.observe()
        with patch("core.dragon_game_corpus.time.time",return_value=3000000000):
            replay = self.observe()
            self.assertTrue(replay["replayed"])
            self.assertEqual(original["observation_digest"],replay["observation_digest"])
            self.assertEqual(len(self.corpus.due(SCOPE)["review_candidates"]),1)
        with self.assertRaises(CatalogueHeld):
            self.observe(stage="released")
        self.assertEqual(len(self.corpus.history(SCOPE,original["game_id"])["observations"]),1)

    def test_independent_game_wikis_and_owner_boundaries(self):
        first = self.observe()
        second = self.observe(source="https://community.example.org/game",
                              kind="community_wiki",language="no")
        self.assertNotEqual(first["source_id"],second["source_id"])
        self.assertEqual(len(self.corpus.sources(SCOPE,first["game_id"])["sources"]),2)
        self.assertEqual(self.corpus.search(OTHER,"Example")["games"],[])
        self.assertEqual(self.corpus.history(OTHER,first["game_id"])["observations"],[])
        self.assertEqual(self.corpus.sources(OTHER,first["game_id"])["sources"],[])
        self.assertEqual(self.corpus.due(OTHER)["review_candidates"],[])

    def test_source_metadata_is_not_network_authority(self):
        for url in ("http://example.org", "https://a:b@example.org/", "https://example.org/?token=x",
                    "https://example.org:444/", "https://example.org/#secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.observe(source=url)
        with self.assertRaises(ValueError):
            self.observe(released_on="2026-02-30")
        self.assertEqual(self.corpus.search(SCOPE,"Example")["games"],[])


class BulkArchiveTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        if os.name == "posix":
            self.root.chmod(0o700)
        self.volume = Volume("primary",self.root,2*GIB)
        self.archive = BulkArchive((self.volume,))
        disk = collections.namedtuple("Disk","total used free")
        self.disk = patch("core.dragon_hoarder_bulk.shutil.disk_usage",
                          return_value=disk(10*GIB,0,10*GIB))
        self.disk.start()
        self.addCleanup(self.disk.stop)

    def test_dedup_restart_integrity_and_scope(self):
        payload = b"historical game wiki revision"*1000
        receipt = self.archive.put("primary",SCOPE,payload)
        self.assertEqual(self.archive.put("primary",SCOPE,payload),receipt)
        self.assertEqual(self.archive.capacity()[0]["objects"],1)
        other = self.archive.put("primary",OTHER,payload)
        self.assertNotEqual(other.scope_key,receipt.scope_key)
        self.assertEqual(self.archive.capacity()[0]["objects"],2)
        restarted = BulkArchive((self.volume,))
        self.assertEqual(restarted.read(SCOPE,receipt),payload)
        with self.assertRaises(StorageHeld):
            restarted.read(OTHER,receipt)
        with self.assertRaises(StorageHeld):
            restarted.read(SCOPE,replace(receipt,raw_bytes=1))
        self.assertTrue(restarted.erase_unreferenced(SCOPE,receipt))
        self.assertFalse(restarted.erase_unreferenced(SCOPE,receipt))
        self.assertEqual(restarted.read(OTHER,other),payload)

    def test_disk_reserve_rejects_new_objects(self):
        self.disk.stop()
        disk = collections.namedtuple("Disk","total used free")
        with patch("core.dragon_hoarder_bulk.shutil.disk_usage",return_value=disk(GIB,0,GIB)):
            with self.assertRaises(StorageHeld):
                self.archive.put("primary",SCOPE,b"new")
            self.assertEqual(self.archive.capacity()[0]["objects"],0)

    def test_corrupt_payload_cannot_be_returned_or_replayed(self):
        receipt = self.archive.put("primary",SCOPE,b"original"*32)
        with sqlite3.connect(self.root / "hoarder-payload-v1.sqlite3") as db:
            db.execute("UPDATE objects SET payload=zeroblob(compressed_bytes)")
        with self.assertRaises(StorageHeld):
            self.archive.read(SCOPE,receipt)
        with self.assertRaises(StorageHeld):
            self.archive.put("primary",SCOPE,b"original"*32)

    def test_same_filesystem_is_not_counted_twice(self):
        nested = self.root / "other"
        nested.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            BulkArchive((self.volume,Volume("another",nested,2*GIB)))
