"""Focused qualification of the new worldwide, structured and media boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import zipfile

from core.dragon_game_corpus import GameCorpus,CatalogueHeld
from core.dragon_world_discovery import WorldDiscovery,sitemap_pages,steam_pages,eve_sde_manifest,fetch_public_feed,DiscoveryHeld
from core.dragon_release_discovery import parse_manifest,parse_steam_catalogue
from core.dragon_game_datasets import DatasetShard,parse_page,chain_step,ZERO
from core.dragon_dataset_ingest import plan,ingest
from core.dragon_game_routing import marker,binding_for
from core.dragon_hoarder_bulk import owner_key
from core.dragon_media_archive import byte_range,_signature
from core.dragon_ecosystem_profiles import public_profiles,manifest
from skeleton.ai.webcrawler.core import FetchResponse

SCOPE={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}


class WorldDiscoveryTests(TestCase):
    def test_exact_eve_build_pointer_and_no_injected_destination(self):
        data=b'{"_key":"sde","buildNumber":424242,"url":"https://bad.example.net/"}\n'
        items=parse_manifest(eve_sde_manifest(data))
        self.assertEqual(len(items),5)
        self.assertTrue(all(x.source.startswith("https://developers.eveonline.com/") for x in items))
        self.assertTrue(all(x.version=="424242" for x in items))
        self.assertTrue(any(x.source.endswith("eve-online-static-data-424242-jsonl.zip") for x in items))
        for bad in (b'{"_key":"sde","buildNumber":"../../x"}',b'{"_key":"sde","buildNumber":1}\n{"_key":"sde","buildNumber":2}'):
            with self.assertRaises(ValueError):eve_sde_manifest(bad)

    def test_sitemap_partition_and_sorted_identity(self):
        urls=["https://example.org/wiki/"+str(i) for i in range(1200)]
        raw=("<urlset>"+''.join("<url><loc>"+x+"</loc></url>" for x in reversed(urls))+"</urlset>").encode()
        result=[x for page in sitemap_pages(raw,"developer","game","Game") for x in parse_manifest(page)]
        self.assertEqual(len(result),len(urls))
        self.assertEqual({x.source for x in result},set(urls))
        with self.assertRaises(ValueError):
            list(sitemap_pages(b'<!DOCTYPE foo><urlset/>',"developer","game","Game"))

    def test_steam_partition(self):
        raw=json.dumps({"applist":{"apps":[{"appid":i,"name":"Game "+str(i)} for i in range(1,1202)]}}).encode()
        pages=list(steam_pages(raw))
        self.assertEqual(len(pages),3)
        self.assertEqual(sum(len(parse_steam_catalogue(x)) for x in pages),1201)

    def test_noarchive_and_robots_denial(self):
        class Fetcher:
            def __init__(self,deny=False):self.deny=deny;self.urls=[]
            def fetch_once(self,url,**kwargs):
                self.urls.append(url)
                if url.endswith("/robots.txt"):
                    body=b"User-agent: *\nDisallow: /feed" if self.deny else b"User-agent: *\nAllow: /"
                    return FetchResponse(url,200,{},body,1.0)
                return FetchResponse(url,200,{"x-robots-tag":"noarchive"},b"{}",1.0)
        for deny,count in ((True,1),(False,2)):
            fetcher=Fetcher(deny)
            with patch("core.dragon_world_discovery.time.sleep"),self.assertRaises(DiscoveryHeld):
                fetch_public_feed("https://example.org/feed",fetcher=fetcher)
            self.assertEqual(len(fetcher.urls),count)

    def test_source_profiles_are_hints_not_authority(self):
        p=public_profiles()
        self.assertFalse(p["production_capacity_verified"])
        self.assertGreaterEqual(p["architectural_limits"]["source_classes"],864)
        self.assertEqual(p["architectural_limits"]["sources_per_game"],20_000_000)
        self.assertGreaterEqual(len(parse_manifest(manifest("persistent-mmo"))),8)
        self.assertGreaterEqual(len(parse_manifest(manifest("large-open-world"))),3)

    def test_disabled_unattended_discovery_never_fetches(self):
        with TemporaryDirectory() as d:
            store=WorldDiscovery(Path(d)/"corpus.sqlite")
            with patch.dict("os.environ",{"SKL_DRAGON_WORLD_DISCOVERY":"0"}):
                self.assertEqual(store.pulse(),{"enabled":False,"network_executed":False})


class StructuredDatasetTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.corpus=GameCorpus(self.root/"catalogue.sqlite")
        x=self.corpus.observe(SCOPE,namespace="developer",external_id="eve",title="EVE",
            stage="updated",source="https://example.org/static.jsonl",kind="static_data_export",
            language="und",event_key="a",version="1",released_on=None)
        self.game=x["game_id"];self.source=x["source_id"];self.observation=x["observation_digest"]
        self.shard=DatasetShard(SCOPE,self.game,root=self.root,create=True)

    def begin(self,raw):
        n=len(parse_page(raw))
        chain=chain_step(ZERO,hashlib.sha256(raw).hexdigest(),0,n)
        return self.shard.begin(dataset="systems",source=self.source,observation_digest=self.observation,
            label="build-1",expected_rows=n,expected_chain=chain,grant_seconds=900,
            rights_acknowledged=True,corpus=self.corpus)

    def test_immutable_seal_fts_graph_replay_and_cleanup(self):
        raw=(b'{"_key":300001,"name":"Alpha","_relations":[{"kind":"connected","target":300002}]}\n'
             b'{"_key":300002,"name":"Beta"}\n')
        receipt=self.begin(raw);v=receipt["id"]
        with self.assertRaises(CatalogueHeld):self.shard.seal(v)
        first=self.shard.append(v,0,raw)
        self.assertFalse(first["replayed"])
        self.assertTrue(self.shard.append(v,0,raw)["replayed"])
        self.assertEqual(self.shard.seal(v)["state"],"sealed")
        self.assertEqual(self.shard.query(v,q="Alpha")["records"][0]["key"],"300001")
        self.assertEqual(self.shard.edges(v,"300002",reverse=True)["edges"][0]["record_key"],"300001")
        self.assertEqual(self.shard.revoke(v),{"revoked":True,"physical_erasure":False})
        with self.assertRaises(LookupError):self.shard.query(v)
        self.assertTrue(self.shard.collect(v)["complete"])

    def test_reject_private_fields_duplicate_ids_and_nonfinite(self):
        for raw in (b'{"_key":1,"access_token":"x"}',b'{"_key":1,"x":NaN}',
                    b'{"_key":1,"_key":2}',b'{"_key":1}\n{"_key":1}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):parse_page(raw)

    def test_two_pass_zip_ingestion(self):
        path=self.root/"sde.zip"
        raw=b'{"_key":1,"name":"Alpha"}\r\n{"_key":2,"name":"Beta"}\n'
        with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("data/mapSystems.jsonl",raw)
        info=plan(path,"data/mapSystems.jsonl")
        self.assertEqual(info["expected_rows"],2)
        out=ingest(self.shard,path,member="data/mapSystems.jsonl",dataset="system_export",
            source=self.source,observation_digest=self.observation,label="build-1",
            rights_acknowledged=True,corpus=self.corpus)
        self.assertEqual(out["rows"],2)
        self.assertEqual(out["state"],"sealed")
        self.assertFalse(out["physical_capacity_verified"])
        with self.assertRaises(ValueError):plan(path,"../mapSystems.jsonl")

    def test_game_routing_basis_and_seed_mismatch(self):
        from uuid import uuid4
        session=str(uuid4())
        self.corpus.bind_capture(SCOPE,game=self.game,source=self.source,
            observation_digest=self.observation,session=session)
        bind=binding_for(self.corpus.path,SCOPE,session)
        row={"_id":session,"status":"completed","request":{"seed_urls":["https://example.org/static.jsonl"]}}
        self.assertEqual(marker(SCOPE,row,bind)["game_id"],self.game)
        self.assertIsNone(binding_for(self.corpus.path,OTHER,session))
        with self.assertRaises(ValueError):marker(OTHER,row,bind)
        with self.assertRaises(ValueError):marker(SCOPE,{**row,"request":{"seed_urls":["https://example.org/other"]}},bind)


class BinaryMediaBoundaryTests(TestCase):
    def test_byte_range_and_signature(self):
        self.assertEqual(byte_range("bytes=10-20",100),(10,20,True))
        self.assertEqual(byte_range("bytes=-5",100),(95,99,True))
        self.assertEqual(byte_range(None,100),(0,99,False))
        for v in ("bytes=0-9,20-30","bytes=100-200","bytes=9-2","bytes=-0"):
            with self.assertRaises(ValueError):byte_range(v,100)
        self.assertTrue(_signature("video/mp4",b"\x00\x00\x00\x18ftypisom"))
        self.assertFalse(_signature("video/mp4",b"<html>unsafe</html>"))


class TenfoldDatasetShardTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()

    def next_game(self):
        from core.dragon_game_datasets import game_shard_candidates
        owner=owner_key(SCOPE)
        for number in range(1,1000):
            candidate=format(number,"064x")
            bucket,lane=game_shard_candidates(owner,candidate)
            if lane:
                return candidate,bucket,lane
        self.fail("no nonzero lane fixture")

    def test_shard_cardinality_and_legacy_names(self):
        from core.dragon_game_datasets import SHARDS,shard_path
        self.assertEqual(SHARDS,2560)
        self.assertEqual(len({shard_path(self.root,i) for i in range(SHARDS)}),SHARDS)
        self.assertEqual(shard_path(self.root,255).name,"game-data-ff.sqlite3")
        self.assertEqual(shard_path(self.root,256).name,"game-data-00-lane-1.sqlite3")
        self.assertEqual(shard_path(self.root,2559).name,"game-data-ff-lane-9.sqlite3")

    def test_new_game_assignment_restart_and_missing_shard_hold(self):
        from core.dragon_game_datasets import shard_path
        game,bucket,lane=self.next_game()
        first=DatasetShard(SCOPE,game,root=self.root,create=True)
        expected=shard_path(self.root,bucket+256*lane)
        self.assertEqual(first.path,expected)
        self.assertEqual(DatasetShard(SCOPE,game,root=self.root).path,expected)
        self.assertEqual(DatasetShard(SCOPE,game,root=self.root,create=True).path,expected)
        expected.unlink()
        with self.assertRaises(LookupError):
            DatasetShard(SCOPE,game,root=self.root,create=True)
        self.assertFalse(expected.exists())

    def test_existing_tombstone_pins_game_to_legacy(self):
        import sqlite3
        from core.dragon_game_datasets import SCHEMA,shard_path
        game,bucket,lane=self.next_game()
        legacy=shard_path(self.root,bucket)
        legacy.touch(mode=0o600)
        db=sqlite3.connect(legacy)
        try:
            db.executescript(SCHEMA)
            db.execute("""INSERT INTO dataset_versions(owner,game,id,dataset,source,observation_digest,
                label,expected_rows,expected_chain,chain,created_at,expires_at,state)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'erased')""",
                (owner_key(SCOPE),game,"a"*64,"fixture","b"*64,"c"*64,"legacy",1,"d"*64,ZERO,0,0))
            db.commit()
        finally:db.close()
        self.assertEqual(DatasetShard(SCOPE,game,root=self.root,create=True).path,legacy)
        self.assertEqual(DatasetShard(SCOPE,game,root=self.root).path,legacy)
        self.assertFalse(shard_path(self.root,bucket+256*lane).exists())

    def test_missing_legacy_directory_cannot_reassign_existing_game(self):
        from core.dragon_game_datasets import shard_path
        game,bucket,lane=self.next_game()
        first=DatasetShard(SCOPE,game,root=self.root,create=True)
        shard_path(self.root,bucket).unlink()
        with self.assertRaises(CatalogueHeld):
            DatasetShard(SCOPE,game,root=self.root,create=True)
        self.assertTrue(first.path.exists())

    def test_maintenance_advances_all_ten_slots(self):
        import os
        from core.dragon_game_datasets import sweep_dataset_shard
        corpus=self.root/"corpus.sqlite"
        with patch.dict(os.environ,{"SKL_DRAGON_DATASET_ROOT":str(self.root)}):
            result=sweep_dataset_shard(corpus)
        self.assertEqual(result["shards_visited"],10)
        self.assertEqual(result["shards_held"],0)
        with GameCorpus(corpus)._db() as db:
            self.assertEqual(db.execute("SELECT cursor FROM dataset_maintenance").fetchone()[0],10)


class TenfoldVolumeConfigurationTests(TestCase):
    def test_file_configuration_avoids_environment_limit(self):
        import os
        from core.dragon_hoarder_bulk import MAX_VOLUMES,StorageHeld
        from core.dragon_storage_topology import topology_config
        self.assertEqual(MAX_VOLUMES,2560)
        var="SKL_DRAGON_HOARDER_VOLUMES_JSON"
        with TemporaryDirectory() as d:
            path=Path(d).resolve()/"volumes.json"
            raw=json.dumps([{"name":"v"+str(i),"root":"/private/example/"+str(i),"payload_budget":1073741824}
                            for i in range(MAX_VOLUMES)])
            path.write_text(raw,encoding="utf-8")
            path.chmod(0o600)
            with patch.dict(os.environ,{var:"",var+"_FILE":str(path)}):
                self.assertEqual(topology_config(var),raw)
            with patch.dict(os.environ,{var:"[]",var+"_FILE":str(path)}):
                with self.assertRaises(StorageHeld):topology_config(var)
            if os.name=="posix":
                path.chmod(0o644)
                with patch.dict(os.environ,{var:"",var+"_FILE":str(path)}):
                    with self.assertRaises(StorageHeld):topology_config(var)
