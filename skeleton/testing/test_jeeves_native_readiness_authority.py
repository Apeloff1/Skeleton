"""A self-asserted GGUF report must not pass Jeeves source readiness.

Synthetic only: no installed weight bytes, native model generation,
Windows/WSL2, rights adjudication or release evidence is produced.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.jeeves.agent.native_readiness import inspect_native_jeeves
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER,
)


class ForgedReport:
    content_verified=True
    rights_approved=True
    source_sha="a"*40
    archive_sha256="b"*64
    model_sha256=MODEL
    tokenizer_sha256=TOKENIZER
    manifest_sha256="c"*64
    release_certified=False
    shard_count=1
    model_bytes=4096


class TestJeevesReadinessAuthority(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()

    def test_fake_supervisor_and_forged_rights_are_never_source_ready(self):
        result=inspect_native_jeeves(self.worker,ForgedReport())
        self.assertTrue(result.model_bound)
        self.assertTrue(result.tenant_bound)
        self.assertFalse(result.sqlite_spine_present)
        self.assertFalse(result.source_receipt_bound)
        self.assertFalse(result.source_bridge_ready)
        self.assertFalse(result.real_turn_witnessed)
        self.assertFalse(result.device_qualified)
        self.assertFalse(result.release_certified)

    def test_fake_sqlite_methods_and_db_attribute_cannot_bypass_type_checks(self):
        self.worker.spine.db=object()
        self.worker.spine.session_gate=object()
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source"
        ) as witness:
            result=inspect_native_jeeves(self.worker,ForgedReport())
        witness.assert_not_called()
        self.assertFalse(result.sqlite_spine_present)
        self.assertFalse(result.source_bridge_ready)

    def test_fake_installer_witness_is_not_queried_for_noncanonical_worker(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_readiness.require_activated_source",
            side_effect=AssertionError("must not inspect fake source"),
        ) as witness:
            record=inspect_native_jeeves(self.worker,ForgedReport())
        witness.assert_not_called()
        self.assertFalse(record.source_bridge_ready)

    def test_none_installer_receipt_does_not_claim_installed_rights(self):
        result=inspect_native_jeeves(self.worker)
        self.assertFalse(result.source_receipt_bound)
        self.assertFalse(result.source_bridge_ready)
        self.assertTrue(any("source" in hold for hold in result.holds))

    def test_stale_model_sha_denied_even_before_source_witness(self):
        self.worker.spine.backend.model_digest="e"*64
        result=inspect_native_jeeves(self.worker,ForgedReport())
        self.assertFalse(result.model_bound)
        self.assertFalse(result.source_bridge_ready)

    def test_stale_tokenizer_denied_even_before_source_witness(self):
        self.worker.spine.backend.tokenizer_digest="e"*64
        result=inspect_native_jeeves(self.worker,ForgedReport())
        self.assertFalse(result.model_bound)
        self.assertFalse(result.source_bridge_ready)

    def test_fake_readiness_fields_do_not_claim_generation_or_release(self):
        result=inspect_native_jeeves(self.worker,ForgedReport()).to_record()
        self.assertEqual(result["schema"],"jeeves.native_readiness.v1")
        for key in (
            "sqlite_spine_present","source_receipt_bound",
            "source_bridge_ready","real_turn_witnessed",
            "device_qualified","release_certified",
        ):
            self.assertIs(result[key],False)
        self.assertNotIn("model_source_rights_independently_verified",result)
        self.assertNotIn("private",str(result))

    def test_random_worker_and_absent_spine_cannot_claim_source(self):
        for worker in (None,object(),{},True,[]):
            with self.subTest(worker=type(worker).__name__):
                result=inspect_native_jeeves(worker,ForgedReport())
                self.assertFalse(result.source_bridge_ready)
                self.assertFalse(result.sqlite_spine_present)
                self.assertFalse(result.real_turn_witnessed)

    def test_no_source_witness_on_receipt_like_mapping(self):
        raw=vars(ForgedReport)
        result=inspect_native_jeeves(self.worker,dict(raw))
        self.assertFalse(result.source_bridge_ready)
        self.assertFalse(result.source_receipt_bound)


if __name__ == "__main__":
    unittest.main()
