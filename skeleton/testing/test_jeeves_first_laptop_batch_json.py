"""Strict bounded JSON wire format for the complete first-laptop source bundle."""
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

from skeleton.jeeves.native_fabric.laptop_ops.batch.schema import BUNDLE_INPUT_SCHEMA
from skeleton.jeeves.native_fabric.laptop_ops.batch.limits import DEFAULT_BUNDLE_LIMITS
from skeleton.jeeves.native_fabric.laptop_ops.strict_json import decode

class TestBatchWireSafety(unittest.TestCase):
    def test_full_json_fixture_is_bounded_and_round_trips(self):
        payload = encode_bundle(successful_bundle())
        self.assertLessEqual(len(payload), DEFAULT_BUNDLE_LIMITS.max_evidence_bytes)
        self.assertTrue(evaluate_json(payload).accepted_source_only)
        self.assertEqual(decode(payload)["schema"], BUNDLE_INPUT_SCHEMA)

    def test_nonfinite_duplicate_key_and_invalid_unicode_fail(self):
        payloads = (
            b'{"schema":"x","schema":"y","domains":{}}',
            b'{"schema":"x","domains":{"extra":NaN}}',
            b'{"schema":"x","domains":{"\u0061":"\\ud800"}}',
            b'{"schema":"x","domains":{}} junk',
            b'\xff',
            b'',
            b'[]',
        )
        for value in payloads:
            with self.subTest(size=len(value)):
                with self.assertRaises(LaptopGateHold):
                    evaluate_json(value)

    def test_oversized_payload_held_before_parsing(self):
        oversized = b" " * (DEFAULT_BUNDLE_LIMITS.max_evidence_bytes + 1)
        with self.assertRaises(LaptopGateHold):
            evaluate_json(oversized)

    def test_wrong_schema_and_missing_domain_are_rejected(self):
        source = successful_bundle()
        wrong = b'{"schema":"outdated","domains":{}}'
        with self.assertRaises(LaptopGateHold):
            evaluate_json(wrong)
        truncated = dict(source)
        truncated.pop(next(iter(truncated)))
        with self.assertRaises(LaptopGateHold):
            evaluate_json(encode_bundle(truncated))

    def test_json_scalar_tree_depth_is_conservative(self):
        deep = b"[" * 60 + b"0" + b"]" * 60
        with self.assertRaises(LaptopGateHold):
            decode(deep)
