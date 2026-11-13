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

class ColdReopenPreflightTests(unittest.TestCase):
    def test_approval_is_exact_boolean_before_any_activation(self):
        rig=SyntheticColdRig()
        for denied in (False,0,1,"yes",[True],None):
            with self.subTest(approved=repr(denied)),rig.patch() as (activated,_,_):
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(**{**OPTS,"approved":denied})
                activated.assert_not_called()
        self.assertEqual(rig.count,0)

    def test_invalid_paths_and_traversals_are_held_before_installer_reads(self):
        for field,value in (
            ("model_root",Path("relative/model")),
            ("state_dir",Path("relative/state")),
            ("capacity_root",Path("relative/capacity")),
            ("model_root",Path("/private/../hostile")),
            ("state_dir",Path("/private/../outside")),
            ("model_root",None),
        ):
            rig=SyntheticColdRig()
            with self.subTest(field=field,value=str(value)),rig.patch() as (activate,_,_):
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(**{**OPTS,field:value})
                activate.assert_not_called()

    def test_invalid_private_utf8_does_not_create_sqlite_state(self):
        worker=FakeWorker()
        for prompt in (None,True,0,[],"","  \r\n","hello\x00bad","\ud800","a"*32769):
            rig=SyntheticColdRig()
            with self.subTest(prompt=repr(prompt)[:20]),rig.patch() as (activated,_,_):
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(**{**OPTS,"prompt":prompt})
                activated.assert_not_called()
            self.assertFalse(rig.first.spine.created)

    def test_bad_native_context_budget_rejected_before_startup(self):
        for changes in (
            {"n_ctx":127},{"n_ctx":128,"max_new_tokens":128},
            {"max_new_tokens":0},{"n_threads":0},{"gpu_layers":129},
            {"capacity_slots":0},{"capacity_budget_bytes":0},
        ):
            rig=SyntheticColdRig()
            with self.subTest(changes=changes),rig.patch() as (activated,_,_):
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(**{**OPTS,**changes})
                activated.assert_not_called()

    def test_missing_installed_rights_is_not_synthetic_device_pass(self):
        rig=SyntheticColdRig()
        with rig.patch() as (activate,initial,reopened):
            initial.side_effect=ContractViolation("missing verified rights")
            with self.assertRaises(ContractViolation):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.count,1)
        self.assertEqual(rig.first.generation_calls,0)
        self.assertEqual(rig.second.generation_calls,0)

    def test_second_installer_failure_never_downgrades_to_fake_replay(self):
        rig=SyntheticColdRig()
        original=rig.activate
        def denied(**kw):
            if rig.count:
                raise ContractViolation("reopened installer rejected the source")
            return original(**kw)
        with rig.patch() as (activate,_,_):
            activate.side_effect=denied
            with self.assertRaisesRegex(ContractViolation,"installer rejected"):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)
        self.assertIn("closed_1",rig.order)


if __name__=="__main__":
    unittest.main()
