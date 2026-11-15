"""Focused acceptance for discovery, custody and retrieval boundaries."""
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import hashlib
import json
import os
import sqlite3

from core.dragon_game_corpus import CatalogueHeld,GameCorpus
from core.dragon_hoarder_bulk import BulkArchive,Volume,GIB,StorageHeld
from core.dragon_hoarder_manifests import ManifestArchive,BLOCK
from core.dragon_hybrid_rank import Candidate,rank,fuse_ranked,fingerprint,select_passage
from core.dragon_release_discovery import parse_manifest,parse_release_feed,parse_steam_catalogue
from core.dragon_release_queue import ReleaseQueue

SCOPE={"tenant_id":"t","owner_id":"o"}
OTHER={"tenant_id":"t","owner_id":"different"}


def feed(title="Example RPG",stage="announced"):
    return json.dumps({"schema":"dragon.game-feed.v1","provider":"independent","entries":[{
        "id":"example-123","title":title,"stage":stage,"links":[
        {"url":"https://example.org/wiki","kind":"official_wiki","language":"en"},
        {"url":"https://community.example.org/guide","kind":"community_wiki","language":"en"}]}]}).encode()


class DiscoveryTests(TestCase):
    def test_multisource_and_release_revision(self):
        first=parse_manifest(feed())
        second=parse_manifest(feed(stage="released"))
        self.assertEqual(len(first),2)
        self.assertNotEqual(first[0].event_key,second[0].event_key)
        self.assertEqual(first[0].external_id,second[0].external_id)
        self.assertEqual(first[0].source,second[0].source)
        self.assertEqual(first[0].stage,"announced")

    def test_invalid_manifest_never_produces_partial_results(self):
        data=json.loads(feed())
        data["entries"][0]["links"].append({"url":"https://example.org/?token=private"})
        with self.assertRaises(ValueError):
            parse_manifest(json.dumps(data).encode())
        with self.assertRaises(ValueError):
            parse_manifest(b'{"schema":"x","schema":"y"}')
        with self.assertRaises(ValueError):
            parse_steam_catalogue(b'{"applist":{"apps":[{"appid":true,"name":"bad"}]}}')

    def test_steam_deterministic_app_identity(self):
        proposals=parse_steam_catalogue(b'{"applist":{"apps":[{"appid":12,"name":"Example"}]}}')
        item=proposals[0]
        self.assertEqual(item.external_id,"12")
        self.assertEqual(item.source,"https://store.steampowered.com/app/12/")
        self.assertEqual(item.stage,"unknown")

    def test_rss_shared_article_keeps_distinct_event_witnesses(self):
        raw=b'<rss><channel><item><guid>patch1</guid><link>https://example.org/updates</link></item><item><guid>patch2</guid><link>https://example.org/updates</link></item></channel></rss>'
        props=parse_release_feed(raw,provider="independent",external_id="demo",title="Example")
        self.assertEqual(len(props),2)
        self.assertNotEqual(props[0].event_key,props[1].event_key)
        self.assertEqual(props[0].stage,"unknown")

    def test_xml_dtd_and_entity_rejection(self):
        with self.assertRaises(ValueError):
            parse_release_feed(b'<!DOCTYPE rss [<!ENTITY x "test">]><rss/>',
                                   provider="independent",external_id="demo",title="Example")


class QueueTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"catalogue.sqlite"
        self.queue=ReleaseQueue(self.path)

    def enqueue(self,value=None,operation="import-1"):
        return self.queue.enqueue(SCOPE,raw=value or feed(),adapter="manifest",operation=operation)

    def test_import_replay_owner_isolation_and_actual_index(self):
        batch=self.enqueue()
        self.assertTrue(self.enqueue()["replayed"])
        with self.assertRaises(CatalogueHeld):
            self.enqueue(feed(stage="released"))
        self.assertEqual(self.queue.status(SCOPE,batch["batch_id"])["counts"]["queued"],2)
        with self.assertRaises(LookupError):
            self.queue.status(OTHER,batch["batch_id"])
        self.assertEqual(self.queue.pulse()["done"],2)
        self.assertEqual(self.queue.pulse()["done"],0)
        corpus=GameCorpus(self.path)
        matches=corpus.search(SCOPE,"example RPG")["games"]
        self.assertEqual(len(matches),1)
        sources=corpus.sources(SCOPE,matches[0]["game_id"])["sources"]
        self.assertEqual(len(sources),2)
        plan=corpus.capture_plan(SCOPE,matches[0]["game_id"],sources[0]["source_id"],sources[0]["observation_digest"])
        self.assertFalse(plan["crawl_authorized"])
        self.assertEqual(corpus.search(OTHER,"example")["games"],[])

    def test_commit_before_ack_crash_replays_exact_release_event(self):
        batch=self.enqueue()
        row=self.queue._claim()
        self.queue.corpus.observe(json.loads(row["scope_json"]),**json.loads(row["payload"]))
        with patch("core.dragon_release_queue.time.time",return_value=4_000_000_000):
            self.assertEqual(self.queue.pulse()["done"],2)
            self.assertEqual(self.queue._settle(row),"superseded")
        self.assertEqual(self.queue.status(SCOPE,batch["batch_id"])["counts"]["done"],2)
        game=GameCorpus(self.path).search(SCOPE,"Example")["games"][0]["game_id"]
        self.assertEqual(len(GameCorpus(self.path).history(SCOPE,game)["observations"]),2)

    def test_old_catalogue_observation_cannot_launch_latest_source_plan(self):
        self.enqueue()
        self.queue.pulse()
        corpus=GameCorpus(self.path)
        gid=corpus.search(SCOPE,"Example")["games"][0]["game_id"]
        old=corpus.sources(SCOPE,gid)["sources"][0]
        self.enqueue(feed(stage="released"),operation="import-2")
        self.queue.pulse()
        with self.assertRaises(CatalogueHeld):
            corpus.capture_plan(SCOPE,gid,old["source_id"],old["observation_digest"])


