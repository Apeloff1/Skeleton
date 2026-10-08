"""Adversarial serving-policy input validation and complete decision provenance."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.flgb_model_runtime import MAX_TOKENS
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler
from skeleton.ai.model_runtime.serving_policy import (
    PolicyAwareServingPlanner, ServiceClass, ServingRequest,
)


class TestServingPolicyInputIntegrity(unittest.TestCase):
    def planner(self):
        return PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2024))

    def test_request_id_rejects_invalid_types_and_controls(self):
        for invalid in (None, True, 5, [], {}, "", "r" * 257, "\x00", "\x1f", "\ud800"):
            with self.subTest(repr=repr(invalid)), self.assertRaises(ValueError):
                ServingRequest(invalid, 1, 1)

    def test_valid_unicode_identity_is_replay_stable(self):
        planner = self.planner()
        req = ServingRequest("plán-élève", 2, 1)
        self.assertEqual(planner.plan(req), planner.plan(req))
        self.assertEqual(len(planner.plan(req).digest), 64)

    def test_request_requires_typed_service_class(self):
        for value in (None, "interactive", "", 1, True, object()):
            with self.subTest(value=repr(value)), self.assertRaisesRegex(ValueError, "ServiceClass"):
                ServingRequest("r", 1, 1, service_class=value)

    def test_request_flags_are_strict_booleans(self):
        for field in ("prefix_cached", "draft_model_available"):
            for value in (None, "true", 1, 0, [], object()):
                with self.subTest(field=field, value=repr(value)), self.assertRaises(ValueError):
                    ServingRequest("r", 1, 1, **{field: value})

    def test_rejects_boolean_fractional_negative_and_oversized_tokens(self):
        for field in ("prompt_tokens", "output_tokens", "prefix_tokens"):
            for value in (True, 1.5, -1, MAX_TOKENS + 1):
                kwargs = dict(prompt_tokens=1, output_tokens=1, prefix_tokens=0)
                kwargs[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    ServingRequest("r", **kwargs)

    def test_combined_token_budget_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "token budget"):
            ServingRequest("r", MAX_TOKENS, 1)
        with self.assertRaisesRegex(ValueError, "token budget"):
            ServingRequest("r", 0, 0)
        self.assertEqual(
            ServingRequest("r", MAX_TOKENS - 1, 1).prompt_tokens, MAX_TOKENS - 1
        )

    def test_prefix_never_exceeds_prompt(self):
        with self.assertRaisesRegex(ValueError, "prefix exceeds"):
            ServingRequest("r", 1, 1, prefix_tokens=2)

    def test_request_boundary_rejects_wrong_object(self):
        with self.assertRaisesRegex(ValueError, "ServingRequest"):
            self.planner().plan(object())

    def test_pressure_inputs_require_integer_percentages(self):
        for name in ("kv_pressure_pct", "queue_pressure_pct"):
            for value in (True, 5.2, "1", -1, 101):
                with self.subTest(field=name, value=value), self.assertRaises(ValueError):
                    self.planner().plan(ServingRequest("r", 1, 1), **{name: value})

    def test_full_pressure_snapshot_bound_when_decision_does_not_change(self):
        planner = self.planner()
        req = ServingRequest("r", 12, 4)
        first = planner.plan(req, kv_pressure_pct=1, queue_pressure_pct=1)
        second = planner.plan(req, kv_pressure_pct=2, queue_pressure_pct=1)
        third = planner.plan(req, kv_pressure_pct=1, queue_pressure_pct=2)
        self.assertEqual(first.priority_boost, second.priority_boost)
        self.assertEqual(first.phase_mode, second.phase_mode)
        self.assertEqual(len({first.digest, second.digest, third.digest}), 3)

    def test_unavailable_prefix_cache_still_part_of_identity(self):
        planner = self.planner()
        cached = planner.plan(ServingRequest("r", 10, 1, prefix_cached=True))
        uncached = planner.plan(ServingRequest("r", 10, 1, prefix_cached=False))
        self.assertEqual(cached.prefill_tokens, uncached.prefill_tokens)
        self.assertNotEqual(cached.digest, uncached.digest)

    def test_unavailable_draft_model_still_part_of_identity(self):
        planner = self.planner()
        draft = planner.plan(ServingRequest("r", 10, 4, draft_model_available=True))
        no_draft = planner.plan(ServingRequest("r", 10, 4))
        self.assertFalse(draft.speculative)
        self.assertFalse(no_draft.speculative)
        self.assertNotEqual(draft.digest, no_draft.digest)

    def test_prefix_claim_distinguishes_receipts_without_reuse_authority(self):
        planner = self.planner()
        a = planner.plan(ServingRequest("r", 10, 4, prefix_tokens=4))
        b = planner.plan(ServingRequest("r", 10, 4, prefix_tokens=0))
        self.assertEqual(a.prefix_reused_tokens, 0)
        self.assertEqual(b.prefix_reused_tokens, 0)
        self.assertNotEqual(a.digest, b.digest)

    def test_policy_digest_is_bound_across_eras(self):
        a = PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2023))
        b = self.planner()
        request = ServingRequest("r", 10, 4)
        first = a.plan(request)
        second = b.plan(request)
        self.assertEqual(first.prefill_tokens, second.prefill_tokens)
        self.assertNotEqual(first.policy_digest, second.policy_digest)
        self.assertNotEqual(first.digest, second.digest)

    def test_all_service_classes_have_stable_priorities(self):
        planner = self.planner()
        boosts = []
        for service_class in ServiceClass:
            req = ServingRequest(service_class.value, 10, 1, service_class)
            left = planner.plan(req)
            self.assertEqual(left, planner.plan(req))
            boosts.append(left.priority_boost)
        self.assertEqual(boosts, [100, 25, 0, -25])

    def test_interactive_boost_under_pressure_is_explicit(self):
        planner = self.planner()
        req = ServingRequest("r", 10, 1, ServiceClass.INTERACTIVE)
        before = planner.plan(req, queue_pressure_pct=94)
        after = planner.plan(req, queue_pressure_pct=95)
        self.assertEqual(after.priority_boost - before.priority_boost, 50)
        self.assertIn("protect_interactive_latency", after.degradation)
        self.assertNotEqual(before.digest, after.digest)

    def test_background_degradation_threshold_is_explicit(self):
        planner = self.planner()
        req = ServingRequest("r", 10, 1, ServiceClass.BACKGROUND)
        before = planner.plan(req, queue_pressure_pct=89)
        after = planner.plan(req, queue_pressure_pct=90)
        self.assertEqual(after.priority_boost - before.priority_boost, -75)
        self.assertIn("deprioritize_background_under_queue_pressure", after.degradation)

    def test_prefix_affinity_requires_cached_attestation_flag(self):
        planner = self.planner()
        with_cache = ServingRequest("r", 100, 4, prefix_tokens=80, prefix_cached=True)
        without_cache = ServingRequest("r", 100, 4, prefix_tokens=80, prefix_cached=False)
        self.assertEqual(planner.plan(with_cache).prefix_reused_tokens, 80)
        self.assertEqual(planner.plan(without_cache).prefix_reused_tokens, 0)

    def test_speculative_requires_policy_draft_and_generation_window(self):
        policy = RuntimePolicyCompiler().compile(2024, requested=("speculative_decoding",))
        planner = PolicyAwareServingPlanner(policy)
        before = planner.plan(ServingRequest("r", 10, 7, draft_model_available=True))
        after = planner.plan(ServingRequest("r", 10, 8, draft_model_available=True))
        self.assertFalse(before.speculative)
        self.assertTrue(after.speculative)

    def test_pressure_disables_optimized_modes_without_changing_policy(self):
        policy = RuntimePolicyCompiler().compile(
            2024, requested=("speculative_decoding", "phase_disaggregation"),
        )
        planner = PolicyAwareServingPlanner(policy)
        req = ServingRequest("r", 2048, 32, draft_model_available=True)
        fast = planner.plan(req, kv_pressure_pct=89)
        limited = planner.plan(req, kv_pressure_pct=90)
        self.assertTrue(fast.speculative)
        self.assertEqual(fast.phase_mode, "disaggregated")
        self.assertFalse(limited.speculative)
        self.assertEqual(limited.phase_mode, "unified")
        self.assertEqual(fast.policy_digest, limited.policy_digest)


    def test_plan_verification_requires_matching_trusted_context(self):
        planner = self.planner()
        req = ServingRequest("r", 10, 5, prefix_tokens=4, prefix_cached=True)
        plan = planner.plan(req, kv_pressure_pct=30, queue_pressure_pct=20)
        verified = planner.verify(plan, req, kv_pressure_pct=30, queue_pressure_pct=20)
        self.assertEqual(plan, verified)
        self.assertEqual(plan.digest, verified.digest)

    def test_plan_verification_rejects_stale_pressure_receipt(self):
        planner = self.planner()
        req = ServingRequest("r", 10, 5)
        plan = planner.plan(req, kv_pressure_pct=30, queue_pressure_pct=20)
        for pressure in (
            dict(kv_pressure_pct=31, queue_pressure_pct=20),
            dict(kv_pressure_pct=30, queue_pressure_pct=21),
        ):
            with self.subTest(pressure=pressure), self.assertRaisesRegex(
                ValueError, "digest mismatch"
            ):
                planner.verify(plan, req, **pressure)

    def test_plan_verification_rejects_mutated_digest_and_public_fields(self):
        from dataclasses import replace
        planner = self.planner()
        req = ServingRequest("r", 10, 5)
        plan = planner.plan(req)
        forged = (
            replace(plan, digest="0" * 64),
            replace(plan, prefill_tokens=999),
            replace(plan, priority_boost=1000),
            replace(plan, degradation=("bogus",)),
        )
        for item in forged:
            with self.subTest(item=item), self.assertRaises(ValueError):
                planner.verify(item, req)

    def test_plan_verification_rejects_cross_policy_substitution(self):
        old = PolicyAwareServingPlanner(RuntimePolicyCompiler().compile(2023))
        new = self.planner()
        req = ServingRequest("r", 10, 5)
        receipt = old.plan(req)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            new.verify(receipt, req)

    def test_plan_verification_rejects_cross_request_substitution(self):
        planner = self.planner()
        req = ServingRequest("r", 10, 5)
        receipt = planner.plan(req)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            planner.verify(receipt, ServingRequest("different", 10, 5))
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            planner.verify(receipt, ServingRequest("r", 9, 6))

    def test_verifier_rejects_nonascii_and_non_string_digest_without_type_error(self):
        from dataclasses import replace
        planner = self.planner()
        req = ServingRequest("r", 10, 5)
        plan = planner.plan(req)
        for digest in (None, 42, True, "💡" * 64, "z" * 64, "A" * 64, "0" * 63):
            with self.subTest(value=repr(digest)), self.assertRaises(ValueError):
                planner.verify(replace(plan, digest=digest), req)

    def test_plan_verification_rejects_wrong_type(self):
        planner = self.planner()
        req = ServingRequest("r", 10, 5)
        for obj in (None, {}, "receipt", True):
            with self.subTest(value=repr(obj)), self.assertRaisesRegex(
                ValueError, "ServingPlan"
            ):
                planner.verify(obj, req)



if __name__ == "__main__":
    unittest.main()
