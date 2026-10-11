"""Operator model CLI, real reviewer inference and attestation-source custody."""
from __future__ import annotations

from contextlib import redirect_stdout,redirect_stderr
from dataclasses import replace
from pathlib import Path
import io
import json
import tempfile
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_learning_almanac import (
    Curriculum,quarantine_curriculum,
)
from skeleton.ai.game_builder.game_model_cli import main as model_cli
from skeleton.ai.game_builder.game_reviewer_registry import (
    ReviewerRegistry,ROLES,
)
from skeleton.ai.game_builder.game_model_promotion import PromotionError
from skeleton.ai.game_builder.quest_scene_forge import forge_director

from tests.test_game_builder_reviewer_promotion import promotion_corpus


class RealModelOperatorCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"ai_studio"
        GameWorkspace.create(self.root,authorized=True)
        self.registry=ReviewerRegistry(self.root)

    def cmd(self,*args,expected=0):
        stdout=io.StringIO()
        with redirect_stdout(stdout),redirect_stderr(io.StringIO()):
            result=model_cli((str(args[0]),"--root",str(self.root),*args[1:]))
        self.assertEqual(result,expected,
                         f"model CLI {args[0]} unexpectedly returned {result}")
        return json.loads(stdout.getvalue()) if result==0 else None

    def _populate_real_quarantine(self):
        for batch in promotion_corpus():
            hostile=sum(x.expected["decision"]=="reject" for x in batch.examples)
            source=Curriculum(batch.source_project,batch.examples[0].split,
                              batch.original_almanac,batch.examples,
                              hostile,len(batch.examples)-hostile)
            quarantine_curriculum(source,self.root,authorized=True)

    def test_cli_evaluation_stage_shadow_usage_idle_activation_inference(self):
        self._populate_real_quarantine()
        # The deliberately simplistic unit-test classifier is known to
        # exploit the attack_family metadata. Default production rigor must
        # reject it; only an explicit advisory-only lab setting permits
        # testing the lifecycle and emergency rollback behavior.
        strict=self.cmd("evaluate","--trusted-local-operator")
        self.assertFalse(strict["evaluation"]["passed"])
        self.assertIn("validation:reviewer_shortcut_detection",
                      strict["evaluation"]["blockers"])
        tested=self.cmd("evaluate","--trusted-local-operator",
                        "--minimum-counterfactual-accuracy","0")
        self.assertTrue(tested["evaluation"]["passed"])
        self.assertFalse(tested["core_ai_model_changed"])
        staged=self.cmd("stage","--trusted-local-operator",
                        "--minimum-counterfactual-accuracy","0")
        self.assertEqual(staged["status"],"staged")
        self.assertEqual(self.cmd("status")["phase"],"staged")
        state=self.registry.read_state()
        doc=self.registry._candidate(state["candidate"])
        review=(
            [dict(role=role,reviewer_id=f"human_{i:02d}_reviewer",
                  candidate_digest=state["candidate"],
                  evaluation_digest=canonical_digest(doc["evaluation"]),
                  note=f"Independent original game {role} contract reviewed.",
                  approved=True)
             for i,role in enumerate(ROLES)]
        )
        approvals=Path(self.temp.name)/"individual-reviewers.json"
        approvals.write_text(json.dumps(review),encoding="utf-8")
        shadow=self.cmd("approve","--trusted-local-operator",
                        "--reviewers-file",str(approvals))
        self.assertEqual(shadow["status"],"shadow")
        all_worlds=[]
        for mode in ("usage","idle"):
            worlds=[]
            for n in range(2):
                game=forge_director(
                    f"fresh_original_{mode}_{n}",seed=86400+
                    (n if mode=="usage" else n+40),
                    regions=tuple(f"district_{j:02d}" for j in range(8)),
                    quest_types=("main_story","investigation","rival_story"),
                    stages=2,
                )
                file=Path(self.temp.name)/(f"{mode}_{n}.json")
                file.write_text(json.dumps(game.payload()),encoding="utf-8")
                worlds.append(file)
                all_worlds.append(game)
            mode_name="idle-pass" if mode=="idle" else "usage"
            result=self.cmd(mode_name,"--trusted-local-operator",
                            "--director-blueprints",*(str(x) for x in worlds))
            self.assertEqual(result["status"],"shadow")
            self.assertTrue(result["cohort"]["passed"],
                            str(result["cohort"]["blockers"]))
        activated=self.cmd("activate","--trusted-local-operator")
        self.assertEqual(activated["status"],"active")
        self.assertEqual(self.cmd("status")["phase"],"active")
        evidence=Path(self.temp.name)/"new-source.json"
        evidence.write_text(json.dumps({
            "attack_family":"unknown_cinematic_state_forgery",
            "source_campaign_digest":all_worlds[0].digest,
        }),encoding="utf-8")
        prediction=self.cmd("predict","--trusted-local-operator",
                            "--game-digest",all_worlds[0].digest,
                            "--evidence-file",str(evidence))
        self.assertEqual(prediction["active_model_digest"],activated["active"])
        self.assertTrue(prediction["canon_replay_required"])
        self.assertFalse(prediction["publication_approved"])
        self.assertTrue(prediction["prediction"]["advisory_only"])
        rollback=self.cmd("rollback","--trusted-local-operator",
                          "--reason","Local reviewer policy requires emergency rollback.")
        self.assertEqual(rollback["status"],"rolled_back")
        self.assertIsNone(rollback["active"])
        self.cmd("predict","--trusted-local-operator",
                 "--game-digest",all_worlds[0].digest,
                 "--evidence-file",str(evidence),expected=2)

    def test_reviewer_source_metadata_tampering_blocks_all_future_promotions(self):
        self._populate_real_quarantine()
        stage=self.cmd("stage","--trusted-local-operator")
        file=self.registry.root/"candidates"/(stage["candidate"]+".json")
        record=json.loads(file.read_text())
        record["evaluation"]["passed"]=False
        file.write_text(json.dumps(record),encoding="utf-8")
        with self.assertRaises(PromotionError):
            self.registry.read_state()
        self.cmd("status",expected=2)
        self.cmd("approve","--trusted-local-operator",
                 "--reviewers-file",str(file),expected=2)

    def test_unreviewed_operator_cannot_promote_or_run_idle_models(self):
        self.cmd("stage",expected=2)
        self.cmd("usage","--director-blueprints","one.json","two.json",expected=2)
        self.cmd("idle-pass","--director-blueprints","one.json","two.json",expected=2)
        self.cmd("activate",expected=2)
        self.assertEqual(self.cmd("status")["phase"],"idle")


if __name__=="__main__":
    unittest.main()
