"""Real emulator snapshot audit accepts only exact source-bound state progress."""
from __future__ import annotations

import unittest

from skeleton.ai.game_builder.studio_native_replay_telemetry import (
    NativeCheckpointError, FIELDS, selected_checkpoints, make_checkpoint,
    first_cpu_divergence,
    validate_checkpoints, parse_nes_samples,
)


def cpu(*, level=0, x=1, y=2, health=4, score=0, turns=0, gems=2, won=0):
    return {
        "Level": level, "PlayerX": x, "PlayerY": y,
        "Health": health, "Score": score % 256,
        "ScoreHigh": score // 256,
        "TurnCount": turns & 255, "TurnCountHigh": turns >> 8,
        "GemsRemaining": gems, "GameWon": won, "GameLost": 0,
    }


class NativeReplayCheckpointTests(unittest.TestCase):
    def check(self, rows, *, actions=3, score=310):
        return validate_checkpoints(
            rows, actions=actions, source_world="a" * 64,
            source_proof="b" * 64,
            expected_final={
                "level_index": 0, "x": 5, "y": 4, "health": 4,
                "score": score,
            },
        )

    def test_bounded_samples_cover_original_full_run(self):
        for count in (1, 2, 64, 127, 128, 129, 20_000):
            checkpoints = selected_checkpoints(count)
            self.assertEqual(checkpoints[0], 1 if count > 1 else count)
            self.assertEqual(checkpoints[-1], count)
            self.assertEqual(len(checkpoints), min(count, 128))
            self.assertEqual(tuple(sorted(set(checkpoints))), checkpoints)
        with self.assertRaises(NativeCheckpointError):
            selected_checkpoints(20_001)

    def test_machine_code_full_score_high_byte_is_admitted(self):
        rows = [
            make_checkpoint(1, cpu(turns=1, x=2, score=10)),
            make_checkpoint(2, cpu(turns=2, x=3, score=20, gems=1)),
            make_checkpoint(3, cpu(turns=3, level=1, x=5, y=4,
                                   score=310, gems=0, won=1)),
        ]
        report = self.check(rows)
        self.assertEqual(report["sampled_boundaries"], 3)
        self.assertEqual(report["last_observed_action"], 3)
        self.assertFalse(report["physical_controller_verified"])
        self.assertFalse(report["checkpoint_weight_training_done"])
        self.assertEqual(len(report["checkpoint_digest"]), 64)

    def test_diagnostics_identify_only_first_actual_wrong_cpu_field(self):
        reference = [make_checkpoint(1, cpu(turns=1, x=2, score=10))]
        wrong = [make_checkpoint(1, cpu(turns=1, x=3, score=20))]
        diagnostic = first_cpu_divergence(wrong, reference)
        self.assertEqual(diagnostic["category"], "cpu_state_diverged")
        self.assertEqual(diagnostic["action"], 1)
        self.assertEqual(diagnostic["changed_fields"], ["PlayerX", "Score"])
        self.assertEqual(diagnostic["expected"], {"PlayerX": 2, "Score": 10})
        self.assertEqual(diagnostic["observed"], {"PlayerX": 3, "Score": 20})
        self.assertIsNone(first_cpu_divergence(reference, reference))
        self.assertEqual(
            first_cpu_divergence([], reference)["category"],
            "sample_count_mismatch",
        )

    def test_wrong_state_action_healing_score_regress_or_premature_win_fail(self):
        valid = [
            make_checkpoint(1, cpu(turns=1, x=2, score=10)),
            make_checkpoint(2, cpu(turns=2, x=3, score=20)),
            make_checkpoint(3, cpu(turns=3, level=1, x=5, y=4,
                                   score=310, gems=0, won=1)),
        ]
        cases = []
        for idx, alteration in (
            (0, {"GameWon": 1}),
            (1, {"Score": 1}),
            (1, {"Level": 3}),
            (2, {"GameLost": 1}),
            (2, {"GemsRemaining": 1}),
        ):
            changed = [dict(x) for x in valid]
            changed[idx]["state"] = {**changed[idx]["state"], **alteration}
            cases.append(changed)
        cases.append(valid[:-1])
        cases.append([valid[1], valid[0], valid[2]])
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(NativeCheckpointError):
                self.check(rows)

    def test_parse_exact_nes_cpu_samples_with_no_code_execution(self):
        original = (
            "1 0 2 2 4 10 0 1 0 2 0 0" + chr(10)
            + "2 0 3 2 4 20 0 2 0 1 0 0" + chr(10)
            + "3 1 5 4 4 54 1 3 0 0 1 0" + chr(10)
        ).encode("ascii")
        parsed = parse_nes_samples(original, 3)
        self.assertEqual(parsed[-1]["state"]["ScoreHigh"], 1)
        self.check(parsed)
        for bad in (
            original.replace(b"3 1 5", b"3 8 5"),
            original[:-2],
            original + b"4 1 5 4 4 54 1 4 0 0 1 0\n",
            original.replace(b"3 0 0 1 0", b"evil()"),
        ):
            with self.subTest(bad=bad), self.assertRaises(NativeCheckpointError):
                parsed = parse_nes_samples(bad, 3)
                self.check(parsed)


if __name__ == "__main__":
    unittest.main()
