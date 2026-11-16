"""Hermetic official API, direct raw body, backup and real scratch qualification."""
from __future__ import annotations
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock,Mock,patch

from core import dragon_authorized_api as api
from core import dragon_backup_discovery as discovery
from core import dragon_ingestion_qualification as qualification
from core.dragon_graph_deployment import DeploymentHeld,_json
from core.dragon_mongo_receipt import _new_json
from core.dragon_raw_export_custody import RawExportCustody
from skeleton.ai.webcrawler.bound_http import SocketBoundFetcher
from skeleton.ai.webcrawler.core import FetchResponse

SCOPE={"tenant_id":"fixture","owner_id":"operator"}
# No real credentials or server connections are used.
DUMMY="fixture"+"a"*24


class OfficialProfileTests(unittest.TestCase):
    def test_fixed_endpoints_and_no_arbitrary_path(self):
        fetcher=SocketBoundFetcher()
        cases=(("github_releases","https://api.github.com/repos/example/project/releases"),
               ("github_tags","https://api.github.com/repos/example/project/tags"),
               ("huggingface_dataset","https://huggingface.co/api/datasets/example/project"))
        with patch.object(SocketBoundFetcher,"_fetch_once",return_value=Mock()) as fetch:
            for provider,url in cases:
                fetcher.fetch_publisher_api_once(provider,"example/project",token=DUMMY,
                            user_agent=api.USER_AGENT,max_bytes=1024)
                self.assertEqual(fetch.call_args.args[0],url)
                identity,headers=fetch.call_args.kwargs["publisher_identity"]
                self.assertEqual(identity,url)
                self.assertEqual(headers["Authorization"],"Bearer "+DUMMY)
            for resource in ("example/project?x=1","example/../project","https://elsewhere.invalid/x","example/project#x"):
                with self.assertRaises(ValueError):
                    fetcher.fetch_publisher_api_once("github_releases",resource,token=DUMMY,
                            user_agent=api.USER_AGENT,max_bytes=1024)
            self.assertEqual(fetch.call_count,3)

    def test_grant_requires_finite_independent_rights(self):
        grant={"schema":api.SCHEMA,"scope":SCOPE,"principal_email":"fixture@example.invalid",
               "provider":"github_tags","resource":"example/project","expires_at":300,
               "operation":"fixture","token_file":"/private/token.json","raw_store":None,
               "retain_seconds":0,"publisher_permission_acknowledged":True,
               "independent_resource_acknowledged":True,"retention_rights_acknowledged":False,
               "egress_approved":True}
        self.assertEqual(api.validate_grant(grant,now=100),grant)
        for change in ({"expires_at":110},{"provider":"other"},{"egress_approved":False},
                       {"independent_resource_acknowledged":False},{"retain_seconds":300}):
            with self.assertRaises(ValueError):api.validate_grant({**grant,**change},now=100)

    def test_retention_denies_private_or_uncertain_http_policy(self):
        headers={"content-type":"application/json","cache-control":"public, max-age=60"}
        def response(h,body=b'{"name":"fixture"}',status=200):
            return FetchResponse("https://api.github.com/repos/example/project/tags",
                                 status,h,body,100.0)
        with patch.object(api,"source_capture_rights",return_value=Mock(retain=True)),patch.object(
                api,"inspect_response",return_value=None):
            self.assertTrue(api._raw_candidate(response(headers),DUMMY))
            for changed in ({"cache-control":"private, public"},{"cache-control":"public, no-store"},
                            {"vary":"Authorization"},{"set-cookie":"fixture"},{"cache-control":"max-age=60"}):
                self.assertFalse(api._raw_candidate(response({**headers,**changed}),DUMMY))
            self.assertFalse(api._raw_candidate(response(headers,b'{"token":"fixture"}'),DUMMY))
            self.assertFalse(api._raw_candidate(response(headers,b'{"name":1,"name":2}'),DUMMY))
            self.assertFalse(api._raw_candidate(response(headers,status=403),DUMMY))

    def test_ordinary_fetch_never_adds_publisher_identity(self):
        with patch.object(SocketBoundFetcher,"_fetch_once",return_value=Mock()) as call:
            SocketBoundFetcher().fetch_once("https://example.invalid/",user_agent="fixture",max_bytes=64)
            self.assertNotIn("publisher_identity",call.call_args.kwargs)


class OfficialHoldTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_hold_is_owner_scoped_and_other_hosts_do_not_read_store(self):
        from core.dragon_crawler import CrawlerError
        app=Mock();store=Mock()
        app._acquisition_store.return_value=store
        store.find_one=AsyncMock(return_value={"_id":"fixture"})
        await api.assert_no_api_restriction(app,SCOPE,["example.invalid"])
        store.find_one.assert_not_awaited()
        with self.assertRaises(CrawlerError):
            await api.assert_no_api_restriction(app,SCOPE,["api.github.com"])
        predicate=store.find_one.await_args.args[0]
        self.assertEqual(predicate["_id"],{"$in":[api.api_record_id(SCOPE,"api.github.com")]})
        self.assertNotEqual(api.api_record_id(SCOPE,"api.github.com"),
                            api.api_record_id({**SCOPE,"owner_id":"other"},"api.github.com"))


class LocalQualificationTests(unittest.TestCase):
    def setUp(self):
        folder=TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name).resolve()

    def test_direct_entity_retention_and_scope(self):
        store=RawExportCustody(self.root/"raw.sqlite3",create=True)
        body=b'{"name":"synthetic export"}'
        sha=hashlib.sha256(body).hexdigest()
        with patch("core.dragon_raw_export_custody.shutil.disk_usage",return_value=Mock(free=2**40)):
            receipt=store.retain_response(SCOPE,body,expected_sha=sha,operation="fixture",
                    retention_seconds=300,rights_acknowledged=True)
            self.assertEqual(store.read_chunk(SCOPE,receipt["id"],0),body)
            with self.assertRaises(LookupError):
                store.read_chunk({**SCOPE,"owner_id":"foreign"},receipt["id"],0)
            with self.assertRaises(ValueError):
                store.retain_response(SCOPE,body,expected_sha="0"*64,operation="changed",
                       retention_seconds=300,rights_acknowledged=True)

    def setup_root(self,name):
        root=self.root/name;root.mkdir(mode=0o700)
        (root/"fixture").write_bytes(b"outer")
        child=root/"child";child.mkdir(mode=0o700)
        (child/"fixture").write_bytes(b"inner")
        return root

    def plan(self,root,name):
        data={"schema":discovery.SCHEMA,"roots":[{"id":"fixture","plane":"source","path":str(root)}]}
        path=self.root/name;_new_json(path,data)
        return path,hashlib.sha256(_json(data)).hexdigest()

    def test_full_declared_tree_and_exact_mirror(self):
        source=self.setup_root("source")
        mirror=self.setup_root("mirror")
        plan,sha=self.plan(source,"plan.json")
        mirror_plan,_=self.plan(mirror,"mirror.json")
        ledger=self.root/"inventory.sqlite3"
        result=discovery.discover(plan,ledger,expected_plan_sha=sha,offline_acknowledged=True)
        self.assertEqual(result["files"],2)
        self.assertFalse(result["all_application_roots_proven"])
        self.assertIn("configuration",result["missing_planes"])
        checked=discovery.verify_mirror(ledger,mirror_plan,
                 expected_inventory_digest=result["inventory_digest"],offline_acknowledged=True)
        self.assertTrue(checked["declared_mirror_verified"])
        (mirror/"extra").write_bytes(b"unexpected")
        with self.assertRaises(DeploymentHeld):
            discovery.verify_mirror(ledger,mirror_plan,expected_inventory_digest=result["inventory_digest"],
                                    offline_acknowledged=True)

    def test_symlink_or_special_object_holds_inventory(self):
        source=self.setup_root("source")
        try:(source/"alias").symlink_to(source/"fixture")
        except (OSError,NotImplementedError):self.skipTest("symlink support unavailable")
        plan,sha=self.plan(source,"plan.json")
        with self.assertRaises(DeploymentHeld):
            discovery.discover(plan,self.root/"inventory.sqlite3",expected_plan_sha=sha,offline_acknowledged=True)

    def test_real_two_worker_graph_and_fts_qualification(self):
        with patch("core.dragon_lead_graph.MIN_RESERVE",0),patch(
                "core.dragon_graph_deployment.RESERVE",0):
            report=qualification.qualify(self.root,workers=2,rows_per_worker=8,scratch_acknowledged=True)
        self.assertEqual(report["rows"],16)
        self.assertGreaterEqual(report["nodes"],16*17)
        self.assertTrue(report["synthetic_canonical_ingestion_verified"])
        self.assertTrue(report["cleanup_verified"])
        self.assertFalse(report["production_maximum_capacity_verified"])
        self.assertEqual(list(self.root.iterdir()),[])


if __name__=="__main__":unittest.main()
