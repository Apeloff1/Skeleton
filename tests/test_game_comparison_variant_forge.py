"""Contract checks for original comparative game variants; no ROM/core is executed."""

from __future__ import annotations

import unittest

from skeleton.jeeves.game_comparison_schema import digest
from skeleton.jeeves.game_comparison_variant_forge import (
    ComparativeVariantError,
    forge_original_comparison_variants,
)


def _report() -> dict:
    games={}
    for index in range(2):
        identity=f"test_game_{index}"
        games[identity]={
            "id":identity,
            "status":"actual_native_observations_captured",
            "source_sha256":digest({"synthetic_fixture_game":identity}),
            "phases":{
                phase:{
                    "source":"actual_isolated_libretro",
                    "evidence_sha256":digest({"fixture":identity,"phase":phase}),
                } for phase in ("earlier","middle","after")
            },
        }
    report={
        "schema_version":"skeleton.game.comparative_study_result.v1",
        "study_id":"fixture_only",
        "games":games,
        "observer_notes":[],
    }
    report["result_sha256"]=digest(report)
    return report


class ComparativeVariantForgeContracts(unittest.TestCase):
    def test_three_original_projects_and_ordered_evidence(self) -> None:
        result=forge_original_comparison_variants(
            _report(),game_ids=["test_game_0","test_game_1"],
            target_id="nes",project_prefix="test_comparison",author_seed=15,
        )
        self.assertEqual(result["new_original_scene_variations"],3)
        self.assertEqual([v["design_era"] for v in result["authored_variants"]],["earlier","middle","after"])
        self.assertEqual(len({v["original_project_sha256"] for v in result["authored_variants"]}),3)
        for variant in result["authored_variants"]:
            self.assertTrue(variant["validation"]["valid"])
            self.assertTrue(variant["project_files"])
            self.assertEqual(len(variant["source_game_evidence"]),2)
            self.assertFalse(variant["source_game_evidence"][0]["source_content_reused"])
            self.assertFalse(variant["rendered_or_compiled_into_native_rom"])

    def test_tampered_source_evidence_rejected(self) -> None:
        report=_report()
        report["games"]["test_game_0"]["source_sha256"]="0"*64
        with self.assertRaises(ComparativeVariantError):
            forge_original_comparison_variants(
                report,game_ids=["test_game_0","test_game_1"],target_id="nes"
            )

    def test_duplicate_game_ref_rejected(self) -> None:
        with self.assertRaises(ComparativeVariantError):
            forge_original_comparison_variants(
                _report(),game_ids=["test_game_0","test_game_0"],target_id="nes"
            )

    def test_unsupported_target_rejected(self) -> None:
        with self.assertRaises((ComparativeVariantError,ValueError)):
            forge_original_comparison_variants(
                _report(),game_ids=["test_game_0","test_game_1"],
                target_id="this_is_not_a_console"
            )


if __name__=="__main__":
    unittest.main()
