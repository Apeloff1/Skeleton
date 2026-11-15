"""Regression contracts for the large generated seed catalogue.

No network requests occur in these tests. The checked counts are construction
and deduplication evidence, not source availability, authorization or capacity.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.dragon_game_corpus import GameCorpus,CatalogueHeld,game_id
from core.dragon_game_taxonomy import SOURCE_CLASSES,FAMILIES
from core.dragon_mod_seed_catalogue import (
    _load,_canonical_locator,summary,page,applications,import_applications,attach_specialists,
)
from core.dragon_release_queue import ReleaseQueue

SCOPE={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}


class ModSeedRegistryTests(TestCase):
    def test_full_census_and_route_identity(self):
        stats=summary()
        self.assertGreaterEqual(stats["total_unique_locators"],4600)
        self.assertEqual(stats["total_unique_locators"],stats["legacy_unique_locators"]+stats["expanded_records"]-stats["overlap_with_legacy"])
        self.assertEqual(sum(stats["lanes"].values()),stats["expanded_records"])
        self.assertEqual(sum(stats["providers"].values()),stats["expanded_records"])
        self.assertGreaterEqual(stats["candidate_apps"],600)
        self.assertGreaterEqual(stats["candidate_repositories"],380)
        self.assertGreaterEqual(stats["mod_related_records"],6900)
        self.assertFalse(stats["network_authorized"])
        self.assertFalse(stats["source_verified"])
        self.assertFalse(stats["physical_capacity_verified"])
        self.assertGreaterEqual(len(SOURCE_CLASSES),1958)
        self.assertGreaterEqual(len(FAMILIES),60)
        _,rows,apps,by_app,_,_=_load()
        self.assertEqual(len({_canonical_locator(r["url"]) for r in rows.values()}),len(rows))
        for row in rows.values():
            self.assertIn(row["kind"],SOURCE_CLASSES)
            self.assertEqual(row["family"],SOURCE_CLASSES[row["kind"]].family)
            self.assertFalse(row["verified"])
            self.assertFalse(row["network_authorized"])
            if row["appid"] is not None:
                self.assertIn(row["appid"],apps)
                self.assertEqual(row["candidate_game_id"],game_id("steam",row["appid"]))
            else:
                self.assertIsNone(row["candidate_game_id"])
        for appid,ids in by_app.items():
            self.assertEqual(apps[appid]["seeds"],len(ids))
            self.assertEqual(apps[appid]["mod_related_seeds"],sum(rows[x]["mod_related"] for x in ids))

    def test_paging_and_exact_filters(self):
        seen=[];cursor=None
        while True:
            result=page(lane="mod_platforms",provider="nexusmods",mod_only=True,after=cursor,limit=47)
            self.assertTrue(all(x["provider"]=="nexusmods" and x["mod_related"] for x in result["seeds"]))
            seen.extend(x["seed_id"] for x in result["seeds"])
            cursor=result["next_cursor"]
            if cursor is None:break
        self.assertEqual(seen,sorted(set(seen)))
        self.assertEqual(len(seen),summary()["providers"]["nexusmods"])
        first=page(lane="tool_repositories",limit=1)
        with self.assertRaises(ValueError):
            page(lane="game_surfaces",after=first["next_cursor"])
        with self.assertRaises(ValueError):
            page(lane="tool_repositories",q="skyrim",after=first["next_cursor"])
        self.assertTrue(page(q="Fallout",mod_only=True)["seeds"])
        self.assertTrue(page(q="BepInEx",lane="tool_repositories")["seeds"])
        self.assertTrue(page(q="FiveM",lane="tool_repositories")["seeds"])
        self.assertTrue(page(appid="294100",mod_only=True)["seeds"])
        matches=applications(q="Skyrim")["applications"]
        self.assertTrue(any(a["appid"]=="489830" for a in matches))
        self.assertTrue(all(a["verified"] is False for a in matches))

    def test_app_specific_nexus_alias_not_silently_merged(self):
        _,rows,_,_,_,_=_load()
        urls=[r for r in rows.values() if "/skyrimspecialedition" in r["url"] and r["provider"]=="nexusmods"]
        self.assertEqual(len(urls),3)
        self.assertTrue(all(r["appid"] is None and r["candidate_game_id"] is None for r in urls))


class ModSeedImportTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name).resolve()/"corpus.sqlite3"
        self.corpus=GameCorpus(self.path)
        self.queue=ReleaseQueue(self.path)
        self.revision=summary()["revision"]

    def seed(self,external="one",scope=SCOPE):
        result=self.corpus.observe(scope,namespace="independent",external_id=external,title="Owned game",
            stage="unknown",source="https://example.org/game",kind="storefront",language="und",
            event_key="first",version=None,released_on=None)
        return result["game_id"]

    def test_atomic_import_multiple_real_candidate_ids(self):
        ids=["294100","108600"]
        a=import_applications(self.path,SCOPE,revision=self.revision,operation="bulk",
            appids=ids,mod_only=True,acknowledged=True)
        b=import_applications(self.path,SCOPE,revision=self.revision,operation="bulk",
            appids=ids[::-1],mod_only=True,acknowledged=True)
        self.assertEqual(a["batch_id"],b["batch_id"])
        self.assertTrue(b["replayed"])
        self.assertEqual(a["selected"],a["total"])
        self.assertFalse(a["capture_granted"])
        self.assertEqual({r["game_id"] for r in a["applications"]},{game_id("steam",x) for x in ids})
        with self.assertRaises(CatalogueHeld):
            import_applications(self.path,SCOPE,revision=self.revision,operation="bulk",
                appids=ids,mod_only=False,acknowledged=True)
        for _ in range(8):
            self.queue.pulse(limit=16)
        for appid in ids:
            stored=self.corpus.sources(SCOPE,game_id("steam",appid))["sources"]
            self.assertTrue(stored)
            self.assertTrue(any(r["kind"]=="community_workshop" for r in stored))
            self.assertTrue(all(r["verified"] is False for r in stored))
            self.assertFalse(self.corpus.sources(OTHER,game_id("steam",appid))["sources"])

    def test_specialist_binding_rejects_wrong_owner_or_app(self):
        owned=self.seed()
        neutral=page(lane="tool_repositories",limit=1)["seeds"][0]
        specific=page(appid="294100",limit=1)["seeds"][0]
        with self.assertRaises(LookupError):
            attach_specialists(self.path,OTHER,revision=self.revision,operation="foreign",
                game=owned,seed_ids=[neutral["seed_id"]],acknowledged=True)
        with self.assertRaises(ValueError):
            attach_specialists(self.path,SCOPE,revision=self.revision,operation="wrong-app",
                game=owned,seed_ids=[specific["seed_id"]],acknowledged=True)
        with self.assertRaises(ValueError):
            attach_specialists(self.path,SCOPE,revision="0"*64,operation="stale",
                game=owned,seed_ids=[neutral["seed_id"]],acknowledged=True)
        receipt=attach_specialists(self.path,SCOPE,revision=self.revision,operation="bound",
            game=owned,seed_ids=[neutral["seed_id"]],acknowledged=True)
        self.assertEqual(receipt["game_id"],owned)
        self.assertFalse(receipt["source_verified"])
        self.queue.pulse(limit=8)
        self.assertEqual(len(self.corpus.sources(SCOPE,owned)["sources"]),2)

    def test_no_implicit_binding_or_duplicate_selection(self):
        for args in (
            {"appids":["294100"],"acknowledged":False},
            {"appids":["294100","294100"],"acknowledged":True},
            {"appids":["999999999999"],"acknowledged":True},
        ):
            with self.assertRaises(ValueError):
                import_applications(self.path,SCOPE,revision=self.revision,operation="bad",**args)
