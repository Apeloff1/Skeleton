"""30-game cross-cohort portfolio contracts using fabricated hash-chain fixtures."""
import copy
import unittest

from skeleton.jeeves.game_comparison_portfolio import (
    GameComparisonPortfolioError, combine_comparison_cohorts,
    render_comparison_portfolio_dashboard,
)
from skeleton.jeeves.game_comparison_schema import digest, validate_study
from tests.test_game_comparison_pairwise import controller


def sample_study(count=30):
    games = []
    for idx in range(count):
        name = "game_" + str(idx)
        games.append({
            "id": name, "title": name, "series_id": "synthetic_series",
            "release_order": idx + 1, "release_year": 2000 + idx,
            "series_phase": ("earlier", "middle", "after")[idx % 3],
            "target_id": "nes", "core_id": "fceumm",
            "source_path": "/approved/" + name + ".nes",
            "source_sha256": digest(["rom", name]),
            "rights_evidence_digest": digest(["operator-rights", name]),
            "actions": ["idle", "right", "a"],
            "seed": 7, "frames_per_step": 1, "controller_devices": ["joypad"],
        })
    return {
        "schema_version": "skeleton.game.comparative_study.v1",
        "study_id": "portfolio_source_contract", "title": "Constructed receipts only",
        "games": games, "pairs": [{
            "left_id": games[0]["id"], "right_id": games[1]["id"], "questions": []}],
        "notes": [], "max_active": 10,
    }


def batch_export(study, batch_index):
    model = validate_study(study)
    study_digest = digest(model)
    registry = digest(["approved-registry"])
    lanes = {}
    for game in model["games"][batch_index * 10:(batch_index + 1) * 10]:
        name = game["id"]
        content = game["source_sha256"]
        env = digest(["environment", name])
        core_sha = digest(["installed-core", name])
        first = digest([
            "skeleton.game.live_comparison.v1", study_digest, name,
            content, env, registry, "reset", 7,
        ])
        ports = [controller(1)]
        receipt = {
            "schema_version": "skeleton.game.live_native_step_receipt.v1",
            "game_id": name, "index": 1, "episode_step": 1,
            "reset_generation": 0, "input_vector_sha256": digest(ports),
            "controller_ports": ports, "action_mode": "actual_native_controller_input",
            "frame_sha256": digest(["screen", name]),
            "pcm_sha256": digest(["pcm", name]),
            "native_frame_calls": 1, "native_audio_frames": 512,
            "transition_sha256": digest(["transition", name]),
            "objective_observations": {
                "screen_mean": .2, "visual_change": .4,
                "audio_rms": .1, "step_fraction": 1 / 256,
            },
            "source_content_sha256": content,
            "core_sha256": core_sha, "previous_chain_sha256": first,
        }
        last = digest(receipt)
        receipt["receipt_sha256"] = last
        lanes[name] = {
            "game_id": name, "core_id": "fceumm", "target_id": "nes",
            "source_media_sha256": content, "core_sha256": core_sha,
            "native_environment_sha256": env, "seed": 7,
            "initial_chain_sha256": first, "final_chain_sha256": last,
            "step_count": 1, "reset_count": 0,
            "native_events": [{
                "event_kind": "native_step",
                "receipt": receipt, "receipt_sha256": last,
            }],
        }
    return {
        "schema_version": "skeleton.game.live_evidence_export.v1",
        "study_id": model["study_id"], "study_digest": study_digest,
        "registry_digest": registry,
        "batch_index": batch_index, "lanes": lanes,
    }


class PortfolioNativeCohortContracts(unittest.TestCase):
    def test_thirty_game_three_batch_four_hundred_thirty_five_pairs(self):
        study = sample_study()
        result = combine_comparison_cohorts(
            study, [batch_export(study, n) for n in range(3)])
        self.assertEqual(result["recorded_game_count"], 30)
        self.assertEqual(result["pair_count"], 435)
        self.assertEqual(result["recorded_batch_count"], 3)
        self.assertTrue(result["complete_native_cohort_coverage"])
        self.assertFalse(result["cross_batch_frames_synchronized"])
        self.assertIsNone(result["pairs"][0]["gameplay_or_emulator_fidelity_winner"])
        self.assertIn(result["portfolio_sha256"],
                      render_comparison_portfolio_dashboard(result))

    def test_missing_third_batch_not_marked_complete(self):
        study = sample_study()
        result = combine_comparison_cohorts(study, [batch_export(study, 0), batch_export(study, 1)])
        self.assertEqual(result["recorded_game_count"], 20)
        self.assertEqual(result["pair_count"], 190)
        self.assertEqual(len(result["missing_game_ids"]), 10)
        self.assertFalse(result["complete_native_cohort_coverage"])

    def test_duplicate_batch_and_cross_batch_identity_rejected(self):
        study = sample_study()
        packet = batch_export(study, 0)
        with self.assertRaises(GameComparisonPortfolioError):
            combine_comparison_cohorts(study, [packet, copy.deepcopy(packet)])
        altered = batch_export(study, 1)
        altered["registry_digest"] = "0" * 64
        with self.assertRaises(GameComparisonPortfolioError):
            combine_comparison_cohorts(study, [packet, altered])

    def test_native_core_or_seed_cannot_change_under_study(self):
        study = sample_study()
        packet = batch_export(study, 0)
        packet["lanes"]["game_0"]["core_id"] = "wrong_core"
        with self.assertRaises(GameComparisonPortfolioError):
            combine_comparison_cohorts(study, [packet])

    def test_receipt_tampering_cannot_be_merged(self):
        study = sample_study()
        packet = batch_export(study, 0)
        packet["lanes"]["game_0"]["native_events"][0]["receipt"]["frame_sha256"] = "f" * 64
        with self.assertRaises(GameComparisonPortfolioError):
            combine_comparison_cohorts(study, [packet])

    def test_changed_study_revision_cannot_reuse_old_evidence(self):
        study = sample_study()
        packet = batch_export(study, 0)
        changed = copy.deepcopy(study)
        changed["title"] = "A new study revision"
        with self.assertRaises(GameComparisonPortfolioError):
            combine_comparison_cohorts(changed, [packet])


if __name__ == "__main__":
    unittest.main()
