"""Portable browser session contract matches the canonical Python replay schema."""
from __future__ import annotations

import json
import re
import unittest

from skeleton.jeeves.worlds.world_canon import compile_html, propose
from skeleton.jeeves.worlds.world_session import replay, restore


def sample():
    return propose(
        world_id="portable", premise="A signal appears in the valley.",
        protagonist="Mira", region="Cinder Vale", goal="Follow the signal."
    )


class PlayableSessionContractTests(unittest.TestCase):
    def test_html_exposes_portable_session_controls(self):
        page = compile_html(sample())
        self.assertIn("Export session", page)
        self.assertIn("Restore session", page)
        self.assertIn("session-receipt", page)
        self.assertIn('role", "status"', page)

    def test_html_binds_receipts_to_canonical_source_digest(self):
        world = sample()
        page = compile_html(world)
        receipt = replay(world, ["pursue_goal"])
        self.assertIn(receipt["source_digest"], page)
        self.assertIn("session_stale_source", page)
        self.assertIn("session_state_mismatch", page)
        self.assertEqual(restore(world, receipt), receipt)

    def test_html_replays_choices_instead_of_trusting_state(self):
        page = compile_html(sample())
        self.assertIn("function replayTrace(ids)", page)
        self.assertIn("choice.requires.every(f => acquired.has(f))", page)
        self.assertIn("choice.from !== scene", page)
        self.assertIn("receipt.scene !== expected.scene", page)
        self.assertIn("receipt.ended !== expected.ended", page)

    def test_html_has_bounded_restore_input_and_no_storage_side_effects(self):
        page = compile_html(sample())
        self.assertIn("new TextEncoder().encode(text).length > 65536", page)
        self.assertIn("ids.length > 512", page)
        self.assertNotIn("localStorage", page)
        self.assertNotIn("sessionStorage", page)
        self.assertNotIn("eval(", page)

    def test_session_draft_survives_rerender_and_failed_restore(self):
        page = compile_html(sample())
        self.assertIn('let receiptDraft = "";', page)
        self.assertIn('field.value = receiptDraft;', page)
        self.assertIn('receiptDraft = field.value;', page)
        self.assertIn('importReceipt(receiptDraft)', page)
        self.assertIn('receiptStatus = "Restore rejected: " + error.message;', page)
        self.assertIn('status.textContent = receiptStatus;', page)
        self.assertIn('receiptStatus = "Session restored";', page)
        self.assertIn('receiptStatus = "Session exported";', page)

    def test_restore_bounds_utf8_bytes_not_javascript_code_units(self):
        page = compile_html(sample())
        self.assertIn('new TextEncoder().encode(text).length > 65536', page)
        self.assertNotIn('text.length > 65536', page)

    def test_html_data_is_json_with_no_untrusted_executable_markup(self):
        world = sample()
        world["prompt"] = "</script><script>alert(1)</script>"
        world["scenes"][0]["narrative"] = "</script><img src=x>"
        page = compile_html(world)
        self.assertEqual(page.count("<script>"), 1)
        self.assertEqual(page.count('<script id="world-data"'), 1)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<img src=x>", page)

    def test_round_trip_receipt_is_stable_json(self):
        world = sample()
        receipt = replay(world, ["pursue_goal"])
        decoded = json.loads(json.dumps(receipt, sort_keys=True))
        self.assertEqual(restore(world, decoded), receipt)


if __name__ == "__main__":
    unittest.main()
