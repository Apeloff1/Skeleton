"""Hostile serialized replay bundles must fail closed before replay."""
from __future__ import annotations
import unittest
from skeleton.game.gameplay.ridge_rescue.custody import CustodyError, verify_run


class SerializedBundleSafetyTests(unittest.TestCase):
    def test_duplicate_envelope_key(self) -> None:
        with self.assertRaises(CustodyError):
            verify_run('{"payload":{},"payload":{},"sha256":"x"}')

    def test_duplicate_nested_key(self) -> None:
        with self.assertRaises(CustodyError):
            verify_run('{"payload":{"state":{"turn":1,"turn":2}},"sha256":"x"}')

    def test_nonfinite_json_number(self) -> None:
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(CustodyError):
                verify_run('{"payload":{"state":' + value + '},"sha256":"x"}')

    def test_bytes_input_obeys_same_policy(self) -> None:
        with self.assertRaises(CustodyError):
            verify_run(b'{"payload":{},"payload":{},"sha256":"x"}')


if __name__ == "__main__":
    unittest.main()
