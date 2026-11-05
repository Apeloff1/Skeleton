"""Cold-reopen GGUF acceptance: simulated worker contracts, not device proof.

The test double intentionally shares its in-memory SQLite-shaped receipt
mapping between two distinct native workers. The real acceptance path uses
activate_checked twice against the persisted canonical SQLite spine.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, redirect_stderr
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    cold_reopen_acceptance,
    first_turn_acceptance,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


SOURCE={
    "model_sha256":MODEL,
    "tokenizer_sha256":TOKENIZER,
    "manifest_sha256":"c"*64,
    "archive_sha256":"d"*64,
    "source_sha":"e"*40,
    "installed_model_bytes":2048,
    "installed_shard_count":1,
}
OPTS={
    "model_root":Path("/private/approved-gguf"),
    "state_dir":Path("/private/sqlite"),
    "tenant":"local",
    "subject":"owner",
    "prompt":"  private local first turn\n",
    "approved":True,
}


class SyntheticColdRig:
    def __init__(self):
        self.first=FakeWorker()
        self.second=FakeWorker()
        self.second.spine=self.first.spine
        self.order=[]
        self.count=0
        self.after_first=None
        self.replace_second=None

    @contextmanager
    def _stack(self,number):
        self.order.append("open_"+str(number))
        try:
            yield
        finally:
            self.order.append("closed_"+str(number))
            if number==1 and self.after_first:
                self.after_first()

    def activate(self, **kw):
        self.count+=1
        self.order.append("activate_"+str(self.count))
        if self.count==1:
            return self._stack(1),self.first,object()
        if self.count==2:
            if "closed_1" not in self.order:
                raise AssertionError("second native child opened before first closed")
            return self._stack(2),self.replace_second or self.second,object()
        raise AssertionError("unexpected third native activation")

    @contextmanager
    def patch(self, *,second_source=None):
        with (
            mock.patch.object(cold_reopen_acceptance,"activate_checked",
                side_effect=self.activate) as activated,
            mock.patch.object(first_turn_acceptance,
                "require_activated_source",return_value=dict(SOURCE)) as initial,
            mock.patch.object(cold_reopen_acceptance,
                "require_activated_source",
                return_value=dict(SOURCE) if second_source is None else second_source
            ) as reopened,
        ):
            yield activated,initial,reopened

class ColdSourceCustodyTests(unittest.TestCase):
    def test_one_generation_cold_close_and_committed_replay(self):
        rig=SyntheticColdRig()
        with rig.patch() as (activated,initial,reopened):
            record=cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.count,2)
        self.assertEqual(rig.order,[
            "activate_1","open_1","closed_1",
            "activate_2","open_2","closed_2",
        ])
        self.assertEqual(activated.call_count,2)
        self.assertEqual(initial.call_count,2)
        self.assertEqual(reopened.call_count,2)
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)
        self.assertEqual(len(rig.first.spine.receipts),1)
        self.assertEqual(record["schema"],"laptop-native-cold-reopen-e2e.v1")
        self.assertEqual(record["model_sha256"],MODEL)
        self.assertEqual(record["tokenizer_sha256"],TOKENIZER)
        self.assertTrue(record["source_verified_twice"])
        self.assertTrue(record["sqlite_replay_after_cold_reopen"])
        self.assertFalse(record["second_generation_attempted"])
        self.assertFalse(record["private_prompt_disclosed"])
        self.assertFalse(record["physical_device_qualified"])
        self.assertFalse(record["release_certified"])

    def test_new_worker_is_mandatory_not_same_inprocess_instance(self):
        rig=SyntheticColdRig()
        rig.replace_second=rig.first
        with rig.patch():
            with self.assertRaisesRegex(ContractViolation,"independently activated"):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.count,2)
        self.assertIn("closed_2",rig.order)
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)

    def test_unchanged_model_source_manifest_required_at_reopen(self):
        rig=SyntheticColdRig()
        changed={**SOURCE,"manifest_sha256":"f"*64}
        with rig.patch(second_source=changed):
            with self.assertRaisesRegex(ContractViolation,"source changed"):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.count,2)
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)

    def test_installed_archive_and_rights_revision_cannot_change(self):
        for label,value in (
            ("archive_sha256","f"*64),
            ("source_sha","f"*40),
            ("installed_shard_count",2),
        ):
            rig=SyntheticColdRig()
            with self.subTest(label=label),rig.patch(second_source={
                **SOURCE,label:value,
            }):
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(**OPTS)
            self.assertEqual(rig.first.generation_calls,1)
            self.assertEqual(rig.second.generation_calls,0)

    def test_cold_source_epoch_change_prevents_replay_attribution(self):
        rig=SyntheticColdRig()
        rig.after_first=lambda:setattr(
            rig.first.spine.backend,"model_digest","f"*64,
        )
        with rig.patch():
            # The canonical source check can reject at the earlier
            # active-backend/principal mismatch, before our later epoch check.
            # Both are fail-closed holds and neither permits replay disclosure.
            with self.assertRaises(ContractViolation):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)

    def test_missing_sqlite_after_full_restart_is_not_regenerated(self):
        rig=SyntheticColdRig()
        rig.after_first=rig.first.spine.receipts.clear
        with rig.patch():
            with self.assertRaisesRegex(ContractViolation,"not authoritative"):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.count,2)
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)

    def test_cold_pending_recovery_has_no_implicit_third_activation(self):
        rig=SyntheticColdRig()
        rig.after_first=rig.first.spine.receipts.clear
        with rig.patch():
            with self.assertRaises(ContractViolation):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.count,2)
        self.assertEqual(rig.second.generation_calls,0)

    def test_callback_runs_before_second_worker_closes(self):
        rig=SyntheticColdRig()
        seen=[]
        def publish(worker,receipt,report):
            seen.append(report["schema"])
            self.assertIs(worker,rig.second)
            self.assertEqual(rig.second.generation_calls,0)
            self.assertNotIn("closed_2",rig.order)
            self.assertTrue(report["sqlite_replay_after_cold_reopen"])
        with rig.patch():
            report=cold_reopen_acceptance.run(**OPTS,publisher=publish)
        self.assertEqual(seen,["laptop-native-cold-reopen-e2e.v1"])
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)
        self.assertEqual(rig.order[-1],"closed_2")
        self.assertFalse(report["release_certified"])

    def test_invalid_publisher_never_activates_native(self):
        rig=SyntheticColdRig()
        with rig.patch():
            with self.assertRaises(ContractViolation):
                cold_reopen_acceptance.run(**OPTS,publisher=object())
        self.assertEqual(rig.count,0)

    def test_failed_publication_closes_second_worker_without_retry(self):
        rig=SyntheticColdRig()
        def refuse_write(worker,receipt,report):
            raise RuntimeError("synthetic sink unavailable")
        with rig.patch():
            with self.assertRaises(RuntimeError):
                cold_reopen_acceptance.run(**OPTS,publisher=refuse_write)
        self.assertEqual(rig.count,2)
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)
        self.assertEqual(rig.order[-1],"closed_2")


if __name__=="__main__":
    unittest.main()
