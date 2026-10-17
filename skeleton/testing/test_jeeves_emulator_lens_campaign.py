"""Synthetic-only multi-page lens campaign contract; not native ROM proof."""
from __future__ import annotations

import copy
import unittest

from skeleton.jeeves.game_emulator_lens_review import (
    review_verified_training_report,
)
from skeleton.jeeves.game_emulator_lens_campaign import (
    LensCampaignError, assemble_source_pinned_lens_campaign,
    audit_lens_campaign,
)
from skeleton.testing.test_jeeves_emulator_full_lens_review import _synthetic_report


def _pages(page_size: int = 37) -> list[dict]:
    report = _synthetic_report()
    pages = []
    offset = 0
    while True:
        page = review_verified_training_report(report, offset=offset, limit=page_size)
        pages.append(page)
        if page["next_offset"] is None:
            return pages
        offset = page["next_offset"]


class LensCampaignContract(unittest.TestCase):
    def test_exact_catalog_coverage_is_read_only_and_source_bound(self):
        pages = _pages()
        audit = audit_lens_campaign(pages)
        self.assertEqual(audit["lens_count"], pages[0]["catalog_lens_count"])
        self.assertEqual(audit["page_count"], len(pages))
        self.assertTrue(audit["full_registered_catalog_covered"])
        self.assertFalse(audit["model_weights_updated"])
        self.assertFalse(audit["production_model_promotion_authorized"])
        self.assertFalse(audit["independent_native_replay_verified"])
        self.assertEqual(audit, audit_lens_campaign(copy.deepcopy(pages)))

    def test_source_reconstruction_rejects_rehashed_synthetic_review_claims(self):
        report = _synthetic_report()
        pages = _pages()
        verified = audit_lens_campaign(pages, source_report=report)
        self.assertTrue(verified["all_review_pages_reconstructed_from_source"])
        self.assertFalse(verified["independent_native_replay_verified"])
        forged = copy.deepcopy(pages)
        forged[0]["reviews"][0]["jeeves_playback"]["task"] = "invented result"
        from skeleton.jeeves.game_learning import _digest
        forged[0]["review_digest"] = _digest({
            key: value for key, value in forged[0].items()
            if key != "review_digest"
        })
        # Self-consistent rehashing is not source authenticity.
        with self.assertRaises(LensCampaignError):
            audit_lens_campaign(forged, source_report=report)
        forged[0]["source_report_digest"] = "a" * 64
        forged[0]["review_digest"] = _digest({
            key: value for key, value in forged[0].items()
            if key != "review_digest"
        })
        with self.assertRaises(LensCampaignError):
            audit_lens_campaign(forged, source_report=report)

    def test_full_campaign_assembles_all_lenses_for_varied_page_sizes(self):
        report = _synthetic_report()
        for size in (1, 17, 37, 64, 256, 512):
            with self.subTest(page_size=size):
                assembled = assemble_source_pinned_lens_campaign(
                    report, page_size=size,
                )
                self.assertTrue(assembled["full_registered_catalog_covered"])
                self.assertTrue(assembled["all_review_pages_reconstructed_from_source"])
                self.assertEqual(
                    assembled["lens_count"], _pages()[0]["catalog_lens_count"],
                )
                self.assertFalse(assembled["production_model_promotion_authorized"])
        for invalid in (0, -1, 513, True, 2.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(LensCampaignError):
                    assemble_source_pinned_lens_campaign(report, page_size=invalid)

    def test_missing_reordered_or_duplicate_page_rejected(self):
        pages = _pages()
        for bad in (pages[:-1], pages[1:], pages[:1] + pages[:1] + pages[1:],
                    list(reversed(pages))):
            with self.subTest(size=len(bad)):
                with self.assertRaises(LensCampaignError):
                    audit_lens_campaign(bad)

    def test_tamper_and_fake_independent_review_rejected(self):
        pages = _pages()
        for change in ("digest", "lens", "promotion", "dragon", "pagination"):
            bad = copy.deepcopy(pages)
            if change == "digest":
                bad[0]["review_digest"] = "0" * 64
            elif change == "lens":
                bad[0]["reviews"][0]["lens_key"] = "invented"
            elif change == "promotion":
                bad[0]["production_model_promotion_authorized"] = True
            elif change == "dragon":
                bad[0]["reviews"][0]["dragon_observation"]["status"] = "complete"
            else:
                bad[0]["next_offset"] = None
            with self.subTest(change=change):
                with self.assertRaises(LensCampaignError):
                    audit_lens_campaign(bad)

    def test_bounded_input_contract(self):
        with self.assertRaises(LensCampaignError):
            audit_lens_campaign([])
        with self.assertRaises(LensCampaignError):
            audit_lens_campaign([{}] * 129)


if __name__ == "__main__":
    unittest.main()
