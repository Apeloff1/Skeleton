"""Actual packaged source registry and owner-fenced discovery navigation."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.dragon_navigation_federation import NavigationFederation
from skeleton.ai.webcrawler.navigation_backlog import observe
from skeleton.ai.webcrawler.operations import CrawlRun,CrawlRequest
from skeleton.ai.webcrawler.source_navigation import catalogue,Catalogue,REGISTRY_PATH,objective,rank_sources,frontier_signal
from test_dragon_navigation_federation import SCOPE,OTHER,NOW


class CatalogueTests(unittest.TestCase):
    def test_full_catalogue_and_source_identity(self):
        reg=catalogue();summary=reg.summary()
        self.assertGreaterEqual(summary["sources"],3820)
        self.assertGreaterEqual(summary["hosts"],357)
        self.assertEqual(len(summary["families"]),10)
        self.assertEqual(len(reg.by_id),summary["sources"])
        self.assertFalse(summary["network_authorized"])
        for s in reg.rows:
            self.assertFalse(s.public()["rights_verified"])
            self.assertEqual(reg.match(s.url),s)

    def test_repository_density_does_not_erase_other_publishers(self):
        result=rank_sources("world of warcraft mods tools documentation",limit=64)
        hosts={r["host"] for r in result["sources"]}
        self.assertGreater(len(hosts),1)
        self.assertTrue(all(not r["network_authorized"] for r in result["sources"]))

    def test_specific_ecosystem_sources_and_authority(self):
        for query,ecosystem,expected in (
            ("EVE Online static data export ESI schema","eve","developers.eveonline.com"),
            ("World of Warcraft raid combat logs addons","warcraft","www.warcraftlogs.com"),
            ("Minecraft modding plugins","minecraft","modrinth.com"),
            ("Grand Theft Auto GTA modding FiveM","grand-theft-auto","docs.fivem.net"),
            ("Super Mario Nintendo historical games","nintendo","www.mariowiki.com"),
        ):
            with self.subTest(query=query):
                result=rank_sources(query,limit=24)
                self.assertIn(ecosystem,result["ecosystems"])
                self.assertIn(expected,{s["host"] for s in result["sources"]})
                self.assertTrue(all(s["network_authorized"] is False for s in result["sources"]))
                prior=[s["source_id"] for s in result["sources"]]
                self.assertFalse(set(prior)&{s["source_id"] for s in rank_sources(query,previous=prior)["sources"]})

    def test_root_path_boundaries_no_suffix_or_credential_confusion(self):
        reg=catalogue()
        root=reg.match("https://steamcommunity.com/workshop/")
        self.assertEqual(root.name,"Steam Workshop")
        self.assertNotEqual(reg.match("https://steamcommunity.com/workshop-other").id,root.id)
        self.assertIsNone(reg.match("https://steamcommunity.com.evil.example/workshop/"))
        self.assertIsNone(reg.match("https://user@steamcommunity.com/workshop/"))
        self.assertIsNone(reg.match("http://steamcommunity.com/workshop/"))
        self.assertIsNone(reg.match("https://steamcommunity.com:8443/workshop/"))
        task=objective("Steam mods workshop")
        self.assertIsNotNone(frontier_signal(root.url,task))
        self.assertIsNone(frontier_signal("https://unlisted.example/index",task))

    def test_malformed_catalogue_fails_closed(self):
        data=json.loads(REGISTRY_PATH.read_bytes())
        data["sources"].append(data["sources"][0])
        with self.assertRaises(ValueError):Catalogue(json.dumps(data).encode())
        data["sources"].pop()
        data["sources"][0]["url"]="https://example.com/private?token=foo"
        with self.assertRaises(ValueError):Catalogue(json.dumps(data).encode())


class SourceAtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.repo=NavigationFederation(Path(self.tmp.name)/"catalogue.sqlite3")

    def publish(self,index,host):
        root="https://example.com/flight/manual"
        child="https://"+host+"/flight/navigation"
        request=CrawlRequest(seed_urls=(root,),allowed_hosts=("example.com",host),
            query="flight manual",max_depth=2,frontier_strategy="companion")
        run=CrawlRun.create(request,scope=SCOPE,consent={"consent_id":"atlas-"+str(index),
            "capture_acknowledged":True,"source_rights_acknowledged":True,"expires_at":NOW+3600},now=NOW)
        observe(run._state["discovery_backlog"],url=child,parent=root,depth=1,kind="document_link")
        run._state["state"]="budget_exhausted";run._state["stop_reason"]="cumulative_budget"
        return self.repo.publish(SCOPE,session_id="atlas-"+str(index),snapshot=run.snapshot(),
            rights_reference="fixture authorized public locator metadata",retention_seconds=7200,
            acknowledged=True,now=NOW)

    def test_incremental_hosts_cross_host_provenance_and_revocation(self):
        first=self.publish(1,"aircraft.example")
        before=self.repo.source_atlas(SCOPE,action="inventory",now=NOW)
        self.assertEqual({h["host"] for h in before["hosts"]},{"example.com","aircraft.example"})
        second=self.publish(2,"aviation.example")
        inventory=self.repo.source_atlas(SCOPE,action="inventory",now=NOW)
        self.assertEqual({h["host"] for h in inventory["hosts"]},{"example.com","aircraft.example","aviation.example"})
        trace=self.repo.source_atlas(SCOPE,action="trace",host="example.com",now=NOW)
        self.assertEqual({x["host"] for x in trace["targets"]},{"aircraft.example","aviation.example"})
        self.assertTrue(all(x["parent_ids"] and not x["network_authorized"] for x in trace["targets"]))
        self.assertEqual(self.repo.source_atlas(OTHER,action="inventory",now=NOW)["hosts"],[])
        self.repo.revoke(SCOPE,first["grant_id"])
        trace=self.repo.source_atlas(SCOPE,action="trace",host="example.com",now=NOW)
        self.assertEqual({x["host"] for x in trace["targets"]},{"aviation.example"})
        self.repo.revoke(SCOPE,second["grant_id"])
        self.assertEqual(self.repo.source_atlas(SCOPE,action="inventory",now=NOW)["hosts"],[])

    def test_source_plan_retains_graph_and_registry_boundary(self):
        grant=self.publish(1,"aircraft.example")
        result=self.repo.source_atlas(SCOPE,action="plan",query="flight manual",limit=48,now=NOW)
        self.assertTrue(any(x["origin"]=="registry" for x in result["sources"]))
        observed=[x for x in result["sources"] if x["origin"]=="retained_graph"]
        self.assertTrue(observed)
        self.assertTrue(all(x["permission_required"] and not x["network_authorized"] for x in result["sources"]))
        prior=[x["candidate_id"] for x in result["sources"]]
        fresh=self.repo.source_atlas(SCOPE,action="plan",query="flight manual",previous=prior,limit=48,now=NOW)
        self.assertFalse(set(prior)&{x["candidate_id"] for x in fresh["sources"]})
        self.repo.revoke(SCOPE,grant["grant_id"])
        result=self.repo.source_atlas(SCOPE,action="plan",query="flight manual",limit=48,now=NOW)
        self.assertFalse(any(x["origin"]=="retained_graph" for x in result["sources"]))


if __name__=="__main__":unittest.main()
