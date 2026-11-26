"""Global source federation and classified discovery regression contracts."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.dragon_game_corpus import GameCorpus,CatalogueHeld,game_id
from core.dragon_game_taxonomy import SOURCE_CLASSES,FAMILIES
from core.dragon_source_directory import summary,page,enqueue,_load
from core.dragon_source_classification import classify_locator,EXTENSIONS,PATH_RULES
from core.dragon_release_discovery import parse_manifest,PROVIDERS
from core.dragon_release_queue import ReleaseQueue
from core.dragon_world_discovery import sitemap_pages,partition_feed
from core.dragon_ecosystem_profiles import public_profiles,manifest

SCOPE={"tenant_id":"tenant","owner_id":"owner"}
OTHER={"tenant_id":"tenant","owner_id":"other"}


class DirectoryCoverageTests(TestCase):
    def test_registry_coverage_and_stable_categories(self):
        overview=summary()
        self.assertGreaterEqual(len(SOURCE_CLASSES),1689)
        self.assertGreaterEqual(len(FAMILIES),52)
        self.assertGreaterEqual(overview["total_leads"],460)
        self.assertGreaterEqual(overview["distinct_origins"],397)
        self.assertGreaterEqual(len(overview["groups"]),22)
        self.assertFalse(overview["network_authorized"])
        groups={r["id"]:r for r in overview["groups"]}
        for name in ("warcraft","gta-v","gta-vi","fallout","mario","eve","global-catalogue","international",
                     "preservation","genre-specialists","sandbox-ugc","jrpg-action","western-rpg","competitive-fps",
                     "racing-sport-flight","puzzle-narrative","vr-accessibility","media-industry"):
            self.assertIn(name,groups)
        self.assertEqual(groups["fallout"]["scope"],"franchise")
        self.assertEqual(groups["mario"]["scope"],"franchise")
        self.assertEqual(groups["global-catalogue"]["scope"],"multi_game_directory")
        self.assertIsNone(groups["global-catalogue"]["preset_game_id"])
        self.assertEqual(groups["eve"]["preset_game_id"],game_id("developer","eve-online"))
        self.assertEqual(groups["gta-vi"]["preset_game_id"],game_id("publisher","gta-vi"))
        self.assertEqual(sum(x["leads"] for x in groups.values()),overview["total_leads"])
        for kind,spec in SOURCE_CLASSES.items():
            self.assertLessEqual(len(kind),32)
            self.assertLessEqual(len(spec.family),32)

    def test_full_keyset_listing_and_filter_fence(self):
        expected=summary()["total_leads"]
        ids=[];cursor=None
        while True:
            result=page(after=cursor,limit=17)
            self.assertFalse(result["network_authorized"])
            for lead in result["leads"]:
                ids.append(lead["lead_id"])
                self.assertIn(lead["provider"],PROVIDERS)
                self.assertEqual(lead["family"],SOURCE_CLASSES[lead["kind"]].family)
                self.assertFalse(lead["verified"])
            cursor=result["next_cursor"]
            if cursor is None:break
        self.assertEqual(len(ids),expected)
        self.assertEqual(ids,sorted(set(ids)))
        first=page(group="warcraft",limit=1)
        self.assertIsNotNone(first["next_cursor"])
        with self.assertRaises(ValueError):page(group="mario",after=first["next_cursor"])
        with self.assertRaises(ValueError):page(group="warcraft",q="addon",after=first["next_cursor"])
        self.assertTrue(page(group="warcraft",q="addon")["leads"])
        self.assertTrue(page(group="gta-v",q="scripting")["leads"])
        self.assertTrue(page(group="fallout",q="plugin")["leads"])
        self.assertTrue(page(group="mario",q="speedrun")["leads"])

    def test_profile_metadata_is_not_network_authority(self):
        profiles=public_profiles()
        self.assertGreaterEqual(len(profiles["profiles"]),6)
        for profile in profiles["profiles"]:
            self.assertFalse(profile["network_authority"])
            self.assertFalse(profile["measured"])
            proposals=parse_manifest(manifest(profile["id"]))
            self.assertGreaterEqual(len(proposals),5)
            self.assertEqual(len({(x.namespace,x.external_id) for x in proposals}),1)
        self.assertFalse(profiles["production_capacity_verified"])


class BindingTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name).resolve()/"corpus.sqlite3"
        self.corpus=GameCorpus(self.path)
        self.queue=ReleaseQueue(self.path)

    def seed(self,scope=SCOPE):
        return self.corpus.observe(scope,namespace="independent",external_id="a-game",title="A game",
            stage="unknown",source="https://example.org/game",kind="storefront",language="und",event_key="first",
            version=None,released_on=None)["game_id"]

    def ids(self,group):
        return [x["lead_id"] for x in page(group=group,limit=2)["leads"]]

    def test_preset_bind_durable_and_replay_exact_selection(self):
        ids=self.ids("warcraft")
        a=enqueue(self.path,SCOPE,operation="wow",group="warcraft",lead_ids=ids,use_preset=True,acknowledged=True)
        b=enqueue(self.path,SCOPE,operation="wow",group="warcraft",lead_ids=ids[::-1],use_preset=True,acknowledged=True)
        self.assertEqual(a["batch_id"],b["batch_id"])
        self.assertTrue(b["replayed"])
        self.assertFalse(b["capture_granted"])
        self.assertEqual(a["game_id"],game_id("publisher","world-of-warcraft"))
        with self.assertRaises(CatalogueHeld):
            enqueue(self.path,SCOPE,operation="wow",group="warcraft",lead_ids=ids[:1],use_preset=True,acknowledged=True)
        self.queue.pulse(limit=4)
        stored=self.corpus.sources(SCOPE,a["game_id"])["sources"]
        self.assertEqual(len(stored),2)
        self.assertFalse(any(x["verified"] for x in stored))

    def test_broad_directory_requires_existing_owner_identity(self):
        ids=self.ids("global-catalogue")
        with self.assertRaises(ValueError):
            enqueue(self.path,SCOPE,operation="no-game",group="global-catalogue",lead_ids=ids,use_preset=True,acknowledged=True)
        gid=self.seed()
        with self.assertRaises(LookupError):
            enqueue(self.path,OTHER,operation="foreign",group="global-catalogue",lead_ids=ids,game=gid,acknowledged=True)
        with self.assertRaises(ValueError):
            enqueue(self.path,SCOPE,operation="mixed",group="global-catalogue",lead_ids=ids[:1]+self.ids("warcraft")[:1],game=gid,acknowledged=True)
        with self.assertRaises(ValueError):
            enqueue(self.path,SCOPE,operation="unack",group="global-catalogue",lead_ids=ids,game=gid)
        accepted=enqueue(self.path,SCOPE,operation="bind",group="global-catalogue",lead_ids=ids,game=gid,acknowledged=True)
        self.assertEqual(accepted["game_id"],gid)
        self.queue.pulse(limit=4)
        self.assertEqual(len(self.corpus.sources(SCOPE,gid)["sources"]),3)
        self.assertEqual(self.corpus.sources(OTHER,gid)["sources"],[])


class ClassifiedSitemapTests(TestCase):
    def test_all_rules_use_real_taxonomy(self):
        for extension,kind in EXTENSIONS.items():
            self.assertIn(kind,SOURCE_CLASSES)
            self.assertEqual(classify_locator("https://example.org/file"+extension)["kind"],kind)
        for fragments,kind in PATH_RULES:
            self.assertIn(kind,SOURCE_CLASSES)
        cases={
            "https://example.org/ja/addons/plugin":"addon_directory",
            "https://example.org/vehicles/sedan":"vehicle_database",
            "https://example.org/raids/boss":"raid_reference",
            "https://example.org/mods/plugin":"mod_collection_catalogue",
            "https://example.org/courses/one":"platformer_level_database",
            "https://example.org/test%2Fmods":"reference_database",
            "https://example.org/my-mods-story":"reference_database",
        }
        for url,kind in cases.items():
            result=classify_locator(url)
            self.assertEqual(result["kind"],kind)
            self.assertFalse(result["verified"])
            self.assertFalse(result["network_authorized"])
        self.assertEqual(classify_locator("https://example.org/ja/addons/plugin")["language"],"ja")
        self.assertEqual(classify_locator("https://example.org/vehicles/sedan")["language"],"und")

    def test_classified_adapter_does_not_change_legacy_sitemap_identity(self):
        raw=b"<urlset><url><loc>https://example.org/ja/addons/one</loc></url><url><loc>https://example.org/vehicles/sedan</loc></url><url><loc>https://example.org/file.mp4</loc></url></urlset>"
        legacy=[x for part in sitemap_pages(raw,"independent","g","A game") for x in parse_manifest(part)]
        new=[x for part in sitemap_pages(raw,"independent","g","A game",classified=True) for x in parse_manifest(part)]
        self.assertEqual({x.kind for x in legacy},{"reference_database"})
        self.assertEqual({x.kind for x in new},{"addon_directory","vehicle_database","gameplay_video"})
        self.assertEqual({x.source for x in legacy},{x.source for x in new})
        adapter,pages,options=partition_feed({"adapter":"classified_sitemap","provider":"independent",
            "game_external_id":"g","title":"A game"},raw)
        self.assertEqual(adapter,"manifest")
        self.assertEqual(len(list(pages)),1)
        self.assertEqual(options,{})
