"""Synthetic native source and SQLite operator custody regression tests.

The model is a TEST DOUBLE and its installed source proof is explicitly
patched. Passing these tests neither qualifies an installed GGUF/rights
approval, real inference, laptop hardware, Windows/WSL2 nor release.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import BytesIO, StringIO
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER,
)

SOURCE = {
    "model_sha256": MODEL,
    "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64,
    "archive_sha256": "d" * 64,
    "source_sha": "e" * 40,
    "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


def make_fence(worker, *, source=SOURCE, tenant="local", subject="owner"):
    with mock.patch(
        "skeleton.jeeves.agent.native_source_fence.require_activated_source",
        return_value=dict(source) if type(source) is dict else source,
    ) as witness:
        fence = NativeSourceFence(
            worker, object(), expected_tenant=tenant,
            expected_subject=subject,
        )
    return fence


class NativeSourceFenceTests(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()

    def test_canonical_source_and_principal_are_explicitly_bounded(self):
        fence = make_fence(self.worker)
        self.assertEqual(fence.principal.model_sha256, MODEL)
        self.assertEqual(fence.principal.tokenizer_sha256, TOKENIZER)
        self.assertEqual(fence.principal.tenant, "local")
        self.assertEqual(fence.principal.subject, "owner")
        self.assertIs(fence.release_certified, False)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_same_model_but_another_worker_cannot_use_native_fence(self):
        fence = make_fence(self.worker)
        with self.assertRaisesRegex(ContractViolation, "different native worker"):
            fence.assert_live(FakeWorker())
        self.assertEqual(self.worker.generation_calls, 0)

    def test_wrong_tenant_or_subject_refused_before_source_inspection(self):
        for tenant, subject in (("other", "owner"), ("local", "foreign")):
            with self.subTest(tenant=tenant, subject=subject):
                with mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                ) as witness:
                    with self.assertRaisesRegex(ContractViolation, "requested owner"):
                        NativeSourceFence(
                            self.worker, object(), expected_tenant=tenant,
                            expected_subject=subject,
                        )
                    witness.assert_not_called()
        self.assertEqual(self.worker.generation_calls, 0)

    def test_source_proof_requires_exact_nonprivate_fields(self):
        for report in (
            None, True, {}, {"model_sha256": MODEL}, "verified",
            {**SOURCE, "unverified_device_claim": True},
            {**SOURCE, "model_sha256": "f" * 64},
            {**SOURCE, "tokenizer_sha256": "f" * 64},
        ):
            with self.subTest(report=repr(report)[:32]):
                with mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                    return_value=report,
                ) as witness:
                    with self.assertRaises(ContractViolation):
                        NativeSourceFence(
                            self.worker, object(), expected_tenant="local",
                            expected_subject="owner",
                        )
                    self.assertEqual(witness.call_count, 1)

    def test_invalid_source_inventory_and_digests_are_refused(self):
        invalid = (
            {"installed_model_bytes": True},
            {"installed_shard_count": True},
            {"installed_model_bytes": 10**12 + 1},
            {"installed_shard_count": 65537},
            {"installed_shard_count": -1},
            {"manifest_sha256": "0" * 63},
            {"manifest_sha256": "A" * 64},
            {"archive_sha256": "Z" * 64},
            {"source_sha": "Q" * 40},
            {"source_sha": "a" * 39},
            {"unknown_proof": "self-reported"},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                report = {**SOURCE, **changes}
                with mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                    return_value=report,
                ):
                    with self.assertRaises(ContractViolation):
                        NativeSourceFence(
                            self.worker, object(),
                            expected_tenant="local", expected_subject="owner",
                        )
        self.assertEqual(self.worker.generation_calls, 0)

    def test_midstream_malformed_inventory_cannot_be_published(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=[dict(SOURCE), dict(SOURCE),
                         {**SOURCE, "installed_shard_count": True}],
        ):
            fence = NativeSourceFence(
                self.worker, object(), expected_tenant="local",
                expected_subject="owner",
            )
            with self.assertRaises(ContractViolation):
                fence.assert_live(self.worker)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_changed_archive_or_installed_source_is_held_between_commands(self):
        for field, invalid in (
            ("manifest_sha256", "f" * 64),
            ("archive_sha256", "f" * 64),
            ("source_sha", "f" * 40),
            ("installed_model_bytes", 4096),
        ):
            with self.subTest(field=field):
                worker = FakeWorker()
                with mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                    side_effect=[
                        dict(SOURCE), dict(SOURCE),
                        {**SOURCE, field: invalid},
                    ],
                ) as witness:
                    fence = NativeSourceFence(
                        worker, object(), expected_tenant="local",
                        expected_subject="owner",
                    )
                    with self.assertRaisesRegex(ContractViolation, "source"):
                        fence.assert_live(worker)
                    self.assertEqual(witness.call_count, 3)
                self.assertEqual(worker.generation_calls, 0)

    def test_changed_model_or_tokenizer_during_private_operation_holds(self):
        for attr in ("model_digest", "tokenizer_digest"):
            worker = FakeWorker()
            with self.subTest(attr=attr):
                fence = make_fence(worker)
                setattr(worker.spine.backend, attr, "f" * 64)
                with self.assertRaises(ContractViolation):
                    fence.assert_live(worker)
                self.assertEqual(worker.generation_calls, 0)

    def test_foreign_owner_during_read_is_denied_without_source_claim(self):
        fence = make_fence(self.worker)
        self.worker.spine.identity.subject = "foreign"
        with self.assertRaises(ContractViolation):
            fence.assert_live(self.worker)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_source_callback_that_changes_owner_after_witness_is_held(self):
        count = {"calls": 0}
        def switch_worker(*args):
            count["calls"] += 1
            if count["calls"] == 2:
                self.worker.spine.identity.subject = "foreign"
            return dict(SOURCE)
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=switch_worker,
        ):
            with self.assertRaisesRegex(ContractViolation, "principal changed"):
                NativeSourceFence(
                    self.worker, object(), expected_tenant="local",
                    expected_subject="owner",
                )

    def test_lease_loss_during_status_is_fail_closed(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=[dict(SOURCE), dict(SOURCE),
                         ContractViolation("native capacity lease expired")],
        ):
            fence = NativeSourceFence(
                self.worker, object(), expected_tenant="local",
                expected_subject="owner",
            )
            with self.assertRaisesRegex(ContractViolation, "lease expired"):
                fence.assert_live(self.worker)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_installer_failure_holds_before_any_operator_model_use(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=ContractViolation("missing installed archive rights"),
        ):
            with self.assertRaises(ContractViolation):
                NativeSourceFence(
                    self.worker, object(), expected_tenant="local",
                    expected_subject="owner",
                )
        self.assertEqual(self.worker.generation_calls, 0)


if __name__ == "__main__":
    unittest.main()
