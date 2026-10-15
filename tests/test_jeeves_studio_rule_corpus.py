"""Rule-variant gameplay corpus must be replayed, pinned and trainer-admissible."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.training.jeeves_studio_curriculum import (
    StudioCurriculumError, load_studio_curriculum,
)
from skeleton.ai.training.jeeves_studio_rule_corpus import (
    RULE_CORPUS_SCHEMA, build_rule_training_corpus,
    verify_rule_training_corpus, publish_rule_training_corpus,
)
from skeleton.jeeves.game_studio_environment import make_studio_source
from skeleton.jeeves.game_studio_rule_curriculum import (
    PROPOSAL_SCHEMA, make_rule_curriculum,
)
from skeleton.jeeves.game_studio_rule_training_cli import train_rule_curriculum


def fingerprint(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode()).hexdigest()


class RuleNeuralCorpusTests(unittest.TestCase):
    def setUp(self):
        self.source = make_studio_source("economy", {"market_nodes": 2, "goods": 10},
                                         actions=("inspect", "wait", "survey"))
        proposal = {
            "schema_version": PROPOSAL_SCHEMA, "proposal_id": "inflation-hard",
            "base_digest": fingerprint(self.source),
            "reason": "Raise market elasticity to study a difficult scarcity economy.",
            "scene_seed": None,
            "operations": [{
                "scope":"settings", "path":"price_elasticity",
                "op":"add", "value":4,
            }],
        }
        self.proposals = [proposal]
        self.plan = make_rule_curriculum(self.source,self.proposals,max_steps=4)

    def test_both_conditions_create_replay_verified_neural_inputs(self):
        entries = [
            {"scenario_id":"baseline","seed":0,"actions":["inspect","survey"]},
            {"scenario_id":"inflation-hard","seed":1,"actions":["survey","wait"]},
        ]
        doc=build_rule_training_corpus(
            self.plan,entries,authorized=True,rights_cleared=True,
        )
        self.assertEqual(doc["schema_version"],RULE_CORPUS_SCHEMA)
        verified=verify_rule_training_corpus(doc)
        self.assertEqual(len(verified),4)
        self.assertTrue(all("Original game training circumstance" in row
                            for row in verified))
        self.assertTrue(any("inflation-hard" in row for row in verified))
        self.assertTrue(any("baseline" in row for row in verified))
        with TemporaryDirectory() as folder:
            p=Path(folder)/"replay.json"
            sha=publish_rule_training_corpus(p,doc)
            labels, pinned=load_studio_curriculum(p,expected_sha256=sha)
            self.assertEqual(labels,verified)
            self.assertEqual(pinned,sha)
            with self.assertRaises(StudioCurriculumError):
                load_studio_curriculum(p,expected_sha256="0"*64)

    def test_forged_rewards_or_missing_conditions_are_rejected(self):
        entries=[
            {"scenario_id":"baseline","seed":0,"actions":["inspect"]},
            {"scenario_id":"inflation-hard","seed":1,"actions":["survey"]},
        ]
        doc=build_rule_training_corpus(
            self.plan,entries,authorized=True,rights_cleared=True,
        )
        tampered=deepcopy(doc)
        tampered["episodes"][1]["recorded"]["episodes"][0]["examples"][0]="I win"
        with self.assertRaises(StudioCurriculumError):
            verify_rule_training_corpus(tampered)
        with self.assertRaises(StudioCurriculumError):
            build_rule_training_corpus(
                self.plan,entries[:1],authorized=True,rights_cleared=True,
            )
        with self.assertRaises(StudioCurriculumError):
            build_rule_training_corpus(
                self.plan,
                [{"scenario_id":"baseline","seed":1,"actions":["inspect"]},
                 {"scenario_id":"inflation-hard","seed":0,"actions":["inspect"]}],
                authorized=True,rights_cleared=True,
            )

    def test_actual_q_gameplay_exposes_independently_replayed_neural_corpus(self):
        with TemporaryDirectory() as folder:
            base=Path(folder)
            policy=base/"rule-policy.json"
            corpus=base/"neural-rules.json"
            report=train_rule_curriculum(
                base_source=self.source, proposals=self.proposals,
                output=policy,neural_corpus_output=corpus,
                authorized=True,rights_cleared=True,
                episodes_per_scenario=1,max_steps=3,seed=5,
            )
            self.assertGreater(report["actual_q_updates"],0)
            self.assertTrue(policy.is_file())
            self.assertTrue(corpus.is_file())
            self.assertEqual(report["neural_corpus_sha256"],
                             hashlib.sha256(corpus.read_bytes()).hexdigest())
            checked, _=load_studio_curriculum(
                corpus,expected_sha256=report["neural_corpus_sha256"],
            )
            self.assertGreaterEqual(len(checked),2)
            self.assertFalse(json.loads(policy.read_text())[
                "production_neural_weights_modified"])
            self.assertEqual(len(json.loads(corpus.read_text())["episodes"]),2)


if __name__=="__main__":
    unittest.main()
