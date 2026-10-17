"""Classify real stage blockers without persisting arbitrary log or secret text."""
from __future__ import annotations

import unittest

from skeleton.ai.game_builder.studio_production_blocker_taxonomy import (
    classify_production_blockers,
)


def blocked(target, stage, reason):
    return {
        "target": target, "stage": stage, "status": "blocked",
        "blocker": reason,
    }


class StudioProductionBlockerClassificationTests(unittest.TestCase):
    def test_distinct_compiler_asset_emulator_and_runtime_causes(self):
        events = [
            blocked("nintendo_game_boy", "rom", "toolchain_missing:rgbasm"),
            blocked("nintendo_game_boy", "rom", "compiled_handheld_original_art_mismatch"),
            blocked("nintendo_famicom", "rom", "compiled_nes_chr_original_art_mismatch"),
            blocked("nintendo_game_boy", "rom", "compiled_original_psg_music_mismatch"),
            blocked("nintendo_famicom", "emulator", "fceux_not_installed"),
            blocked("nintendo_game_boy", "emulator", "pyboy_not_installed"),
            blocked("nintendo_famicom", "browser", "javascript_playthrough_not_qualified"),
            blocked("nintendo_famicom", "godot", "godot_playthrough_not_qualified"),
            blocked("nintendo_famicom", "emulator", "nes_cpu_intermediate_checkpoint_mismatch"),
        ]
        result = classify_production_blockers(events)
        self.assertEqual(result["classified_blockers"], len(events))
        self.assertEqual(
            [row["category"] for row in result["findings"]],
            ["compiler_unavailable", "compiled_sprite_mismatch",
             "compiled_sprite_mismatch", "compiled_audio_mismatch",
             "nes_emulator_unavailable",
             "gameboy_emulator_unavailable", "browser_evidence_missing",
             "godot_evidence_missing", "controller_or_gameplay_divergence"],
        )
        self.assertTrue(all(row["operator_reproduction_required"] for row in result["findings"]))
        self.assertTrue(all(not row["automatic_retry_authorized"] for row in result["findings"]))
        self.assertFalse(result["trained_model_weights"])
        self.assertFalse(result["almanac_knowledge_promoted"])
        self.assertEqual(len(result["classification_digest"]), 64)

    def test_raw_exception_text_is_never_promoted_into_permanent_history(self):
        sensitive = "execution_exception:Password_is_not_an_allowed_source"
        result = classify_production_blockers([
            blocked("nintendo_game_boy", "rom", sensitive),
            blocked("nintendo_game_boy", "rom", sensitive),
        ])
        self.assertEqual(result["classified_blockers"], 1)
        self.assertEqual(result["findings"][0]["category"], "execution_exception")
        self.assertNotIn("Password", repr(result))
        self.assertEqual(result["omitted_after_limit"], 0)

    def test_source_bound_retries_are_deduplicated_and_bounded(self):
        events = [blocked("nintendo_game_boy", "rom", "toolchain_missing:rgbasm")]
        events += [
            blocked(f"target{i}", "source", "source_not_yet_generated")
            for i in range(20)
        ]
        result = classify_production_blockers(events, limit=5)
        self.assertEqual(result["classified_blockers"], 5)
        self.assertEqual(result["omitted_after_limit"], 16)
        self.assertFalse(result["findings"][0]["original_source_modified"])

    def test_invalid_stage_event_or_unbounded_text_fails_closed(self):
        for bad in (
            [blocked("gb", "unregistered", "missing")],
            [blocked("gb", "rom", "")],
            [blocked("gb", "rom", "x" * 257)],
            [{"target": "gb", "stage": "rom", "status": "made_up",
              "blocker": "missing"}],
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                classify_production_blockers(bad)


if __name__ == "__main__":
    unittest.main()