class RankingTests(TestCase):
    def test_phrase_and_title_prioritize_exact_relevant_source(self):
        result=rank("dragon fire damage",[
            Candidate("a","Unrelated","dragon statue and forest"),
            Candidate("b","Dragon fire damage","Exact dragon fire damage mechanics and resistance"),
            Candidate("c","Cooking","bread and spices")])
        self.assertEqual(result[0]["key"],"b")
        self.assertTrue(result[0]["phrase"])
        self.assertNotIn("c",[x["key"] for x in result])

    def test_rank_fusion_and_unicode_original_span(self):
        self.assertEqual(fuse_ranked([["b","a"],["a","c"]],limit=2),["a","b"])
        text="x"*200+" blå drage fire damage "+"z"*200
        start,end=select_passage("blå drage",text,100)
        self.assertIn("blå drage",text[start:end])
        self.assertEqual(fingerprint(text),fingerprint(text))
        self.assertNotEqual(fingerprint(text)["sha256"],fingerprint(text+"!")["sha256"])

    def test_bounds_and_deterministic_ties(self):
        candidates=[Candidate("b","Same","same"),Candidate("a","Same","same")]
        self.assertEqual([x["key"] for x in rank("same",candidates)],["a","b"])
        with self.assertRaises(ValueError): rank("",candidates)
        with self.assertRaises(ValueError): rank("same",candidates*40)


class ManifestTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.root.chmod(0o700)
        self.volume=self.root/"volume"
        self.volume.mkdir(mode=0o700)
        self.bulk=BulkArchive((Volume("primary",self.volume,2*GIB),))
        self.manifests=ManifestArchive(self.root/"manifests.sqlite",self.bulk)
        self.disk=patch("core.dragon_hoarder_bulk.shutil.disk_usage",return_value=type("Disk",(),{"free":10*GIB})())
        self.disk.start()
        self.addCleanup(self.disk.stop)

    def begin(self,data,operation="1",logical_key="game/wiki"):
        return self.manifests.begin(SCOPE,logical_key=logical_key,operation=operation,
                    expected_hash=hashlib.sha256(data).hexdigest(),expected_bytes=len(data))["manifest"]

    def test_chunked_reconstruction_and_shared_ref_gc(self):
        first=b"a"*BLOCK
        last=b"patch"
        data=first+last
        a=self.begin(data,"a")
        b=self.begin(first+b"newer","b")
        for mid,tail in ((a,last),(b,b"newer")):
            with self.assertRaises(StorageHeld): self.manifests.seal(SCOPE,mid)
            self.manifests.append(SCOPE,mid,1,tail)
            self.manifests.append(SCOPE,mid,0,first)
            self.manifests.seal(SCOPE,mid)
        self.assertEqual(self.manifests.read_chunk(SCOPE,a,0)+self.manifests.read_chunk(SCOPE,a,1),data)
        self.assertEqual(self.manifests.usage(SCOPE)["unique_chunks"],3)
        self.manifests.abort(SCOPE,a)
        self.assertEqual(self.manifests.collect(SCOPE)["collected"],1)
        self.assertEqual(self.manifests.read_chunk(SCOPE,b,0),first)
        with self.assertRaises(StorageHeld): self.manifests.read_chunk(OTHER,b,0)
        self.manifests.abort(SCOPE,b)
        self.assertEqual(self.manifests.collect(SCOPE)["collected"],2)

    def test_uncertain_cross_store_publication_can_be_reverified(self):
        data=b"historical wiki page"
        a=self.begin(data)
        self.manifests.append(SCOPE,a,0,data)
        # Payload committed, but the acknowledgement was not durable.
        with sqlite3.connect(self.root/"manifests.sqlite") as db:
            db.execute("UPDATE chunks SET compressed_bytes=NULL")
        self.assertTrue(self.manifests.seal(SCOPE,a)["sealed"])
        restored=ManifestArchive(self.root/"manifests.sqlite",BulkArchive((Volume("primary",self.volume,2*GIB),)))
        self.assertEqual(restored.read_chunk(SCOPE,a,0),data)

    def test_wrong_whole_digest_cannot_seal(self):
        a=self.begin(b"alpha")
        self.manifests.append(SCOPE,a,0,b"omega")
        with self.assertRaises(StorageHeld): self.manifests.seal(SCOPE,a)
        with self.assertRaises(StorageHeld): self.manifests.read_chunk(SCOPE,a,0)
        with self.assertRaises(StorageHeld): self.manifests.append(SCOPE,a,0,b"alpha")
