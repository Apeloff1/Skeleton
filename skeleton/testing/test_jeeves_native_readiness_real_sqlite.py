"""Check canonical SQLite readiness without promoting a fake GGUF to real.

The production SQLite handle, SessionGate and SupervisedAI are genuine;
the token generator and installed-source witness are explicitly synthetic.
No physical GGUF/Windows/model-rights/release evidence is created here.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_readiness import inspect_native_jeeves
from skeleton.testing.laptop_native_sqlite_reopen_support import (
    RealSQLiteSyntheticGGUFRig, MODEL, TOKENIZER, SOURCE,
)


@unittest.skipUnless(
    os.name=="posix" and Path("/proc/self/fd").is_dir(),
    "descriptor-backed canonical SQLite requires Linux",
)
class TestJeevesReadinessWithCanonicalSpine(unittest.TestCase):
    def setUp(self):
        self.rig=RealSQLiteSyntheticGGUFRig()
        self.addCleanup(self.rig.close)
        self.stack,self.worker,self.report=self.rig.activate(
            model_root=self.rig.model_root,
            state_dir=self.rig.root,
            tenant="local",subject="operator",
        )
        self.addCleanup(self.stack.close)

    def test_canonical_sqlite_requires_explicit_installed_source_witness(self):
        result=inspect_native_jeeves(self.worker,object())
        self.assertTrue(result.model_bound)
        self.assertTrue(result.tenant_bound)
        self.assertTrue(result.sqlite_spine_present)
        self.assertFalse(result.source_receipt_bound)
        self.assertFalse(result.source_bridge_ready)
        self.assertEqual(self.rig.backends[0].calls,0)

    def test_source_only_simulation_can_exercise_positive_branch_under_patch(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source",
            return_value=dict(SOURCE),
        ) as inspector:
            result=inspect_native_jeeves(self.worker,object())
        inspector.assert_called_once()
        self.assertIs(inspector.call_args.args[0],self.worker)
        self.assertIs(type(inspector.call_args.args[1]),object)
        self.assertTrue(result.model_bound)
        self.assertTrue(result.sqlite_spine_present)
        self.assertTrue(result.source_receipt_bound)
        self.assertTrue(result.source_bridge_ready)
        self.assertFalse(result.real_turn_witnessed)
        self.assertFalse(result.device_qualified)
        self.assertFalse(result.release_certified)
        self.assertEqual(self.rig.backends[0].calls,0)

    def test_source_witness_throw_is_fail_closed_and_error_is_redacted(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source",
            side_effect=RuntimeError("/private/weights/operator-key"),
        ):
            result=inspect_native_jeeves(self.worker,object())
        self.assertFalse(result.source_bridge_ready)
        self.assertFalse(result.source_receipt_bound)
        self.assertNotIn("/private/weights",str(result.to_record()))
        self.assertEqual(self.rig.backends[0].calls,0)

    def test_installed_source_wrong_model_is_not_promoted(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source",
            return_value={**SOURCE,"model_sha256":"f"*64},
        ):
            result=inspect_native_jeeves(self.worker,object())
        self.assertFalse(result.source_receipt_bound)
        self.assertFalse(result.source_bridge_ready)
        self.assertEqual(self.rig.backends[0].calls,0)

    def test_installed_source_wrong_tokenizer_is_not_promoted(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source",
            return_value={**SOURCE,"tokenizer_sha256":"f"*64},
        ):
            result=inspect_native_jeeves(self.worker,object())
        self.assertFalse(result.source_receipt_bound)
        self.assertFalse(result.source_bridge_ready)

    def test_installer_report_shape_must_be_complete_and_finite(self):
        modified=(
            None,False,"yes",[],
            {**SOURCE,"installed_model_bytes":0},
            {**SOURCE,"installed_shard_count":True},
            {**SOURCE,"installed_shard_count":0},
            {**SOURCE,"installed_model_bytes":1.5},
            {**SOURCE,"installed_model_bytes":None},
            {**SOURCE,"installed_model_bytes":10**12+1},
            {**SOURCE,"installed_shard_count":65537},
            {**SOURCE,"manifest_sha256":"A"*64},
            {**SOURCE,"archive_sha256":"z"*63},
            {**SOURCE,"source_sha":"Q"*40},
            {**SOURCE,"source_sha":"a"*39},
            {**SOURCE,"unexpected_source_rights_claim":True},
        )
        for witness in modified:
            with self.subTest(value=repr(witness)[:60]),mock.patch(
                "skeleton.jeeves.agent.native_readiness.require_activated_source",
                return_value=witness,
            ):
                result=inspect_native_jeeves(self.worker,object())
                self.assertFalse(result.source_bridge_ready)

    def test_model_epoch_change_blocks_source_inspection(self):
        self.rig.backends[0].model_digest="f"*64
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source"
        ) as witness:
            result=inspect_native_jeeves(self.worker,object())
        witness.assert_not_called()
        self.assertFalse(result.model_bound)
        self.assertFalse(result.source_bridge_ready)

    def test_sqlite_readiness_status_never_generates_or_writes(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source",
            return_value=dict(SOURCE),
        ):
            result=inspect_native_jeeves(self.worker,object())
        self.assertTrue(result.source_bridge_ready)
        self.assertEqual(self.rig.query_one("SELECT COUNT(*) FROM sessions"),(0,))
        self.assertEqual(self.rig.backends[0].calls,0)
        self.assertFalse(result.to_record()["release_certified"])
        self.assertFalse(result.to_record()["real_turn_witnessed"])


if __name__=="__main__":
    unittest.main()
