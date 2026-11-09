"""Exact replay curriculum and operator-pinned candidate trainer contract."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.training.jeeves_studio_curriculum import (
    StudioCurriculumError, build_studio_curriculum,
    verify_studio_curriculum, load_studio_curriculum, publish_corpus,
)
from skeleton.ai.training.jeeves_production_game_train import (
    ProductionCheckpointError,train,
)
from skeleton.jeeves.game_studio_environment import make_studio_source

class StudioCurriculumTests(unittest.TestCase):
    def test_gameplay_produces_real_replay_verified_training_examples(self):
        source=make_studio_source("economy",actions=("inspect","survey","wait"))
        corpus=build_studio_curriculum(
            source,[{"seed":8,"actions":["inspect","survey","wait"]}],
            authorized=True,rights_cleared=True,
        )
        examples=verify_studio_curriculum(corpus)
        self.assertEqual(len(examples),3)
        self.assertIn("Original playable engine economy",examples[0])
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/"training.json"
            expected=publish_corpus(file,corpus)
            self.assertEqual(sha256(file.read_bytes()).hexdigest(),expected)
            actual,pinned=load_studio_curriculum(file,expected_sha256=expected)
            self.assertEqual(actual,examples)
            self.assertEqual(pinned,expected)
            with self.assertRaises(StudioCurriculumError):
                load_studio_curriculum(file,expected_sha256="0"*64)
        altered=deepcopy(corpus)
        altered["episodes"][0]["terminal_digest"]="0"*64
        with self.assertRaises(StudioCurriculumError):
            verify_studio_curriculum(altered)

    def test_unadmitted_and_duplicate_worlds_do_not_train(self):
        source=make_studio_source("narrative",actions=("inspect","review"))
        with self.assertRaises(PermissionError):
            build_studio_curriculum(source,[{"seed":1,"actions":["inspect"]}],
                                    authorized=True,rights_cleared=False)
        with self.assertRaises(StudioCurriculumError):
            build_studio_curriculum(source,[
                {"seed":1,"actions":["inspect"]},{"seed":1,"actions":["review"]}],
                authorized=True,rights_cleared=True)

    def test_unpinned_corpus_rejected_before_real_model_load(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            with self.assertRaises(ProductionCheckpointError):
                train(None,expected="0"*64,candidate=base/"candidate.json",
                      report=base/"report.json",epochs=1,lr=0.005,
                      min_coverage=0.8,max_domain_regression=0.0,
                      studio_corpus=base/"source.json")

if __name__=="__main__":
    unittest.main()
