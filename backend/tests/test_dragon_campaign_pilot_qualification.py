"""Hermetic Dragon Atlas pilot qualification, policy and release-hold tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from core.dragon_campaign_pilot_qualification import qualify_dragon_pilot


def _stage(n: int):
    return [
        {"ordinal": i, "name": "verified_source_stage",
         "receipt_digest": "a" * 64, "chain_digest": "b" * 64}
        for i in range(n)
    ]


def _report():
    return {
        "schema_version": "skeleton.dragon.campaign_atlas_dashboard.v1",
        "atlas_digest": "a" * 64, "snapshot_digest": "b" * 64,
        "mandate_digest": "c" * 64, "run_sequence": 5,
        "stages": _stage(26),
        "read_only": True, "network_executed": False,
        "publication_granted": False, "training_permission": False,
        "review_required": True,
        "source_policy": {
            "digest": "d" * 64, "sources_seen": 2,
            "included_source_count": 2, "excluded_source_count": 0,
        },
        "retrieval": {
            "digest": "e" * 64, "retained_hits": 2, "distinct_hosts": 2,
        },
        "review_operations": {
            "tasks_total": 2, "pending_tasks": 2, "blocked_tasks": 0,
            "durable_review_mutations": False, "human_review_recorded": False,
        },
        "forensics": {
            "report_digest": "f" * 64,
            "atlas_digest": "a" * 64,
            "source_policy_digest": "d" * 64,
            "retrieval_digest": "e" * 64,
            "stages": _stage(26),
            "selected_passages": 2,
            "privacy_held_sources": 0,
            "active_content_held_sources": 0,
            "security_held_sources": 0,
            "provenance_held_sources": 0,
            "grounding_deficit_objectives": 0,
            "query_unsupported_objectives": 0,
            "context_budget_exceeded": False,
            "source_bodies_redacted": True,
            "publication_granted": False,
            "training_permission": False,
            "network_or_model_invoked": False,
        },
        "operations": {
            "report_digest": "1" * 64,
            "source_snapshot_digest": "b" * 64,
            "run_sequence": 5,
            "stages": _stage(6),
            "source_text_redacted": True, "read_only": True,
            "network_executed": False,
            "automatic_recovery_authorized": False,
            "capacity_holds": [],
            "observed_resource_samples": 1,
            "pending_dispatch": False,
            "uncertain_bytes": 0,
            "historical_events_incomplete": False,
            "event_clock_integrity_review": False,
            "unresolved_robots_origins": 0,
            "stale_robots_origins": 0,
        },
        "context": {
            "raw_source_text_redacted": True,
            "fresh_policy_recheck_required": True,
        },
        "scorecard": {"decision": "human_review_hold"},
        "source_similarity": {"source_bodies_redacted": True},
        "retrieval_robustness": {
            "source_bodies_excluded": True, "flagged_objectives": [],
        },
    }


class DragonPilotQualificationTests(unittest.TestCase):
    def test_healthy_pilot_never_grants_release_or_publication(self):
        report = qualify_dragon_pilot(_report())
        self.assertEqual(report["pilot_status"], "ready_for_human_review")
        self.assertEqual(report["blocked_checks"], [])
        self.assertTrue(all(c["status"] == "qualified" for c in report["checks"]))
        self.assertEqual(len(report["external_release_checks"]), 10)
        self.assertFalse(report["release_authorized"])
        self.assertFalse(report["publication_authorized"])
        self.assertFalse(report["training_authorized"])
        self.assertTrue(report["human_review_required"])
        self.assertTrue(report["recheck_mongo_authority_before_any_followup"])

    def test_deterministic_source_bound_digest(self):
        a = qualify_dragon_pilot(_report())
        b = qualify_dragon_pilot(deepcopy(_report()))
        self.assertEqual(a, b)
        value = dict(a)
        digest = value.pop("qualification_digest")
        self.assertEqual(digest, sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode()).hexdigest())
        altered = _report()
        altered["snapshot_digest"] = "2" * 64
        altered["operations"]["source_snapshot_digest"] = "2" * 64
        self.assertNotEqual(qualify_dragon_pilot(altered)["qualification_digest"], digest)

    def test_withdrawal_conservatively_holds_pilot(self):
        metadata = _report()
        metadata["source_policy"]["included_source_count"] = 1
        metadata["source_policy"]["excluded_source_count"] = 1
        receipt = qualify_dragon_pilot(metadata)
        self.assertIn("current_policy", receipt["blocked_checks"])
        self.assertEqual(receipt["pilot_status"], "held_for_repair")
        self.assertFalse(receipt["release_authorized"])

    def test_unknown_dispatch_and_incomplete_history_hold_recovery(self):
        metadata = _report()
        metadata["operations"].update(
            pending_dispatch=True, uncertain_bytes=2048,
            historical_events_incomplete=True,
        )
        receipt = qualify_dragon_pilot(metadata)
        self.assertIn("restart_custody", receipt["blocked_checks"])
        self.assertIn("reconcile_canonical_worker_and_mongo_checkpoint",
                      receipt["operator_actions"])

    def test_native_frozen_capacity_holds_remain_advisory(self):
        metadata = _report()
        metadata["operations"]["capacity_holds"] = (
            "physical_resource_pressure_unobserved",
        )
        metadata["retrieval_robustness"]["flagged_objectives"] = (
            "source_diversity_review",
        )
        receipt = qualify_dragon_pilot(metadata)
        self.assertIn("measured_capacity", receipt["blocked_checks"])
        self.assertIn("source_robustness", receipt["blocked_checks"])
        self.assertFalse(receipt["release_authorized"])

    def test_resource_hold_type_guard_rejects_unbounded_or_forged_rows(self):
        for bad in (None, "not-list", (False,), ("x" * 100,), tuple("x" for _ in range(257))):
            with self.subTest(bad=type(bad).__name__):
                metadata = _report()
                metadata["operations"]["capacity_holds"] = bad
                with self.assertRaises(ValueError):
                    qualify_dragon_pilot(metadata)
        for bad in (None, ["x" * 100], (True,), tuple("x" for _ in range(9))):
            with self.subTest(bad=type(bad).__name__):
                metadata = _report()
                metadata["retrieval_robustness"]["flagged_objectives"] = bad
                with self.assertRaises(ValueError):
                    qualify_dragon_pilot(metadata)

    def test_forensic_and_review_holds_fail_closed(self):
        metadata = _report()
        metadata["forensics"]["privacy_held_sources"] = 1
        metadata["forensics"]["grounding_deficit_objectives"] = 1
        metadata["review_operations"]["blocked_tasks"] = 1
        metadata["review_operations"]["pending_tasks"] = 1
        metadata["retrieval_robustness"]["flagged_objectives"] = ["gap-a"]
        receipt = qualify_dragon_pilot(metadata)
        self.assertEqual(
            set(receipt["blocked_checks"]) & {
                "human_review_queue", "security_and_privacy",
                "provenance_and_grounding", "source_robustness",
            },
            {"human_review_queue", "security_and_privacy",
             "provenance_and_grounding", "source_robustness"},
        )

    def test_no_captured_evidence_is_not_pilot_ready(self):
        metadata = _report()
        metadata["source_policy"].update(
            sources_seen=0, included_source_count=0,
        )
        metadata["retrieval"].update(retained_hits=0, distinct_hosts=0)
        metadata["forensics"]["selected_passages"] = 0
        receipt = qualify_dragon_pilot(metadata)
        self.assertIn("current_policy", receipt["blocked_checks"])
        self.assertIn("source_bound_evidence", receipt["blocked_checks"])

    def test_tampered_cross_plane_digests_refused(self):
        metadata = _report()
        metadata["forensics"]["source_policy_digest"] = "9" * 64
        with self.assertRaises(ValueError):
            qualify_dragon_pilot(metadata)
        metadata = _report()
        metadata["operations"]["run_sequence"] += 1
        with self.assertRaises(ValueError):
            qualify_dragon_pilot(metadata)

    def test_missing_or_modified_stage_chain_refused(self):
        metadata = _report()
        metadata["operations"]["stages"][0]["chain_digest"] = "not-hex"
        with self.assertRaises(ValueError):
            qualify_dragon_pilot(metadata)
        metadata = _report()
        metadata["stages"].pop()
        with self.assertRaises(ValueError):
            qualify_dragon_pilot(metadata)

    def test_unsafe_authority_flags_cannot_be_repackaged(self):
        for path, value in (
            (("publication_granted",), True),
            (("training_permission",), True),
            (("context", "raw_source_text_redacted"), False),
            (("operations", "automatic_recovery_authorized"), True),
            (("forensics", "network_or_model_invoked"), True),
            (("review_operations", "human_review_recorded"), True),
        ):
            with self.subTest(path=path):
                metadata = _report()
                target = metadata
                for component in path[:-1]:
                    target = target[component]
                target[path[-1]] = value
                with self.assertRaises(PermissionError):
                    qualify_dragon_pilot(metadata)

    def test_denies_invalid_types_counters_and_unsupported_metadata(self):
        for key, value in (
            ("sources_seen", True),
            ("included_source_count", -1),
            ("excluded_source_count", 65),
        ):
            with self.subTest(key=key):
                metadata = _report()
                metadata["source_policy"][key] = value
                with self.assertRaises(ValueError):
                    qualify_dragon_pilot(metadata)
        metadata = _report()
        metadata["scorecard"]["decision"] = "auto_approved"
        with self.assertRaises(PermissionError):
            qualify_dragon_pilot(metadata)

    def test_never_echoes_source_text_or_sensitive_metadata(self):
        metadata = _report()
        secret = "PRIVATE_SOURCE_TEXT_ACCESS_TOKEN_SHOULD_NOT_BE_RETURNED"
        metadata["raw_external_document"] = secret
        metadata["operator_private_email"] = secret
        receipt = qualify_dragon_pilot(metadata)
        self.assertNotIn(secret, json.dumps(receipt))
        self.assertNotIn("raw_external_document", json.dumps(receipt))
        self.assertLess(len(json.dumps(receipt)), 12_000)


if __name__ == "__main__":
    unittest.main()
