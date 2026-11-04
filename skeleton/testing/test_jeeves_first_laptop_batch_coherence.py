"""Cross-domain source observation consistency is required before approval."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.batch.catalog import manifest
from skeleton.jeeves.native_fabric.laptop_ops.batch.fixtures import (
    successful_bundle, negative_bundle, encode_bundle,
)
from skeleton.jeeves.native_fabric.laptop_ops.batch.runner import (
    evaluate_bundle, evaluate_json,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import list_domains

class TestBundleCoherence(unittest.TestCase):
    def test_valid_single_stages_may_still_overbook_combined_cpu(self):
        source = successful_bundle()
        source["cpu_admission"]["thread_capacity"]["reserved"] = 4096
        with self.assertRaises(LaptopGateHold):
            evaluate_bundle(source)

    def test_context_prompt_and_output_must_share_one_context_window(self):
        source = successful_bundle()
        source["context_window"]["output_reservation"]["reserved"] = 4096
        with self.assertRaises(LaptopGateHold):
            evaluate_bundle(source)

    def test_two_individually_valid_model_digests_must_match(self):
        for domain, first, second in (
            ("tokenizer_identity", "installed_tokenizer", "model_pairing"),
            ("native_session", "session_model", "active_model"),
            ("output_receipt", "committed_digest", "replayed_digest"),
            ("sqlite_replay", "committed_output", "replayed_output"),
            ("signed_sources", "signed_manifest", "loaded_manifest"),
            ("cold_restart", "checkpoint_digest", "loaded_checkpoint"),
            ("release_gates", "release_model", "installed_model"),
        ):
            with self.subTest(domain=domain):
                source = successful_bundle()
                source[domain][second] = {
                    "expected_sha256": "b" * 64,
                    "observed_sha256": "b" * 64,
                }
                with self.assertRaises(LaptopGateHold):
                    evaluate_bundle(source)

    def test_retrieval_grant_budget_and_memory_budget_crosscheck(self):
        cases = (
            ("source_retrieval", "source_capacity"),
            ("tool_grants", "grant_capacity"),
            ("memory_consent", "consent_capacity"),
        )
        for domain,stage in cases:
            with self.subTest(domain=domain):
                source = successful_bundle()
                source[domain][stage]["reserved"] = 1
                with self.assertRaises(LaptopGateHold):
                    evaluate_bundle(source)

    def test_cancellation_epoch_and_first_turn_reservation_crosscheck(self):
        source = successful_bundle()
        source["cancellation"]["cancel_epoch"]["current"] = 1
        with self.assertRaises(LaptopGateHold):
            evaluate_bundle(source)
        source = successful_bundle()
        source["first_turn"]["generation_reservation"]["reserved"] = 4096
        with self.assertRaises(LaptopGateHold):
            evaluate_bundle(source)

    def test_bad_region_never_partially_passes_other_regions(self):
        source = negative_bundle("bootstrap", "model_archive")
        if source is None:
            self.fail("all negative fixtures must be explicitly generated")
        self.assertFalse(evaluate_bundle(source).accepted_source_only)
