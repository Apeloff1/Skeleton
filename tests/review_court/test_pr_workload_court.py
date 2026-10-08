"""Fail-closed tests for the PR workload court. No network."""
from __future__ import annotations

import unittest

from skeleton.review_court.pr_workload_court import (
    MAIN_PIN,
    OBSERVED_WINDOW,
    CourtError,
    court,
    observed,
)


def _row(**overrides):
    base = {
        "number": 3537,
        "title": "fix(ai): bounded serving preflight and deterministic feedback replay fence",
        "draft": False,
        "additions": 626,
        "deletions": 21,
        "changed_files": 6,
        "head": "40b05d143605b2790bd42253e3d599b4e581ee84",
        "base": MAIN_PIN,
    }
    base.update(overrides)
    return base


class CourtLaw(unittest.TestCase):
    def test_observed_window_pins_serve_and_holds_scatter(self) -> None:
        card = observed()
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["merge_authority"], 0)
        self.assertEqual(card["parent"], "#80")
        by_number = {row["number"]: row for row in card["cards"]}
        self.assertEqual(by_number[3537]["verdict"], "eligible-after-ci")
        self.assertEqual(by_number[3535]["verdict"], "hold-stale-base")
        self.assertEqual(by_number[3559]["verdict"], "hold-volume")
        self.assertEqual(by_number[3560]["verdict"], "hold-volume")
        self.assertGreaterEqual(card["counts"]["hold-volume"], 8)
        self.assertEqual(len(card["digest"]), 64)

    def test_empty_window_fails_closed(self) -> None:
        with self.assertRaises(CourtError):
            court([])

    def test_duplicate_number_fails_closed(self) -> None:
        with self.assertRaises(CourtError):
            court([_row(), _row()])

    def test_bad_sha_fails_closed(self) -> None:
        with self.assertRaises(CourtError):
            court([_row(head="deadbeef")])

    def test_bool_is_not_an_int_count(self) -> None:
        with self.assertRaises(CourtError):
            court([_row(additions=True)])

    def test_volume_title_cannot_become_eligible_by_clearing_draft(self) -> None:
        card = court([_row(
            number=3559,
            title="feat: scatter 10240 organs across 16 thin volumes (SCAT-10240)",
            draft=False,
            additions=10,
            changed_files=1,
        )])
        self.assertEqual(card["cards"][0]["verdict"], "hold-volume")

    def test_stale_base_blocks_tokenizer_lane(self) -> None:
        card = court([_row(
            number=3535,
            title="fix(ai): validate tokenizer checkpoints and release streaming buffers",
            base="962bce33d61da43667f6590a9d3c903004446161",
        )])
        self.assertEqual(card["cards"][0]["verdict"], "hold-stale-base")
        self.assertFalse(card["cards"][0]["base_matches_pin"])

    def test_window_cap(self) -> None:
        rows = [_row(number=i + 1, head=f"{i+1:040x}") for i in range(65)]
        with self.assertRaises(CourtError):
            court(rows)

    def test_observed_digest_is_stable(self) -> None:
        self.assertEqual(observed()["digest"], observed()["digest"])
        self.assertEqual(len(OBSERVED_WINDOW), 12)


if __name__ == "__main__":
    unittest.main()
