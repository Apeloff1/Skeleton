"""Explicit operator operations cannot alter live models or silently recover crash state."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.model.admission import (
    CapacityBroker,CapacityPolicy,Reservation,AdmissionError,AdmissionCorrupt,
)
from skeleton.ai.runtime.operational_ai.model.admission.migration import migrate_unused
from skeleton.ai.runtime.operational_ai.model.admission.recovery import reconcile_orphans
from skeleton.ai.runtime.operational_ai.model.admission.readiness import inspect_lease

D='c'*64

class OpsTests(unittest.TestCase):
    def setUp(self):
        ctx=tempfile.TemporaryDirectory();self.addCleanup(ctx.cleanup)
        self.root=Path(ctx.name)/'capacity';self.root.mkdir(mode=0o700)
        self.policy=CapacityPolicy(1,1_000_000_000,268435456)
        self.req=Reservation(D,'d'*64,'e'*64,300000000)

    def test_first_use_policy_migration_requires_approval(self):
        old=self.policy
        new=CapacityPolicy(2,2_000_000_000,268435456)
        with CapacityBroker(self.root,old) as broker:
            with self.assertRaises(AdmissionError):migrate_unused(broker,new)
            result=migrate_unused(broker,new,approved=True)
            self.assertIn('bootstrap',result['status'])
        with CapacityBroker(self.root,new) as broker:
            self.assertEqual(broker.inspect()['policy']['slots'],2)

    def test_never_migrate_after_any_model_lease(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.req,check_headroom=False):pass
            with self.assertRaises(AdmissionError):
                migrate_unused(broker,CapacityPolicy(2,2_000_000_000),approved=True)

    def test_orphan_repair_requires_explicit_operator_approval(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with self.assertRaises(AdmissionError):reconcile_orphans(broker)

    def test_never_repair_a_live_lease(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.req,check_headroom=False):
                report=reconcile_orphans(broker,approved=True)
                self.assertEqual(report['count'],0)
                self.assertEqual(broker.inspect()['occupied_slots'],1)

    def test_crashed_lease_operator_reconciles_only_free_kernel_slot(self):
        script='''from skeleton.ai.runtime.operational_ai.model.admission import *
import os,sys
b=CapacityBroker(sys.argv[1],CapacityPolicy(1,1000000000,268435456))
b.acquire(Reservation('c'*64,'d'*64,'e'*64,300000000),check_headroom=False)
os._exit(22)
'''
        p=subprocess.run([sys.executable,'-c',script,str(self.root)],
            env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])},capture_output=True,timeout=5)
        self.assertEqual(p.returncode,22,p.stderr)
        with CapacityBroker(self.root,self.policy) as broker:
            self.assertEqual(broker.inspect()['orphaned_slots'],[0])
            result=reconcile_orphans(broker,approved=True)
            self.assertEqual(result['count'],1)
            self.assertEqual(broker.inspect()['orphaned_slots'],[])

    def test_reconcile_limit_refuses_oversized_operator_batch(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with self.assertRaises(AdmissionError):reconcile_orphans(broker,approved=True,maximum=0)

    def test_only_real_operator_backend_matches_slot(self):
        class Stub:
            model_digest=D
            tokenizer_digest=D
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.req,check_headroom=False) as lease:
                self.assertEqual(inspect_lease(lease,Stub())['model_sha256'],D)
                Stub.model_digest='b'*64
                with self.assertRaises(AdmissionCorrupt):inspect_lease(lease,Stub())

    def test_operator_cli_does_not_initialize_missing_registry(self):
        from skeleton.ai.runtime.operational_ai.model.admission.cli import main
        before=set(self.root.iterdir())
        self.assertEqual(main(['--root',str(self.root)]),2)
        self.assertEqual(set(self.root.iterdir()),before)

    def test_doctor_verified_broker_report_excludes_private_names(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.req,check_headroom=False):
                report=broker.inspect()
                self.assertNotIn('root',str(report))
                self.assertNotIn('tenant',str(report))

if __name__=='__main__':unittest.main()
