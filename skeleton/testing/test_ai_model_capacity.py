"""Adversarial kernel-locked model capacity tests; no native model required."""
from __future__ import annotations
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.model.admission import (
    CapacityBroker, CapacityPolicy, Reservation,
    AdmissionBusy, AdmissionCorrupt, AdmissionError,
)
from skeleton.ai.runtime.operational_ai.model.admission.canonical import canonical,parse
from skeleton.ai.runtime.operational_ai.model.admission.proc import current_identity,process_start_tick
from skeleton.ai.runtime.operational_ai.model.admission.record import parse_record
from skeleton.ai.runtime.operational_ai.model.admission.paths import open_file,verified_dir

D1='1'*64
D2='2'*64
D3='3'*64


class CapacityTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory(prefix='ai-model-capacity-')
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)/'capacity'
        self.root.mkdir(mode=0o700)
        self.policy=CapacityPolicy(slots=2,budget_bytes=1_000_000_000,
                                   minimum_host_margin_bytes=268435456)

    def broker(self,policy=None):
        return CapacityBroker(self.root,policy or self.policy)

    def reserve(self,bytes_=300000000):
        return Reservation(D1,D2,D3,bytes_)

    def test_policy_and_reservation_reject_bool_and_overflow(self):
        with self.assertRaises(AdmissionError):CapacityPolicy(slots=True)
        with self.assertRaises(AdmissionError):CapacityPolicy(budget_bytes=1)
        with self.assertRaises(AdmissionError):Reservation(D1,D2,D3,True)
        with self.assertRaises(AdmissionError):Reservation('ff',D2,D3,1)

    def test_policy_write_then_reopen_idempotently(self):
        with self.broker() as a:
            self.assertEqual(a.inspect()['free_slots'],2)
        with self.broker() as b:
            self.assertEqual(b.inspect()['remaining_bytes'],1_000_000_000)

    def test_mismatched_policy_cannot_reinterpret_existing_occupancy(self):
        with self.broker():
            with self.assertRaises(AdmissionCorrupt):
                CapacityBroker(self.root,CapacityPolicy(slots=3,budget_bytes=1_000_000_000))

    def test_lease_prevents_two_models_exceeding_slots(self):
        with self.broker() as broker:
            with broker.acquire(self.reserve(),check_headroom=False) as a:
                with broker.acquire(self.reserve(),check_headroom=False) as b:
                    self.assertNotEqual(a.slot,b.slot)
                    proof=broker.inspect()
                    self.assertEqual(proof['occupied_slots'],2)
                    with self.assertRaises(AdmissionBusy):broker.acquire(self.reserve(),check_headroom=False)
            self.assertEqual(broker.inspect()['occupied_slots'],0)

    def test_aggregate_budget_mandatory(self):
        with self.broker() as broker:
            with broker.acquire(self.reserve(800000000),check_headroom=False):
                with self.assertRaises(AdmissionBusy):broker.acquire(self.reserve(300000000),check_headroom=False)

    def test_read_only_inspection_does_not_claim_any_slot(self):
        with self.broker() as broker:
            report=broker.inspect()
            self.assertEqual(report['occupied_slots'],0)
            self.assertEqual(report['orphaned_slots'],[])

    def test_receipt_sequence_monotonically_increments(self):
        with self.broker() as broker:
            with broker.acquire(self.reserve(),check_headroom=False) as one:
                first=one._entry['sequence']
            with broker.acquire(self.reserve(),check_headroom=False) as two:
                self.assertEqual(two._entry['sequence'],first+1)

    def test_claimed_receipt_private_and_pinned(self):
        with self.broker() as broker:
            with broker.acquire(self.reserve(),check_headroom=False) as lease:
                entry=lease._entry
                self.assertEqual(entry['reservation']['model_sha256'],D1)
                self.assertEqual(entry['process']['pid'],os.getpid())
                self.assertEqual(stat.S_IMODE(os.stat(self.root/f'model-slot-{lease.slot:02d}.lock').st_mode),0o600)

    def test_new_model_pressure_check_executes_before_claim(self):
        with self.broker() as broker:
            with patch('skeleton.ai.runtime.operational_ai.model.admission.headroom.check',side_effect=AdmissionError('low memory')):
                with self.assertRaises(AdmissionError):broker.acquire(self.reserve())
            self.assertEqual(broker.inspect()['occupied_slots'],0)

    def test_lease_released_even_if_record_corrupt(self):
        with self.broker() as broker:
            lease=broker.acquire(self.reserve(),check_headroom=False)
            os.pwrite(lease.fd,b'X',0)
            with self.assertRaises(AdmissionCorrupt):lease.close()
            with self.assertRaises(AdmissionCorrupt):broker.inspect()

    def test_symlink_registry_file_refused(self):
        (self.root/'policy.json').symlink_to(self.root/'nowhere')
        with self.assertRaises(OSError):self.broker()

    def test_world_readable_registry_denied(self):
        with self.broker() as broker:
            pass
        (self.root/'policy.json').chmod(0o644)
        with self.assertRaises(AdmissionCorrupt):self.broker()

    def test_hardlinked_registry_denied(self):
        with self.broker():pass
        os.link(self.root/'policy.json',self.root/'another-policy')
        with self.assertRaises(AdmissionCorrupt):self.broker()

    def test_cross_process_claim_blocks_second_broker(self):
        with self.broker() as broker:
            with broker.acquire(self.reserve(),check_headroom=False) as lease:
                # A second process reads the owner's exact same serialized policy.
                script = '''from pathlib import Path
from skeleton.ai.runtime.operational_ai.model.admission import *
import sys
b=CapacityBroker(Path(sys.argv[1]),CapacityPolicy(2,1000000000,268435456))
try:
    with b.acquire(Reservation('1'*64,'2'*64,'3'*64,750000000),check_headroom=False):
        sys.exit(12)
except AdmissionBusy:
    sys.exit(0)
'''
                p=subprocess.run([sys.executable,'-c',script,str(self.root)],
                    capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])},timeout=5)
                self.assertEqual(p.returncode,0,p.stderr)

    def test_crash_does_not_leave_kernel_capacity_occupied(self):
        script='''from pathlib import Path
from skeleton.ai.runtime.operational_ai.model.admission import *
import os,sys
b=CapacityBroker(Path(sys.argv[1]),CapacityPolicy(2,1000000000,268435456))
b.acquire(Reservation('1'*64,'2'*64,'3'*64,300000000),check_headroom=False)
os._exit(17)
'''
        p=subprocess.run([sys.executable,'-c',script,str(self.root)],
            capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])},timeout=5)
        self.assertEqual(p.returncode,17,p.stderr)
        with self.broker() as broker:
            proof=broker.inspect()
            self.assertEqual(proof['occupied_slots'],0)
            self.assertEqual(proof['orphaned_slots'],[0])
            with broker.acquire(self.reserve(),check_headroom=False) as lease:
                self.assertEqual(lease._entry['sequence'],2)

    def test_passed_descriptor_retains_lease_across_parent_close(self):
        with self.broker() as broker:
            lease=broker.acquire(self.reserve(),check_headroom=False)
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.8)'],
                                   pass_fds=(lease.fd,),stdout=subprocess.DEVNULL)
            try:
                lease.close()
                # The inherited descriptor still owns the same flock kernel object.
                # A mismatched released receipt is fail-closed rather than a free slot.
                with self.assertRaises(AdmissionCorrupt):broker.inspect()
            finally:
                child.terminate();child.wait(timeout=5)
            self.assertEqual(broker.inspect()['occupied_slots'],0)

    def test_thread_safe_claim_one_slot(self):
        policy=CapacityPolicy(1,1_000_000_000,268435456)
        with self.broker(policy) as broker:
            barrier=threading.Barrier(2)
            hits=[]
            def go():
                barrier.wait(timeout=2)
                try:
                    with broker.acquire(self.reserve(),check_headroom=False):
                        hits.append('claimed');time.sleep(.2)
                except AdmissionBusy:
                    hits.append('busy')
            a=threading.Thread(target=go);b=threading.Thread(target=go)
            a.start();b.start();a.join(timeout=5);b.join(timeout=5)
            self.assertCountEqual(hits,['claimed','busy'])

    def test_released_lease_cannot_expose_fd(self):
        with self.broker() as broker:
            lease=broker.acquire(self.reserve(),check_headroom=False)
            lease.close()
            with self.assertRaises(AdmissionError):_=lease.fd

    def test_canonical_refuses_duplicate_and_noncanonical(self):
        with self.assertRaises(AdmissionCorrupt):parse(b'{"a":1,"a":2}')
        with self.assertRaises(AdmissionCorrupt):parse(b'{"b":1, "a":2}')

    def test_process_identity_matches_procfs(self):
        identity=current_identity()
        self.assertEqual(identity['pid'],os.getpid())
        self.assertEqual(identity['start_tick'],process_start_tick(os.getpid()))


if __name__=='__main__':unittest.main()
