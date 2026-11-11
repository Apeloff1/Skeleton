"""Strict portable receipt I/O contracts for reviewed original worlds."""
from __future__ import annotations

import json
import unittest

from skeleton.jeeves.worlds.world_canon import CanonError, propose
from skeleton.jeeves.worlds.world_session import (
    MAX_RECEIPT_BYTES, export_json, replay, restore_json,
)


def world():
    return propose(world_id="portable_io", premise="A new world begins.",
                   protagonist="Mira", region="Cinder Vale", goal="Find home.")


class PortableReceiptIOTests(unittest.TestCase):
    def test_round_trip_and_stable_canonical_bytes(self):
        source = world()
        payload = export_json(source, ["pursue_goal"])
        self.assertEqual(restore_json(source, payload), replay(source, ["pursue_goal"]))
        self.assertEqual(export_json(source, ["pursue_goal"]), payload)

    def test_duplicate_keys_fail_closed(self):
        source = world()
        payload = export_json(source, [])
        tampered = payload.replace(b'"schema":', b'"schema":"bad","schema":', 1)
        with self.assertRaises(CanonError) as raised:
            restore_json(source, tampered)
        self.assertEqual(raised.exception.code, "duplicate_json_key")

    def test_oversize_receipt_rejected_before_decode(self):
        with self.assertRaises(CanonError) as raised:
            restore_json(world(), b"{" + b" " * MAX_RECEIPT_BYTES + b"}")
        self.assertEqual(raised.exception.code, "session_too_large")

    def test_non_bytes_and_malformed_utf8_rejected(self):
        for payload in ('{}', bytearray(b'{}')):
            with self.subTest(payload=type(payload).__name__):
                with self.assertRaises(CanonError) as raised:
                    restore_json(world(), payload)
                self.assertEqual(raised.exception.code, "invalid_session_payload")
        with self.assertRaises(CanonError) as raised:
            restore_json(world(), bytes([255]))
        self.assertEqual(raised.exception.code, "invalid_json")

    def test_source_change_invalidates_receipt(self):
        source = world()
        payload = export_json(source, [])
        modified = json.loads(json.dumps(source))
        modified["prompt"] = "A changed world begins."
        with self.assertRaises(CanonError) as raised:
            restore_json(modified, payload)
        self.assertEqual(raised.exception.code, "session_stale_source")

    def test_state_tamper_invalidates_receipt(self):
        source = world()
        receipt = json.loads(export_json(source, []).decode("utf-8"))
        receipt["ended"] = True
        with self.assertRaises(CanonError) as raised:
            restore_json(source, json.dumps(receipt).encode("utf-8"))
        self.assertEqual(raised.exception.code, "session_state_mismatch")


if __name__ == "__main__":
    unittest.main()
