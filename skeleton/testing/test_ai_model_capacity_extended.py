"""Capacity contract and inference-wrapper attacks; real locks, no model mocks for kernel facts."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.model.admission import (
    AdmissionError,AdmissionCorrupt,CapacityBroker,CapacityPolicy,Reservation,
)
from skeleton.ai.runtime.operational_ai.model.admission.wrapper import AdmittedBackend
from skeleton.ai.runtime.operational_ai.model.admission.paths import verified_dir,open_file,read_file
from skeleton.ai.runtime.operational_ai.model.admission.record import parse_record
from skeleton.ai.runtime.operational_ai.model.admission.canonical import canonical,digest

MODEL='a'*64
TOKEN='b'*64
MANIFEST='c'*64


class FakeNative:
    model_digest=MODEL
    tokenizer_digest=TOKEN
    def __init__(self):
        self.calls=0
        self.admissions=0

    def generate(self,*args,**kwargs):
        self.calls+=1
        return {'fake_for_unit_tests_only':True}

    def admit_before_reservation(self):
        self.admissions+=1
        return {'admitted':True}


class ExtendedTests(unittest.TestCase):
    def setUp(self):
        ctx=tempfile.TemporaryDirectory()
        self.addCleanup(ctx.cleanup)
        self.root=Path(ctx.name)/'private';self.root.mkdir(mode=0o700)
        self.policy=CapacityPolicy(slots=1,budget_bytes=1_000_000_000,
                                   minimum_host_margin_bytes=268435456)
        self.claim=Reservation(MODEL,'d'*64,MANIFEST,300000000)

    def test_live_model_wrapper_enforces_exact_digest(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.claim,check_headroom=False) as lease:
                runtime=AdmittedBackend(FakeNative(),lease)
                self.assertEqual(runtime.model_digest,MODEL)
                self.assertEqual(runtime.tokenizer_digest,TOKEN)
                self.assertEqual(runtime.generate(),{'fake_for_unit_tests_only':True})
                self.assertEqual(runtime.backend.calls,1)
                runtime.admit_before_reservation()
                self.assertEqual(runtime.backend.admissions,1)

    def test_released_capacity_cannot_generate_or_admit(self):
        with CapacityBroker(self.root,self.policy) as broker:
            lease=broker.acquire(self.claim,check_headroom=False)
            runtime=AdmittedBackend(FakeNative(),lease)
            lease.close()
            with self.assertRaises(AdmissionError):runtime.generate()
            with self.assertRaises(AdmissionError):runtime.admit_before_reservation()
            self.assertEqual(runtime.backend.calls,0)

    def test_no_model_without_valid_reservation(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.claim,check_headroom=False) as lease:
                fake=FakeNative();fake.model_digest='e'*64
                with self.assertRaises(AdmissionError):AdmittedBackend(fake,lease)

    def test_receipt_mutation_blocks_model_during_live_lease(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.claim,check_headroom=False) as lease:
                runtime=AdmittedBackend(FakeNative(),lease)
                os.pwrite(lease.fd,b'X',0)
                with self.assertRaises(AdmissionCorrupt):runtime.generate()
                self.assertEqual(runtime.backend.calls,0)
                with self.assertRaises(AdmissionCorrupt):lease.close()

    def test_kernel_unlock_detected_even_with_original_metadata(self):
        import fcntl
        with CapacityBroker(self.root,self.policy) as broker:
            lease=broker.acquire(self.claim,check_headroom=False)
            fcntl.flock(lease.fd, fcntl.LOCK_UN)
            with self.assertRaises(AdmissionCorrupt):lease.assert_live()
            lease.close()

    def test_broker_initial_read_only_root_is_private(self):
        self.root.chmod(0o755)
        with self.assertRaises(AdmissionError):CapacityBroker(self.root,self.policy)

    def test_broker_refuses_capacity_root_symlink(self):
        original=self.root
        new=self.root.parent/'new'
        new.mkdir(mode=0o700)
        original.rmdir()
        original.symlink_to(new)
        with self.assertRaises(OSError):CapacityBroker(original,self.policy)

    def test_slot_link_attack_before_claim(self):
        with CapacityBroker(self.root,self.policy) as broker:
            (self.root/'model-slot-00.lock').symlink_to(self.root/'policy.json')
            with self.assertRaises(OSError):broker.acquire(self.claim,check_headroom=False)

    def test_receipt_rejects_model_field_swap(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.claim,check_headroom=False) as lease:
                record=dict(lease._entry)
                rec=dict(record['reservation']);rec['model_sha256']='f'*64
                record['reservation']=rec
                with self.assertRaises(AdmissionCorrupt):parse_record(canonical(record),self.policy,lease.slot)

    def test_policy_file_checksum_forbidden_unknown_field(self):
        with CapacityBroker(self.root,self.policy):pass
        fd=os.open(self.root/'policy.json',os.O_RDWR)
        try:
            os.ftruncate(fd,0)
            os.write(fd,b'{"version":1,"slots":1,"budget_bytes":1000000000,"minimum_host_margin_bytes":268435456,"ignore":true}')
        finally:os.close(fd)
        with self.assertRaises(AdmissionCorrupt):CapacityBroker(self.root,self.policy)

    def test_never_store_plain_tenant_or_user(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.claim,check_headroom=False) as lease:
                raw=read_file(lease.fd)
                self.assertNotIn(b'operator@email',raw)
                self.assertIn(MODEL.encode(),raw)

    def test_slot_status_explicitly_not_memory_oom_certification(self):
        with CapacityBroker(self.root,self.policy) as broker:
            self.assertIn('not-oom-certification',broker.inspect()['status'])

    def test_repeat_close_is_idempotent(self):
        with CapacityBroker(self.root,self.policy) as broker:
            lease=broker.acquire(self.claim,check_headroom=False)
            lease.close()
            lease.close()
            self.assertEqual(broker.inspect()['occupied_slots'],0)

    def test_live_proof_is_kernel_held(self):
        with CapacityBroker(self.root,self.policy) as broker:
            with broker.acquire(self.claim,check_headroom=False) as lease:
                self.assertEqual(lease.assert_live()['status'],'kernel-slot-held')
                self.assertEqual(broker.inspect()['active'][0]['model_sha256'],MODEL)

    def test_python_json_bool_not_valid_reservation_integer(self):
        with self.assertRaises(AdmissionError):Reservation(MODEL,'d'*64,MANIFEST,False)


if __name__=='__main__':unittest.main()
