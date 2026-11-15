"""Regression coverage for the expanded source directory and view boundaries."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,IsolatedAsyncioTestCase
from unittest.mock import AsyncMock,patch
from uuid import uuid4
import hashlib
import json
import sqlite3

from core.dragon_game_corpus import GameCorpus,source_url,CatalogueHeld,MAX_SOURCES
from core.dragon_game_taxonomy import SOURCE_CLASSES,FAMILIES,public_taxonomy,view_mode
from core.dragon_release_discovery import parse_manifest
from core import dragon_source_library as library

SCOPE={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}


class SourceDirectoryTests(TestCase):
    def setUp(self):
        self.dir=TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path=Path(self.dir.name)/"corpus.sqlite3"
        self.store=GameCorpus(self.path)

    def observe(self,kind="official_wiki",url="https://example.org/guide",event="v1",title="Example RPG",scope=SCOPE,language="en",external="g1"):
        return self.store.observe(scope,namespace="independent",external_id=external,title=title,stage="released",
            source=url,kind=kind,language=language,event_key=event,version=None,released_on=None)

    def test_533_distinct_classes_and_media_preferences(self):
        taxonomy=public_taxonomy()
        self.assertGreaterEqual(len(SOURCE_CLASSES),533)
        self.assertGreaterEqual(len(FAMILIES),24)
        self.assertEqual(len({x["kind"] for x in taxonomy["source_classes"]}),len(SOURCE_CLASSES))
        self.assertEqual(view_mode("official_screenshot"),"image")
        self.assertEqual(view_mode("gameplay_video"),"video")
        self.assertEqual(view_mode("soundtrack_preview"),"audio")
        self.assertEqual(view_mode("pdf_manual"),"document")
        self.assertEqual(view_mode("interactive_map_reference"),"external")
        self.assertFalse(taxonomy["source_use_authority"])

    def test_public_media_url_canonical_and_untrusted_queries_rejected(self):
        expected="https://youtu.be/AbCdEf0123_"
        self.assertEqual(source_url("https://www.youtube.com/watch?v=AbCdEf0123_"),expected)
        self.assertEqual(source_url(expected),expected)
        for bad in ("https://www.youtube.com/watch?v=AbCdEf0123_&token=secret",
                    "https://example.org/guide?secret=token","https://127.0.0.1/a",
                    "https://foo.local/manual","https://u:p@example.org/a","http://example.org/a"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                source_url(bad)

    def test_media_manifest_and_category_facets(self):
        raw=json.dumps({"schema":"dragon.game-feed.v1","provider":"youtube","entries":[
            {"id":"g1","title":"Example RPG","links":[{"url":"https://www.youtube.com/watch?v=AbCdEf0123_",
             "kind":"gameplay_video","language":"en"}]}]}).encode()
        proposed=parse_manifest(raw)[0]
        video=self.store.observe(SCOPE,**proposed.observation())
        self.assertEqual(self.store.sources(SCOPE,video["game_id"],family="moving_media")["sources"][0]["view_mode"],"video")
        game=self.observe()
        self.observe("pdf_manual","https://example.org/manual.pdf",language="ja")
        self.assertEqual(len(self.store.sources(SCOPE,game["game_id"],family="documents",language="ja")["sources"]),1)
        self.assertFalse(self.store.sources(OTHER,game["game_id"])["sources"])
        with self.assertRaises(ValueError):
            self.store.sources(SCOPE,game["game_id"],kind="unknown_category")

    def test_global_locator_index_update_and_scope(self):
        self.observe("official_wiki","https://example.org/boss-guide",title="Old RPG")
        self.observe("official_wiki","https://example.org/boss-guide",event="v2",title="New RPG")
        self.observe("gameplay_video","https://youtu.be/AbCdEf0123_",title="New RPG")
        self.observe("official_wiki","https://other.example.org/boss-guide",title="Private RPG",scope=OTHER)
        found=self.store.search_source_library(SCOPE,"New RPG boss",kind="official_wiki")
        self.assertEqual(len(found["sources"]),1)
        self.assertEqual(found["sources"][0]["latest_observation"]["title"],"New RPG")
        self.assertFalse(self.store.search_source_library(SCOPE,"Old RPG")["sources"])
        self.assertFalse(self.store.search_source_library(SCOPE,"Private RPG")["sources"])
        self.assertFalse(found["source_use_authorized"])

    def test_source_index_backfill_is_restart_safe(self):
        self.observe("pdf_manual","https://example.org/manual.pdf")
        self.observe("community_wiki","https://example.org/wiki")
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM source_locator_fts")
            db.execute("DELETE FROM source_locator_rows")
        self.assertFalse(self.store.search_source_library(SCOPE,"manual")["sources"])
        a=self.store.backfill_source_locators(limit=1)
        b=GameCorpus(self.path).backfill_source_locators(limit=1)
        c=GameCorpus(self.path).backfill_source_locators(limit=1)
        self.assertEqual(a["indexed"]+b["indexed"]+c["indexed"],2)
        self.assertTrue(c["complete"])
        self.assertTrue(self.store.search_source_library(SCOPE,"manual")["index_backfill_complete"])

    def test_transactional_source_count_legacy_initialization_and_quota(self):
        first=self.observe()
        self.assertEqual(MAX_SOURCES,20_000_000)
        # Simulate the first write following an older catalogue migration.
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM game_source_counts")
        self.observe("pdf_manual","https://example.org/manual.pdf")
        self.observe(event="v2")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT total FROM game_source_counts WHERE game=?",(first["game_id"],)).fetchone()[0],2)
        with patch("core.dragon_game_corpus.MAX_SOURCES",2):
            with self.assertRaises(CatalogueHeld):
                self.observe("gameplay_video","https://youtu.be/AbCdEf0123_")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT total FROM game_source_counts WHERE game=?",(first["game_id"],)).fetchone()[0],2)

    def test_bound_capture_history_is_game_source_and_owner_specific(self):
        wiki=self.observe()
        other=self.observe("pdf_manual","https://example.org/manual.pdf")
        sid=str(uuid4())
        self.store.bind_capture(SCOPE,game=wiki["game_id"],source=wiki["source_id"],
                                observation_digest=wiki["observation_digest"],session=sid)
        page=self.store.source_captures(SCOPE,wiki["game_id"],wiki["source_id"])
        self.assertEqual(page["captures"][0]["session_id"],sid)
        self.assertFalse(page["source_use_authorized"])
        self.assertFalse(self.store.source_captures(SCOPE,other["game_id"],other["source_id"])["captures"])
        with self.assertRaises(LookupError):
            self.store.inspect_capture_binding(OTHER,wiki["game_id"],wiki["source_id"],sid)
        with self.assertRaises(LookupError):
            self.store.inspect_capture_binding(SCOPE,other["game_id"],other["source_id"],sid)


class SourceComparisonTests(IsolatedAsyncioTestCase):
    def pin(self,session):
        return {"session":session,"capture_source":"a"*64,"offset":0,"length":4000,
                "session_version":1,"snapshot_digest":"b"*64,"preserved_text_hash":"c"*64,"history_only":True}

    async def test_exact_window_diff_and_authority_recheck(self):
        a,b=self.pin(str(uuid4())),self.pin(str(uuid4()))
        def receipt(pin,text):
            return {"text":text,"canonical_url":"https://example.org/wiki","session_id":pin["session"],
                    "source_id":"a"*64,"span_sha256":hashlib.sha256(text.encode()).hexdigest(),
                    "valid_until":4e9,"history_only":True}
        first=receipt(a,"Title\nold damage\n")
        second=receipt(b,"Title\nnew damage\n")
        with patch.object(library,"read_document",AsyncMock(side_effect=[first,second,first,second])) as reader:
            result=await library.compare_documents(SCOPE,"d"*64,"e"*64,a,b)
        self.assertEqual(reader.await_count,4)
        self.assertTrue(result["partial_windows"])
        self.assertFalse(result["model_context_permission"])
        self.assertTrue(any(x["operation"]=="replace" and x["right"]=="new damage\n" for x in result["changes"]))

    async def test_different_canonical_urls_never_compared(self):
        a,b=self.pin(str(uuid4())),self.pin(str(uuid4()))
        first={"canonical_url":"https://example.org/one","session_id":a["session"],"source_id":"a"*64}
        second={"canonical_url":"https://example.org/two","session_id":b["session"],"source_id":"a"*64}
        with patch.object(library,"read_document",AsyncMock(side_effect=[first,second])):
            with self.assertRaises(ValueError):
                await library.compare_documents(SCOPE,"d"*64,"e"*64,a,b)
