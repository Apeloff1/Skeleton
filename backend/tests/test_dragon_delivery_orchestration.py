"""Hermetic publisher, offline queue, raw custody and device fixtures."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.dragon_export_jobs import ExportJobs
from core.dragon_raw_export_custody import RawExportCustody
from core import dragon_application_backup as backup
from core import dragon_capacity_qualification as capacity
from core import dragon_graph_deployment as custody

SCOPE={"tenant_id":"fixture","owner_id":"operator"}
OTHER={"tenant_id":"fixture","owner_id":"other"}


class LocalDeliveryTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()

    def test_import_queue_finite_replay_and_single_owner_runner(self):
        store=ExportJobs(self.root/"jobs.sqlite3",create=True)
        manifest=self.root/"manifest.json"
        report={"entries":[{"rows":1}]}
        with patch("core.dragon_export_jobs._bound_manifest"),patch("core.dragon_export_jobs.qualify_manifest",return_value=([],report)),patch(
                "core.dragon_export_jobs.time.time",return_value=100):
            a=store.enqueue(SCOPE,manifest,expected_sha="a"*64,execution_seconds=300,rights_acknowledged=True)
            b=store.enqueue(SCOPE,manifest,expected_sha="a"*64,execution_seconds=3600,rights_acknowledged=True)
        self.assertEqual(a["id"],b["id"])
        self.assertEqual(a["expires_at"],b["expires_at"])
        def apply(*args,**kwargs):
            kwargs["authorize"]()
            self.assertEqual(store.pulse(SCOPE,graph_factory=Mock())["state"],"drain_required")
            return {"manifest_sha256":"a"*64,"settlements":[]}
        with patch("core.dragon_export_jobs._bound_manifest"),patch("core.dragon_export_jobs.time.time",return_value=101),patch(
                "core.dragon_export_jobs.apply_manifest",side_effect=apply):
            self.assertEqual(store.pulse(OTHER,graph_factory=Mock())["state"],"idle")
            self.assertEqual(store.pulse(SCOPE,graph_factory=Mock())["state"],"sealed")

    def test_import_expiry_and_explicit_resume(self):
        store=ExportJobs(self.root/"jobs.sqlite3",create=True)
        with patch("core.dragon_export_jobs._bound_manifest"),patch("core.dragon_export_jobs.qualify_manifest",return_value=([],{"entries":[{"rows":1}]})),patch(
                "core.dragon_export_jobs.time.time",return_value=100):
            job=store.enqueue(SCOPE,self.root/"m.json",expected_sha="a"*64,execution_seconds=60,rights_acknowledged=True)
        with patch("core.dragon_export_jobs._bound_manifest"),patch("core.dragon_export_jobs.time.time",return_value=101),patch(
                "core.dragon_export_jobs.apply_manifest",side_effect=ValueError("fixture")):
            self.assertEqual(store.pulse(SCOPE,graph_factory=Mock())["state"],"held")
            with self.assertRaises(ValueError):store.resume(SCOPE,job["id"])
            self.assertFalse(store.resume(SCOPE,job["id"],offline_drained_acknowledged=True)["deadline_renewed"])
        with patch("core.dragon_export_jobs.time.time",return_value=160),patch("core.dragon_export_jobs.apply_manifest") as apply:
            self.assertEqual(store.pulse(SCOPE,graph_factory=Mock())["state"],"idle")
            apply.assert_not_called()

    def test_cancelled_import_stops_before_canonical_graph_work(self):
        store=ExportJobs(self.root/"jobs.sqlite3",create=True)
        with patch("core.dragon_export_jobs._bound_manifest"),patch(
                "core.dragon_export_jobs.qualify_manifest",return_value=([],{"entries":[{"rows":1}]})):
            store.enqueue(SCOPE,self.root/"m.json",expected_sha="a"*64,
                          execution_seconds=300,rights_acknowledged=True)
        with patch("core.dragon_export_jobs.apply_manifest") as apply:
            result=store.pulse(SCOPE,graph_factory=Mock(),cancelled=lambda:True)
        self.assertEqual(result["state"],"held")
        apply.assert_not_called()

    def test_raw_retention_exact_bytes_scope_and_expiry(self):
        store=RawExportCustody(self.root/"raw.sqlite3",create=True)
        raw=b"static independently authorized fixture\n"
        path=self.root/"data.bin";path.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest()
        with patch("core.dragon_raw_export_custody.time.time",return_value=100),patch(
                "core.dragon_raw_export_custody.shutil.disk_usage",return_value=Mock(free=2**40)):
            a=store.retain(SCOPE,path,expected_sha=sha,operation="once",retention_seconds=300,rights_acknowledged=True)
            b=store.retain(SCOPE,path,expected_sha=sha,operation="once",retention_seconds=600,rights_acknowledged=True)
            self.assertEqual(a["expires_at"],b["expires_at"])
            self.assertEqual(store.read_chunk(SCOPE,a["id"],0),raw)
            with self.assertRaises(LookupError):store.read_chunk(OTHER,a["id"],0)
        with patch("core.dragon_raw_export_custody.time.time",return_value=400):
            with self.assertRaises(LookupError):store.metadata(SCOPE,a["id"])
            self.assertEqual(store.purge_expired(SCOPE)["purged"],1)
            self.assertEqual(store.purge_expired(SCOPE)["purged"],0)

    def test_raw_hash_mismatch_cannot_retain(self):
        store=RawExportCustody(self.root/"raw.sqlite3",create=True)
        path=self.root/"data.bin";path.write_bytes(b"fixture")
        with self.assertRaisesRegex(ValueError,"SHA-256 differs"):
            store.retain(SCOPE,path,expected_sha="0"*64,operation="once",retention_seconds=300,rights_acknowledged=True)
        with sqlite3.connect(store.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM raw_exports").fetchone()[0],0)

    def test_capacity_real_disposable_scratch_and_cleanup(self):
        path=self.root/"fixture.sqlite3";path.touch(mode=0o600)
        with sqlite3.connect(path) as db:db.execute("CREATE TABLE sample(x)")
        with patch("core.dragon_capacity_qualification.ecosystem._enumerate",return_value=[("fixture",path)]),patch(
                "core.dragon_graph_deployment.RESERVE",0):
            with self.assertRaises(ValueError):capacity.qualify(bytes_per_device=capacity.BLOCK,rounds=1)
            result=capacity.qualify(bytes_per_device=capacity.BLOCK,rounds=1,scratch_acknowledged=True)
        self.assertEqual(result["scratch_bytes_verified"],capacity.BLOCK)
        self.assertTrue(result["bounded_device_io_verified"])
        self.assertFalse(result["physical_maximum_capacity_verified"])
        self.assertEqual(list(self.root.glob(".dragon-capacity-*")),[])

    def test_backup_requires_all_declared_planes(self):
        plan={"schema":backup.SCHEMA,"application_revision":"a"*40,"artifacts":[]}
        for plane in sorted(backup.REQUIRED):
            plan["artifacts"].append({"plane":plane,"path":str(self.root/plane),"bytes":1,
                                      "sha256":"b"*64,"protected_acknowledged":True})
        self.assertEqual(backup._validate_plan(plan),len(backup.REQUIRED))
        plan["artifacts"].pop()
        with self.assertRaisesRegex(ValueError,"coverage incomplete"):backup._validate_plan(plan)

    def test_combined_backup_and_readback(self):
        from core.dragon_mongo_receipt import _new_json
        knowledge=self.root/"knowledge.sqlite3";knowledge.touch(mode=0o600)
        with sqlite3.connect(knowledge) as db:db.execute("CREATE TABLE sample(x)")
        plan={"schema":backup.SCHEMA,"application_revision":"a"*40,"artifacts":[]}
        for plane in sorted(backup.REQUIRED):
            path=self.root/(plane+".fixture");path.touch(mode=0o600)
            raw=plane.encode();path.write_bytes(raw)
            plan["artifacts"].append({"plane":plane,"path":str(path),"bytes":len(raw),
                        "sha256":hashlib.sha256(raw).hexdigest(),"protected_acknowledged":True})
        private=self.root/"plan.json";_new_json(private,plan)
        dest=self.root/"package"
        with patch.dict(os.environ,{"SKL_DRAGON_KNOWLEDGE_DB_PATH":str(knowledge)},clear=True),patch(
                "core.dragon_graph_deployment.RESERVE",0):
            result=backup.export(private,dest,expected_plan_sha=backup._digest(plan),offline_acknowledged=True)
        self.assertTrue(result["declared_coverage_complete"])
        self.assertFalse(result["full_application_recovery_verified"])
        self.assertEqual(backup.verify(dest),result)
        (dest/"application-artifacts"/"0001.backup").write_bytes(b"altered")
        with self.assertRaises(custody.DeploymentHeld):backup.verify(dest)


class DeliverySchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_scheduler_never_opens_local_artifacts(self):
        from core.dragon_export_jobs import scheduler_pulse
        with patch.dict(os.environ,{},clear=True),patch("core.dragon_export_jobs._read_json") as read:
            self.assertFalse((await scheduler_pulse())["configured"])
            read.assert_not_called()

    async def test_incomplete_configuration_holds_without_file_access(self):
        from core.dragon_export_jobs import scheduler_pulse
        with patch.dict(os.environ,{"SKL_DRAGON_DELIVERY_SCHEDULER":"1"},clear=True),patch(
                "core.dragon_export_jobs._read_json") as read:
            self.assertTrue((await scheduler_pulse())["failed"])
            read.assert_not_called()


class RegistryConnectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_registry_plan_and_authorized_queue(self):
        from core.dragon_registry_connector import plan_connector,queue_connector
        from core.dragon_crawler import authenticated_scope
        from core.dragon_dataset_library import _library
        user={"email":"operator@example.com","tenant_id":"fixture","role":"editor"}
        scope=authenticated_scope(user)
        rev,_=_library();plan=plan_connector("steam-census-index",rev)
        app=Mock();app._grant_principal=AsyncMock();app.create_publisher_intake=AsyncMock(return_value={"session_id":"fixture"})
        body={k:plan[k] for k in ("target","registry_revision","plan_digest")}
        body.update(idempotency_key="operation",consent=True,rights_acknowledged=True,
            publisher_permission_acknowledged=True,independent_resource_acknowledged=True)
        result=await queue_connector(app,scope,body,principal=user)
        self.assertTrue(result["queued"])
        self.assertFalse(result["network_executed"])
        self.assertEqual(app.create_publisher_intake.await_args.args[1]["endpoint"],plan["endpoint"])

    async def test_mismatched_registry_and_unapproved_target_refuse(self):
        from core.dragon_registry_connector import plan_connector
        from core.dragon_dataset_library import _library
        rev,_=_library()
        for target,revision in (("steam-census-index","0"*64),("steam-fronkon",rev)):
            with self.assertRaises(ValueError):plan_connector(target,revision)


if __name__=="__main__":unittest.main()
