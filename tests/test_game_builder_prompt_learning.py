"""User-prompt AI routing, quarantined mirror training and human-approved edits."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.game_project_workspace import (
    GameWorkspace,WorkspaceError,
)
from skeleton.ai.game_builder.game_prompt_router import (
    PromptRoutingError,AXES,route_game_prompt,ingest_ai_draft,
)
from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_director_solver import solve_quest
from skeleton.ai.game_builder.npc_witness_quest_engine import observe_story
from skeleton.ai.game_builder.competitive_mirror_training import (
    run_mirror_competition, training_jsonl, split_project,
)
from skeleton.ai.game_builder.game_learning_almanac import (
    AlmanacError,ReviewDecision,build_curriculum,
    quarantine_curriculum,promote_curriculum,multi_project_index,
)
from skeleton.ai.game_builder.game_workspace_cli import main as workspace_cli


class PromptAndLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "learning_original_game",seed=7162,
            regions=tuple(f"realm_{i:02d}" for i in range(8)),
            quest_types=("main_story","investigation","regional_story"),
            stages=2,
        )
        cls.proof=solve_quest(cls.world,"quest_00",authorized=True).replay

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio=GameWorkspace.create(
            Path(self.temp.name)/"original_studio",authorized=True,
        )
        self.studio.create_project(
            "learning_game","rpg",director_json=self.world.payload(),
            authorized=True,
        )

    def test_user_prompt_routes_witness_quests_cinematics_npc_and_review(self):
        prompt=("Redesign original NPC eyewitness memories so their witnessed "
                "combat events trigger multi-stage quests with alternative "
                "victory conditions, cinematic camera sequences and "
                "adversarial mirror training reviews.")
        plan=route_game_prompt(
            self.studio,prompt,project="learning_game",
            max_targets=14,authorized=True,
        )
        keys={a.key for a in plan.axes}
        self.assertTrue({"npc_story_witness","quest_solver","cinematography",
                         "training_review","npc_behavior"}<=keys)
        self.assertGreaterEqual(len(AXES),15)
        self.assertIn("game/director.json",{p.path for p in plan.files})
        self.assertFalse(plan.payload()["model_inference_performed"])
        self.assertTrue(plan.payload()["human_supervision_required"])
        self.assertEqual(plan.digest,route_game_prompt(
            self.studio,prompt,project="learning_game",
            max_targets=14,authorized=True).digest)

    def test_agent_draft_only_proposes_and_never_bypasses_code_review(self):
        prompt=("Write original NPC witness reactions and staged quest "
                "outcomes without executing third party model generated code.")
        plan=route_game_prompt(
            self.studio,prompt,project="learning_game",authorized=True,
        )
        target=next(t for t in plan.files if t.axis=="npc_story_witness")
        candidate=json.dumps({
            "schema":"original_npc_reactions.v1",
            "original_only":True,"rules":[
                {"event":"witness_healing","story":"Offer to help the village"}
            ],
        })
        proposal=ingest_ai_draft(self.studio,plan,{
            "source":"dragon","target":target.path,"replacement":candidate,
            "base_sha256":target.sha256,
            "explanation":"Add a source-grounded NPC recovery storyline that can be reviewed.",
        },authorized=True)
        self.assertFalse(proposal["automatically_committed"])
        self.assertEqual(proposal["agent_source"],"dragon")
        from pathlib import Path
        dest=self.studio.root/"current"/"learning_game"/target.path
        self.assertFalse(dest.exists())
        with self.assertRaises(PermissionError):
            self.studio.commit(proposal["proposal_id"],authorized=True,
                               human_approved=False)
        self.studio.commit(proposal["proposal_id"],authorized=True,
                           human_approved=True)
        self.assertEqual(json.loads(dest.read_text())["original_only"],True)
        self.assertEqual(self.studio.read(
            "current","learning_game",target.path)["content"],candidate)
        with self.assertRaises(PromptRoutingError):
            ingest_ai_draft(self.studio,plan,{
                "source":"dragon","target":"../../foreign_game.py",
                "replacement":"x","base_sha256":target.sha256,
                "explanation":"Attempt uncontrolled source selection",
            },authorized=True)

    def test_curriculum_has_positive_controls_crossproject_split_and_no_auto_training(self):
        campaign=observe_story(
            self.world,self.proof,population=16,
            active_budget=8,ambient_budget=8,
            maximum_witnesses=12,authorized=True,
        )
        mirror=run_mirror_competition(
            self.world,self.proof,campaign,population=16,
            active_budget=8,ambient_budget=8,
            maximum_witnesses=12,attempts=36,authorized=True,
        )
        self.assertTrue(mirror.passed)
        curriculum=build_curriculum(mirror,campaign,authorized=True)
        self.assertEqual(curriculum.red_team_count,36)
        self.assertGreater(curriculum.positive_controls,0)
        self.assertTrue(all(x.split==curriculum.split for x in curriculum.examples))
        self.assertEqual({x.approval for x in curriculum.examples},{"quarantined"})
        self.assertEqual(set(x.expected["decision"] for x in curriculum.examples),
                         {"reject","accept_witnessed_incident_only"})
        stored=quarantine_curriculum(curriculum,self.studio.root,authorized=True)
        self.assertEqual(stored["examples"],len(curriculum.examples))
        self.assertFalse(stored["neural_training_performed"])
        self.assertTrue(Path(stored["path"]).is_file())
        self.assertEqual(Path(stored["path"]).read_bytes(),
                         training_jsonl(curriculum.examples,authorized=True))
        decision=ReviewDecision(curriculum.digest,False,False,True,False,
                                False,False,"Not reviewed by independent teams.")
        with self.assertRaises(AlmanacError):
            promote_curriculum(curriculum,decision,authorized=True)
        # Synthetic gate attestations are not an actual integration to
        # Wiki/HOAG; promotion remains explicit and train-only.
        complete=ReviewDecision(curriculum.digest,True,True,True,True,True,
                                True,"Operator signed all independent gates.")
        if curriculum.split=="train":
            result=promote_curriculum(curriculum,complete,authorized=True)
            index=multi_project_index((result,),authorized=True)
            self.assertEqual(index["verified_project_count"],1)
            self.assertEqual(index["project_digests"],[self.world.digest])
            self.assertFalse(index["machine_weight_training_performed"])
        else:
            with self.assertRaises(AlmanacError):
                promote_curriculum(curriculum,complete,authorized=True)

    def test_review_cli_generates_real_source_bound_training_quarantine(self):
        blueprint=Path(self.temp.name)/"original-director.json"
        blueprint.write_text(json.dumps(self.world.payload()),encoding="utf-8")
        out=io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(workspace_cli([
                "review-game","--root",str(self.studio.root),
                "--director-blueprint",str(blueprint),
                "--population","16","--active-budget","8",
                "--ambient-budget","8","--witness-limit","12",
                "--mirror-attempts","36","--trusted-local-operator",
            ]),0)
        report=json.loads(out.getvalue())
        self.assertEqual(report["mirror_attempts"],36)
        self.assertEqual(report["rejected_attacks"],36)
        self.assertGreater(report["npc_witnesses"],0)
        self.assertGreater(report["emergent_quests"],0)
        self.assertGreater(report["training_candidates"],36)
        self.assertTrue(report["quarantined_dataset"])
        self.assertFalse(report["neural_model_weights_trained"])
        self.assertEqual(self.studio.tree()["training_quarantine"],1)

if __name__=="__main__":
    unittest.main()
