"""Core finite JSON input, registry and full source case execution."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.catalog import domains
from skeleton.ai.runtime.operational_ai.reliability_fabric.fixtures import run_all
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import (
    Rejected,canonical,strict_json)
class FabricCore(unittest.TestCase):
    def test_complete_registry(self):
        self.assertEqual(len(domains()),40)
        self.assertEqual(len(set(domains())),40)
    def test_duplicate_json_keys_refused(self):
        with self.assertRaises(Rejected):
            strict_json(b'{"x":1,"x":2}')
    def test_nan_is_never_authority(self):
        with self.assertRaises(Rejected):
            strict_json(b'{"temperature":NaN}')
    def test_surrogate_never_canonical(self):
        with self.assertRaises(Rejected):
            canonical({"x":"\ud800"})
    def test_escaped_lone_surrogates_refused_in_values_and_keys(self):
        hostile=(
            b'{"key":"\\ud800"}',
            b'{"nested":["\\udfff"]}',
            b'{"\\ud800":"key"}',
            b'["safe",{"inner":"\\udc00"}]',
        )
        for raw in hostile:
            with self.subTest(raw=raw):
                with self.assertRaises(Rejected):
                    strict_json(raw)

    def test_valid_unicode_surrogate_pair_still_decodes(self):
        self.assertEqual(strict_json(b'{"emoji":"\\ud83d\\ude00"}'),
                         {"emoji":"😀"})

    def test_full_forty_gate_matrix(self):
        rows=run_all()
        self.assertEqual(sum(x["cases"] for x in rows),880)
        self.assertEqual(sum(x["accepted"] for x in rows),80)
        self.assertEqual(sum(x["rejected"] for x in rows),800)
if __name__=="__main__":
    unittest.main()
