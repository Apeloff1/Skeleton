"""Cold-reopen cannot accept malformed source inventory after restart.

All workers are simulated with a shared SQLite-shaped receipt store. A test
double does not prove native GGUF, source rights, physical device or release.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import cold_reopen_acceptance
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.test_laptop_cold_reopen_source_custody import (
    SyntheticColdRig, SOURCE, OPTS,
)


class StrictRestartedGGUFInventoryTests(unittest.TestCase):
    def test_first_snapshot_on_second_worker_must_remain_exact(self):
        for changes in (
            {"installed_model_bytes":True},
            {"installed_shard_count":True},
            {"installed_model_bytes":10**12+1},
            {"source_sha":"A"*40},
            {"manifest_sha256":"A"*64},
            {"extra_claim":"independently_qualified"},
        ):
            with self.subTest(changes=changes):
                rig=SyntheticColdRig()
                with rig.patch(second_source={**SOURCE,**changes}):
                    with self.assertRaises(ContractViolation):
                        cold_reopen_acceptance.run(**OPTS)
                self.assertEqual(rig.count,2)
                self.assertEqual(rig.first.generation_calls,1)
                self.assertEqual(rig.second.generation_calls,0)
                self.assertIn("closed_2",rig.order)

    def test_last_snapshot_cannot_change_type_after_sqlite_read(self):
        for changes in (
            {"installed_model_bytes":False},
            {"installed_shard_count":True},
            {"archive_sha256":"Z"*64},
            {"source_sha":"f"*39},
            {"manifest_sha256":"g"*64},
        ):
            with self.subTest(changes=changes):
                rig=SyntheticColdRig()
                with rig.patch() as (_,_,source):
                    source.side_effect=[dict(SOURCE),{**SOURCE,**changes}]
                    with self.assertRaises(ContractViolation):
                        cold_reopen_acceptance.run(**OPTS)
                self.assertEqual(rig.count,2)
                self.assertEqual(rig.first.generation_calls,1)
                self.assertEqual(rig.second.generation_calls,0)
                self.assertIn("closed_2",rig.order)

    def test_exact_source_acceptance_remains_read_only_on_reopen(self):
        rig=SyntheticColdRig()
        with rig.patch():
            record=cold_reopen_acceptance.run(**OPTS)
        self.assertTrue(record["sqlite_replay_after_cold_reopen"])
        self.assertTrue(record["source_verified_twice"])
        self.assertFalse(record["second_generation_attempted"])
        self.assertFalse(record["release_certified"])
        self.assertEqual(rig.first.generation_calls,1)
        self.assertEqual(rig.second.generation_calls,0)


if __name__ == "__main__":
    unittest.main()
