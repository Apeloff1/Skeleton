"""Offline custody fixtures. Never use production stores or devices."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import os
import sqlite3

from core import dragon_graph_deployment as deploy
from core import dragon_graph_authority as graph
from core.dragon_lead_graph import LeadGraph
from core.dragon_release_queue import ReleaseQueue

SCOPE={"tenant_id":"deployment","owner_id":"fixture"}


class DeploymentTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.base=Path(temp.name).resolve();self.root=self.base/"corpus.sqlite"
        self.root.touch(mode=0o600)
        self.paths=tuple(self.base/("lane-"+str(i)+".sqlite") for i in range(graph.LANES))
        self.graph=LeadGraph(self.root)
        self.graph.configure(SCOPE,enabled=True,acknowledged=True)
        with ReleaseQueue(self.root)._db():pass

    def activate(self):
        graph.provision(self.root,self.paths,offline_acknowledged=True)

    def test_legacy_backup_and_resumable_full_upgrade(self):
        with self.assertRaises(deploy.DeploymentHeld):
            deploy.prepare(self.root,self.paths,self.base/"workspace")
        plan=deploy.prepare(self.root,self.paths,self.base/"workspace",offline_acknowledged=True)
        self.assertFalse(plan["deployed"])
        self.assertEqual(plan["backup"]["files"],1)
        first=deploy.apply(self.base/"workspace",offline_acknowledged=True)
        self.assertTrue(first["all_writer_modes_enabled"])
        self.assertEqual(deploy.apply(self.base/"workspace",offline_acknowledged=True),first)
        self.assertTrue(self.graph.status(SCOPE)["same_owner_disjoint_lanes"])
        self.assertTrue(graph.qualify(self.root,full=True)["full_integrity_audit"])

    def test_canonical_backup_and_isolated_restore_drill(self):
        self.activate()
        backup=self.base/"backup"
        receipt=deploy.backup(self.root,backup,offline_acknowledged=True)
        self.assertEqual(receipt["files"],11)
        self.assertEqual(deploy.verify_backup(backup),receipt)
        result=deploy.drill(backup,self.base/"drill",offline_acknowledged=True)
        self.assertTrue(result["full_graph_audit"])
        self.assertFalse(result["app_launch_qualified"])
        self.assertEqual(result["epoch"],graph.qualify(self.root)["epoch"])
        self.assertEqual(deploy.verify_backup(backup),receipt)

    def test_tampering_and_no_overwrite(self):
        self.activate()
        target=self.base/"backup";deploy.backup(self.root,target,offline_acknowledged=True)
        with self.assertRaises(FileExistsError):
            deploy.backup(self.root,target,offline_acknowledged=True)
        with (target/"lane-0.sqlite3").open("ab") as file:file.write(b"bad")
        with self.assertRaises(deploy.DeploymentHeld):deploy.verify_backup(target)
        self.assertTrue(graph.qualify(self.root)["epoch"])

    def test_exact_restore_and_preexisting_root_refusal(self):
        self.activate();target=self.base/"backup"
        deploy.backup(self.root,target,offline_acknowledged=True)
        # Vacate originals only inside disposable fixture; preserve everything.
        originals=self.base/"originals";originals.mkdir(mode=0o700)
        for path in (self.root,*self.paths):path.rename(originals/path.name)
        self.assertFalse(self.root.exists())
        result=deploy.restore_new(target,offline_acknowledged=True)
        self.assertTrue(result["root_published_last"])
        self.assertTrue(deploy.restore_new(target,offline_acknowledged=True)["replayed"])
        with sqlite3.connect(self.root) as db:
            db.execute("UPDATE dragon_graph_authority SET commit_sequence=commit_sequence+1")
        with self.assertRaises(deploy.DeploymentHeld):deploy.restore_new(target,offline_acknowledged=True)
        self.assertTrue(graph.qualify(self.root)["epoch"])

    def test_staged_restore_resumes_without_overwriting_different_file(self):
        self.activate();target=self.base/"backup"
        deploy.backup(self.root,target,offline_acknowledged=True)
        original_dir=self.base/"originals";original_dir.mkdir(mode=0o700)
        for p in (self.root,*self.paths):p.rename(original_dir/p.name)
        _,manifest=deploy._manifest(target)
        row=manifest["files"][1];destination=Path(row["original"])
        witness={k:row[k] for k in ("bytes","sha256")}
        stage=destination.parent/("."+destination.name+".dragon-restore-"+witness["sha256"][:24])
        deploy._copy(target/row["name"],stage)
        self.assertTrue(deploy.restore_new(target,offline_acknowledged=True)["restored"])
        self.assertFalse(stage.exists())

    def test_capacity_accounts_for_shared_devices_and_denies_shortage(self):
        report=deploy._capacity([(self.base,100),(self.base,200)])
        self.assertEqual(len(report),1);self.assertEqual(report[0]["required_bytes"],300)
        with patch("core.dragon_graph_deployment.shutil.disk_usage",return_value=type("Disk",(),{"free":1})()):
            with self.assertRaises(deploy.DeploymentHeld):deploy._require_space([(self.base,100)])

    def test_real_bounded_fixture_io_and_graph_canary(self):
        self.activate()
        with self.assertRaises(deploy.DeploymentHeld):deploy.benchmark(self.root)
        result=deploy.benchmark(self.root,bytes_per_lane=deploy.BLOCK,acknowledged=True)
        self.assertEqual(result["bytes_written_and_readback"],graph.LANES*deploy.BLOCK)
        self.assertTrue(result["bounded_scratch_io_verified"])
        self.assertFalse(result["maximum_capacity_verified"])
        self.assertFalse(list(self.base.glob(".dragon-io-*")))
        canary=deploy.transaction_probe(self.root,bytes_per_lane=4096,rounds=2,acknowledged=True)
        self.assertTrue(canary["graph_canary_cycles_verified"])
        self.assertEqual(canary["verified_bytes"],graph.LANES*4096*2)
        self.assertFalse(canary["production_ingestion_throughput_verified"])
