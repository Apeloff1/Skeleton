"""The local scorecard records gates it ran and does not promote enterprise claims."""
from __future__ import annotations

import subprocess
import unittest

from skeleton.app.offline_local_scorecard import SCHEMA, measure_local_system


class LocalScorecardTests(unittest.TestCase):
    def test_measured_gates_leave_model_quality_and_volumes_unqualified(self):
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
        ).strip()
        report = measure_local_system(head=head)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["head"], head)
        self.assertTrue(report["exact_head"])
        self.assertTrue(report["gates"]["claim_faithfulness"]["passed"])
        self.assertTrue(report["gates"]["reference_read"]["passed"])
        self.assertTrue(report["gates"]["reference_write_approval"]["passed"])
        self.assertTrue(report["gates"]["reference_write_rollback"]["passed"])
        self.assertTrue(report["gates"]["background_job"]["passed"])
        quality = report["trained_model_quality"]
        self.assertEqual(quality["quality_state"], "unqualified")
        self.assertEqual(quality["reason"], "untrained_transport_only")
        self.assertFalse(quality["trained"])
        self.assertIsNone(quality["scores"])
        self.assertEqual(quality["tokens_generated"], 2)
        enterprise = report["enterprise"]
        self.assertEqual(enterprise["volume_count"], 421)
        self.assertFalse(enterprise["complete_claim_satisfied"])
        self.assertFalse(enterprise["promotion_performed"])
        self.assertEqual(enterprise["volumes_enterprise_qualified_or_superior"], 0)
        self.assertEqual(enterprise["profile_superior"], 0)
        again = measure_local_system(head=None)
        self.assertEqual(again["head"], "head_not_supplied")
        self.assertFalse(again["exact_head"])
        self.assertEqual(
            again["trained_model_quality"]["output_sha256"],
            quality["output_sha256"],
        )
        self.assertFalse(again["enterprise"]["promotion_performed"])


if __name__ == "__main__":
    unittest.main()
