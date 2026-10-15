"""Ten independently audited mirror runs can prioritize actual local Q updates."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_studio_scenario_lab import (
    ANGLES, mirrored_simulations,
)
from skeleton.jeeves.game_studio_multispectral_training import (
    MirrorTrainingError, measured_training_priority, train_ten_run_multispectral,
)


class VerifiedMultispectralTrainerTests(unittest.TestCase):
    def setUp(self):
        self.source=make_studio_source(
            "economy",{"market_nodes":2,"goods":10},
            actions=("inspect","survey","wait","buy:1"),
        )

    def test_measured_priority_cannot_accept_unverified_run(self):
        source=mirrored_simulations(
            self.source,seed=1,steps=2,
            angles=("explore","temporal"),workers=2,
        )
        row=source["lanes"][0]
        observed=measured_training_priority(row)
        self.assertFalse(observed["real_td_error_measured"])
        self.assertEqual(observed["seed"],row["seed"])
        self.assertEqual(observed["source_digest"],row["source_digest"])
        row["multispectral"]["passed_count"]=9
        with self.assertRaises(MirrorTrainingError):
            measured_training_priority(row)

    def test_ten_actual_q_episodes_from_ten_source_verified_mirrors(self):
        with TemporaryDirectory() as path:
            candidate=Path(path)/"candidate.json"
            with self.assertRaises(PermissionError):
                train_ten_run_multispectral(
                    source=self.source,output=candidate,
                    authorized=False,rights_cleared=True,
                    max_steps=2,
                )
            self.assertFalse(candidate.exists())
            report=train_ten_run_multispectral(
                source=self.source,output=candidate,
                authorized=True,rights_cleared=True,
                seed=13,max_steps=2,
            )
            doc=json.loads(candidate.read_text())
            self.assertEqual(report["audited_mirror_runs"],10)
            self.assertEqual(report["audits_passed"],100)
            self.assertEqual(report["actual_q_episodes"],10)
            self.assertGreater(report["actual_q_updates"],0)
            self.assertEqual(len(doc["measured_training_priorities"]),10)
            self.assertEqual(len(doc["training_trace_digests"]),10)
            self.assertEqual(len(set(doc["actual_q_training_episode_seeds"])),10)
            self.assertEqual(len(doc["independent_heldout_seeds"]),3)
            self.assertTrue(set(doc["independent_heldout_seeds"]).isdisjoint(
                doc["actual_q_training_episode_seeds"],
            ))
            self.assertFalse(doc["automatic_promotion"])
            self.assertFalse(doc["production_neural_weights_modified"])
            self.assertFalse(doc["real_spectral_sensor_inputs"])
            with self.assertRaises(FileExistsError):
                train_ten_run_multispectral(
                    source=self.source,output=candidate,
                    authorized=True,rights_cleared=True,max_steps=2,
                )


if __name__=="__main__":
    unittest.main()
