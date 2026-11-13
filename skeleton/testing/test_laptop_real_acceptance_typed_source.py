"""First-turn installed GGUF evidence must be typed, exact and source-only.

All receipt proof is patched and uses FakeWorker. These assertions never
certify weights, source rights, real inference, device or consumer readiness.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    first_turn_acceptance, source_contract,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.laptop_runtime_test_support import FakeWorker
from skeleton.testing.test_laptop_cold_reopen_source_custody import SOURCE


class TypedGGUFSourceContractTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.principal=ActiveModel.from_supervisor(self.worker)

    def test_authoritative_snapshot_is_well_typed_not_release_qualified(self):
        self.assertTrue(source_contract.valid_source_snapshot(dict(SOURCE),self.principal))
        self.assertFalse(hasattr(source_contract, "release_certified"))

    def test_reject_unsafe_identity_and_wrong_principal_type(self):
        for principal in (None,True,{},object()):
            with self.subTest(principal=repr(principal)):
                self.assertFalse(source_contract.valid_source_snapshot(SOURCE,principal))
        other=ActiveModel(
            self.principal.tenant,self.principal.subject,
            "f"*64,self.principal.tokenizer_sha256,
        )
        self.assertFalse(source_contract.valid_source_snapshot(SOURCE,other))

    def test_bad_source_types_and_inventory_never_create_sqlite(self):
        examples=(
            {"installed_model_bytes":True},
            {"installed_model_bytes":1.5},
            {"installed_model_bytes":0},
            {"installed_model_bytes":10**12+1},
            {"installed_shard_count":False},
            {"installed_shard_count":0},
            {"installed_shard_count":65537},
            {"source_sha":"Z"*40},
            {"source_sha":"a"*39},
            {"source_sha":"a"*65},
            {"manifest_sha256":"A"*64},
            {"archive_sha256":"g"*64},
            {"model_sha256":"f"*64},
            {"tokenizer_sha256":"e"*64},
            {"unverified_rights":True},
        )
        for changes in examples:
            with self.subTest(changes=changes):
                fake=FakeWorker()
                with mock.patch.object(
                    first_turn_acceptance,"require_activated_source",
                    return_value={**SOURCE,**changes},
                ):
                    with self.assertRaises(ContractViolation):
                        first_turn_acceptance.run(
                            fake,prompt="private",approved=True,
                            require_real=True,installed_receipt=object(),
                        )
                self.assertEqual(fake.generation_calls,0)
                self.assertFalse(fake.spine.created)

    def test_bad_second_witness_holds_committed_effect_without_reissue(self):
        for changes in (
            {"installed_model_bytes":True},
            {"installed_shard_count":False},
            {"manifest_sha256":"A"*64},
            {"source_sha":"f"*39},
            {"unexpected":"active"},
        ):
            with self.subTest(changes=changes):
                worker=FakeWorker()
                with mock.patch.object(
                    first_turn_acceptance,"require_activated_source",
                    side_effect=[dict(SOURCE),{**SOURCE,**changes}],
                ):
                    with self.assertRaises(ContractViolation):
                        first_turn_acceptance.run(
                            worker,prompt="private",approved=True,
                            installed_receipt=object(),require_real=True,
                        )
                self.assertEqual(worker.generation_calls,1)
                self.assertEqual(len(worker.spine.receipts),1)

    def test_no_installed_receipt_preserves_synthetic_only_evidence(self):
        result=first_turn_acceptance.run(
            self.worker,prompt="source-only test",approved=True,
        )
        self.assertFalse(result["native_model_observed"])
        self.assertFalse(result["operator_approved_real_inference"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(self.worker.generation_calls,1)


if __name__ == "__main__":
    unittest.main()
