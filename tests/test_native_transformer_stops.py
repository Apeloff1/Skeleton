"""Regression coverage for the owned transformer stop-string boundary.

These checks do not pretend to prove model quality or load a checkpoint.
"""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.inference.native_transformer import NativeTransformerModel


class NativeTransformerStopTests(unittest.TestCase):
    def test_earliest_text_occurrence_wins_over_marker_priority(self) -> None:
        text = "answer<EARLY>unused<LATE>"
        self.assertEqual(
            NativeTransformerModel._first_stop_index(text, ("<LATE>", "<EARLY>")),
            text.index("<EARLY>"),
        )

    def test_stop_at_offset_zero(self) -> None:
        self.assertEqual(NativeTransformerModel._first_stop_index("STOPanswer", ("STOP",)), 0)

    def test_no_match_retains_entire_response(self) -> None:
        self.assertIsNone(NativeTransformerModel._first_stop_index("answer", ("<eos>",)))

    def test_empty_stop_collection(self) -> None:
        self.assertIsNone(NativeTransformerModel._first_stop_index("answer", ()))

    def test_unicode_stop_boundary(self) -> None:
        self.assertEqual(
            NativeTransformerModel._first_stop_index("hello🌍END", ("END", "🌍")),
            5,
        )

    def test_empty_marker_does_not_cut_every_response(self) -> None:
        self.assertIsNone(NativeTransformerModel._first_stop_index("answer", ("",)))


if __name__ == "__main__":
    unittest.main()
