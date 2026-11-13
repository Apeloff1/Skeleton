"""Installed-source validation is a single contract for acceptance and chat."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.source_contract import (
    valid_source_snapshot as accepted,
)
from skeleton.jeeves.agent.native_source_fence import (
    valid_source_snapshot as guarded,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.testing.test_laptop_cold_reopen_source_custody import SOURCE
from skeleton.testing.laptop_runtime_test_support import FakeWorker


class ConsistentGGUFValidation(unittest.TestCase):
    def test_acceptance_and_live_source_share_one_validator(self):
        self.assertIs(accepted,guarded)

    def test_source_inventory_shards_hashes_and_owner_are_uniform(self):
        principal=ActiveModel.from_supervisor(FakeWorker())
        examples=(
            dict(SOURCE),
            {**SOURCE,"installed_model_bytes":True},
            {**SOURCE,"installed_shard_count":True},
            {**SOURCE,"manifest_sha256":"f"*64},
            {**SOURCE,"source_sha":"a"*64},
            {**SOURCE,"source_sha":"b"*39},
            {**SOURCE,"extra":True},
        )
        for value in examples:
            with self.subTest(value=value):
                self.assertEqual(accepted(value,principal),guarded(value,principal))


if __name__ == "__main__":
    unittest.main()
