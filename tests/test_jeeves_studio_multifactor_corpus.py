"""Replay-verified multi-factor neural input never claims live weight changes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_studio_multifactor import execute_multifactor_scenarios
from skeleton.ai.training.jeeves_studio_multifactor_corpus import (
    build_multifactor_training_corpus,
    verify_multifactor_training_corpus,
    publish_multifactor_training_corpus,
)
from skeleton.ai.training.jeeves_studio_curriculum import (
    StudioCurriculumError,load_studio_curriculum,
)


class NeuralFactorCorpusTests(unittest.TestCase):
    def setUp(self):
        self.source=make_studio_source(
            "economy",{"market_nodes":3,"goods":10},
            actions=("inspect","wait","survey","buy:1","sell:1"),
        )

    def test_finite_gameplay_replay_is_independent_neural_candidate_input(self):
        measured=execute_multifactor_scenarios(
            self.source,max_scenarios=2,steps=2,seed=4,
            train=True,authorized=True,rights_cleared=True,
        )
        entries=[]
        for row in measured["experiments"]:
            first=row["actual_weight_training"]["training_episode_actions"][0]
            entries.append({"index":row["index"],"seed":first["seed"],
                            "actions":first["actions"]})
        corpus=build_multifactor_training_corpus(
            self.source,interaction_order=3,axis_offset=0,max_scenarios=2,
            recorded_training=entries,authorized=True,rights_cleared=True,
        )
        text=verify_multifactor_training_corpus(corpus)
        self.assertGreaterEqual(len(text),2)
        self.assertTrue(all("Verified multi-factor mechanics" in t for t in text))
        self.assertFalse(corpus["production_neural_weights_modified"])
        self.assertFalse(corpus["automatic_promotion"])
        with TemporaryDirectory() as folder:
            destination=Path(folder)/"new-neural-corpus.json"
            digest=publish_multifactor_training_corpus(destination,corpus)
            loaded,sha=load_studio_curriculum(
                destination,expected_sha256=digest,
            )
            self.assertEqual(loaded,text)
            self.assertEqual(sha,digest)
            self.assertEqual(
                hashlib.sha256(destination.read_bytes()).hexdigest(),digest,
            )
            with self.assertRaises(StudioCurriculumError):
                load_studio_curriculum(destination,expected_sha256="0"*64)

    def test_source_tampering_and_hidden_holdout_is_rejected(self):
        measured=execute_multifactor_scenarios(
            self.source,max_scenarios=2,steps=1,seed=3,train=False,
        )
        entries=[
            {"index":entry["index"],"seed":entry["seed"],
             "actions":[entry["scripted_actions"][0]]}
            for entry in measured["experiments"]
        ]
        doc=build_multifactor_training_corpus(
            self.source,interaction_order=3,axis_offset=0,max_scenarios=2,
            recorded_training=entries,authorized=True,rights_cleared=True,
        )
        corrupted=deepcopy(doc)
        corrupted["entries"][0]["recorded"]["episodes"][0]["examples"][0]="Invented credit for a game win"
        with self.assertRaises(StudioCurriculumError):
            verify_multifactor_training_corpus(corrupted)
        forged=deepcopy(doc)
        forged["independent_heldout_supplied"]=True
        with self.assertRaises(StudioCurriculumError):
            verify_multifactor_training_corpus(forged)
        with self.assertRaises(PermissionError):
            build_multifactor_training_corpus(
                self.source,interaction_order=3,axis_offset=0,max_scenarios=2,
                recorded_training=entries,authorized=False,rights_cleared=True,
            )


if __name__=="__main__":
    unittest.main()
