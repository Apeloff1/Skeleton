"""Stop-delimiter invariants for the learned NumPy recurrent backend."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.inference.neural import _stop_suffix_start


class NeuralStopBoundaryTests(unittest.TestCase):
    def test_suffix_stop_is_removed_from_published_prefix(self) -> None:
        text = "hello<END>"
        cut = _stop_suffix_start(text, ("<END>",))
        self.assertEqual(text[:cut], "hello")

    def test_overlapping_markers_choose_longest_matched_suffix(self) -> None:
        text = "reply<END>"
        self.assertEqual(_stop_suffix_start(text, ("END>", "<END>")), 5)

    def test_unmatched_markers_do_not_truncate(self) -> None:
        self.assertIsNone(_stop_suffix_start("complete", ("<END>",)))

    def test_unicode_suffix_offsets_are_character_aligned(self) -> None:
        self.assertEqual(_stop_suffix_start("hello 🌍", ("🌍",)), 6)

    def test_empty_stops_do_not_match(self) -> None:
        self.assertIsNone(_stop_suffix_start("text", ("",)))


if __name__ == "__main__":
    unittest.main()
