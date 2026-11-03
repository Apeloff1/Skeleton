"""Recursive report privacy scanning rejects secret fields and unbounded nodes."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.privacy import (
    inspect_public,require_public,
)
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestNativePublicResultBoundary(unittest.TestCase):
    def test_hash_only_receipt_is_accepted(self):
        report={
            "source_sha256":"a"*64,"checkpoint_sha256":"b"*64,
            "elapsed_ms":123,"grade":False,"domains":[
                {"name":"sum","score_ppm":1000000},
            ],
        }
        self.assertTrue(inspect_public(report)["publishable"])
        require_public(report)

    def test_no_raw_prompts(self):
        for name in ("prompt","completion","system_prompt",
                     "checkpoint_json","raw_model_output","api_key",
                     "access_token","private_path","raw_token_ids"):
            with self.subTest(name=name),self.assertRaises(SupervisedRejected):
                require_public({"results":{name:"secret-value"}})

    def test_nested_payload_is_also_scanned(self):
        result=inspect_public({"output":[{"receipt":{"password":"secret"}}]})
        self.assertFalse(result["publishable"])
        self.assertEqual(len(result["private_fields"]),1)

    def test_recursive_node_ceiling(self):
        with self.assertRaises(SupervisedRejected):
            inspect_public({"list":[0,1,2,3,4]},max_nodes=4)

    def test_unrecognized_object_refused(self):
        with self.assertRaises(SupervisedRejected):
            inspect_public({"object":object()})

    def test_no_non_string_keys(self):
        with self.assertRaises(SupervisedRejected):
            inspect_public({1:"integer-key"})


if __name__=="__main__":
    unittest.main()
