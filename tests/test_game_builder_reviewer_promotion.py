"""Promotion standards, honest held-out quality and production-safe registry."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.competitive_mirror_training import (
    TrainingCandidate,split_project,
)
from skeleton.ai.game_builder.game_training_flow import (
    CandidateBatch,plan_training_flow,train_isolated_review_ranker,
)
from skeleton.ai.game_builder.game_model_promotion import (
    PromotionError,PromotionStandard,validate_policy,
    evaluate_candidate,predict_review,require_stronger_standard,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_reviewer_registry import (
    PromotionAttestation,ReviewerRegistry,ROLES,
)
from skeleton.ai.game_builder.quest_scene_forge import forge_director


def promotion_corpus():
    groups={"train":[],"validation":[],"test":[]}
    counter=0
    while any(len(groups[k])<v for k,v in (
        ("train",5),("validation",3),("test",3)
    )):
        project=sha256(f"original-game-promotion-cohort-{counter}".encode()).hexdigest()
        split=split_project(project)
        counter+=1
        if len(groups[split])>=({"train":5,"validation":3,"test":3}[split]):
            continue
        rows=[]
        for j in range(16):
            hostile=j%2==0
            category=("state_forgery","chronology","witness_origin",
                      "source_identity")[j%4]
            rows.append(TrainingCandidate(
                project_digest=project,split=split,
                example_id=canonical_digest({"world":project,"action":j}),
                instruction="Verify actual original game evidence and gameplay.",
                input=({"attack_family":category,
                        "source_campaign_digest":project,
                        "source_state":str(j)} if hostile else
                       {"canonical_witness":{
                           "event":"original_player_deed",
                           "source_world":project,"source_state":str(j)}}),
                expected={"decision":"reject" if hostile else
                          "accept_witnessed_incident_only"},
                evidence={"severity":9 if hostile else 2,
                          "verified_control":not hostile,
                          "source_almanac":canonical_digest({"p":project})},
            ))
        groups[split].append(CandidateBatch(
            project,canonical_digest({"independent_almanac":project}),tuple(rows)))
        if counter>1000:
            raise RuntimeError("insufficient stable heldout original game cohorts")
    return tuple(x for split in ("train","validation","test")
                 for x in groups[split])


class ReviewerPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=plan_training_flow(promotion_corpus(),authorized=True)
        cls.fit=train_isolated_review_ranker(cls.plan,authorized=True,epochs=75)
        cls.standards=PromotionStandard()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace=GameWorkspace.create(Path(self.temp.name)/"review_studio",
                                             authorized=True)
        self.registry=ReviewerRegistry(self.workspace.root)

    def _stage(self):
        return self.registry.stage(self.plan,self.fit,authorized=True)

    def _attest(self):
        state=self.registry.read_state()
        doc=self.registry._candidate(state["candidate"])
        digest=canonical_digest(doc["evaluation"])
        return tuple(PromotionAttestation(
            role, f"reviewer_{i:02d}_independent",
            state["candidate"],digest,
            f"I independently reviewed the {role} original-world evidence.",
            True,
        ) for i,role in enumerate(ROLES))

    def _worlds(self,prefix):
        return tuple(forge_director(
            f"fresh_{prefix}_{i}",seed=882900+i+
            (0 if prefix=="usage" else 1000),
            regions=tuple(f"district_{n:02d}" for n in range(8)),
            quest_types=("main_story","investigation","regional_story"),
            stages=2,
        ) for i in range(2))

    def test_actual_trained_weights_recomputed_from_unseen_game_projects(self):
        self.assertEqual(self.fit["status"],"experimental_fit_only")
        evaluation=evaluate_candidate(
            self.plan,self.fit,authorized=True,
            standard=self.standards,
        )
        self.assertEqual(evaluation.candidate_digest,
                         self.fit["fitted_policy_digest"])
        self.assertGreater(evaluation.metrics["test"]["n"],20)
        self.assertGreater(evaluation.metrics["validation"]["n"],20)
        self.assertGreaterEqual(evaluation.metrics["test"]["critical_cases"],12)
        self.assertTrue(evaluation.passed,str(evaluation.blockers))
        self.assertEqual(evaluation.metrics["test"]["fn"],0)
        self.assertEqual(evaluation.metrics["test"]["fp"],0)
        self.assertGreater(evaluation.metrics["test"]["wilson_recall"],0.72)
        self.assertEqual(evaluation.digest,evaluate_candidate(
            self.plan,self.fit,authorized=True).digest)

    def test_unearned_score_promotions_and_weakened_standards_are_rejected(self):
        with self.assertRaises(PermissionError):
            evaluate_candidate(self.plan,self.fit,authorized=False)
        bad=dict(self.fit,symbolic_policy=dict(
            self.fit["symbolic_policy"],weights=[0.0]*128))
        with self.assertRaises(PromotionError):
            evaluate_candidate(self.plan,bad,authorized=True)
        with self.assertRaises(PromotionError):
            validate_policy({"weights":[0.5]*128,
                             "bias":0,"threshold":0.5,
                             "feature_spec":"unavailable external model"})
        weak=replace(self.standards,min_balanced_accuracy=0.6)
        with self.assertRaises(PromotionError):
            require_stronger_standard(self.standards,weak)
        with self.assertRaises(PromotionError):
            evaluate_candidate(self.plan,dict(self.fit,status="blocked"),
                               authorized=True)
        eval_=evaluate_candidate(self.plan,self.fit,authorized=True,
                                 champion=dict(self.fit["symbolic_policy"]))
        self.assertTrue(eval_.passed)
        self.assertTrue(eval_.champion_digest)
        inferior=dict(self.fit["symbolic_policy"],weights=[0.0]*128,bias=0)
        results=evaluate_candidate(self.plan,self.fit,authorized=True,
                                   champion=inferior)
        self.assertTrue(results.passed)

    def test_registry_journal_staging_and_six_unique_reviewers(self):
        staged=self._stage()
        self.assertEqual(staged["status"],"staged")
        self.assertEqual(self.registry.read_state()["revision"],1)
        attest=self._attest()
        with self.assertRaises(PromotionError):
            self.registry.authorize_shadow(attest[:-1],authorized=True)
        duplicated=list(attest)
        duplicated[-1]=replace(duplicated[-1],reviewer_id=duplicated[0].reviewer_id)
        with self.assertRaises(PromotionError):
            self.registry.authorize_shadow(tuple(duplicated),authorized=True)
        shadow=self.registry.authorize_shadow(attest,authorized=True)
        self.assertEqual(shadow["status"],"shadow")
        self.assertEqual(self.registry.read_state()["phase"],"shadow")
        self.assertEqual(self.registry.read_state()["revision"],2)
        with self.assertRaises(PromotionError):
            self.registry.activate(authorized=True)
        with self.assertRaises(PromotionError):
            self.registry.propose_next_standard(authorized=True)
        # Source receipts are written to immutable SHA-256 linked files.
        receipt=json.loads((self.registry.root/"ledger"/"000002.json").read_text())
        self.assertEqual(receipt["previous"],json.loads(
            (self.registry.root/"ledger"/"000001.json").read_text())["digest"])

    def test_usage_idle_must_both_replay_unseen_real_games_before_activation(self):
        staged=self._stage()
        self.registry.authorize_shadow(self._attest(),authorized=True)
        usage=self.registry.observe(self._worlds("usage"),
                                    mode="usage",authorized=True)
        self.assertEqual(usage["mode"],"usage")
        self.assertEqual(usage["cohort"]["metrics"]["n"],250)
        self.assertTrue(usage["cohort"]["passed"],
                        str(usage["cohort"]["blockers"]))
        self.assertEqual(usage["status"],"shadow")
        with self.assertRaises(PromotionError):
            self.registry.activate(authorized=True)
        idle=self.registry.observe(self._worlds("idle"),
                                   mode="idle",authorized=True)
        self.assertTrue(idle["cohort"]["passed"],
                        str(idle["cohort"]["blockers"]))
        activated=self.registry.activate(authorized=True)
        self.assertEqual(activated["status"],"active")
        self.assertEqual(activated["active"],staged["candidate"])
        state=self.registry.read_state()
        self.assertIsNone(state["candidate"])
        self.assertFalse(state["core_ai_parameters_modified"])
        self.assertEqual(state["revision"],5)
        self.assertEqual(len(state["observations"]),2)
        self.assertTrue(set(state["observations"]["usage"]["source_project_ids"]).isdisjoint(
                        state["observations"]["idle"]["source_project_ids"]))
        active=ReviewerRegistry(self.workspace.root)
        self.assertEqual(active.read_state(),state)
        preview=active.propose_next_standard(authorized=True)
        self.assertEqual(preview["promoted_model"],staged["candidate"])
        self.assertTrue(preview["active_standard_unchanged"])
        self.assertTrue(preview["approval_and_separate_stage_required"])
        self.assertGreater(preview["next_standard"]["min_per_class"],
                           self.standards.min_per_class)
        self.assertEqual(active.read_state(),state)
        _,historical=active._historic_source_roles()
        self.assertTrue(
            set(state["observations"]["usage"]["source_project_ids"])
            .issubset(historical))
        self.assertTrue(
            set(state["observations"]["idle"]["source_project_ids"])
            .issubset(historical))
        with self.assertRaises(PromotionError):
            active.stage(self.plan,self.fit,authorized=True,
                         champion=self.fit["symbolic_policy"])
        with self.assertRaises(PermissionError):
            active.propose_next_standard(authorized=False)
        result=active.abort("Human reviewer requests safe rollback.",authorized=True)
        self.assertEqual(result["status"],"rolled_back")
        self.assertIsNone(result["active"])

    def test_historical_idle_and_usage_cohorts_cannot_be_replayed(self):
        self._stage()
        self.registry.authorize_shadow(self._attest(),authorized=True)
        self.registry.observe(self._worlds("usage"),mode="usage",authorized=True)
        self.registry.observe(self._worlds("idle"),mode="idle",authorized=True)
        self.registry.activate(authorized=True)
        # Active scoring may overwrite the display's "usage" slot, but its
        # earlier sources must remain protected in the full sealed journal.
        new=self.registry.observe(self._worlds("fresh_live"),
                                  mode="usage",authorized=True)
        self.assertEqual(new["status"],"active")
        historical=self.registry._historic_source_roles()[1]
        self.assertTrue(set(new["cohort"]["source_project_ids"]).issubset(historical))
        self.assertTrue({w.digest for w in self._worlds("usage")}.issubset(historical))
        with self.assertRaises(PromotionError):
            self.registry.observe(self._worlds("usage"),mode="idle",
                                  authorized=True)

    def test_abort_incomplete_candidates_leaves_canonical_review_unchanged(self):
        staged=self._stage()
        with self.assertRaises(PermissionError):
            self.registry.abort("Untrusted emergency rollback.",authorized=False)
        stopped=self.registry.abort(
            "Operator canceled unverified local reviewer.",
            authorized=True)
        self.assertEqual(stopped["status"],"rolled_back")
        self.assertIsNone(stopped["active"])
        self.assertTrue((self.registry.root/"candidates"/
                         (staged["candidate"]+".json")).exists())
        self.assertEqual(self.registry.read_state()["phase"],"rolled_back")

    def test_corrupted_journal_is_never_a_confirmed_promotion(self):
        self._stage()
        journal=self.registry.root/"ledger"/"000001.json"
        altered=json.loads(journal.read_text())
        altered["event"]="fake model deployment"
        journal.write_text(json.dumps(altered))
        with self.assertRaises(PromotionError):
            self.registry.read_state()
        with self.assertRaises(PromotionError):
            ReviewerRegistry(self.workspace.root)

    def test_interrupted_ledger_commit_recovery_does_not_fabricate_approval(self):
        self._stage()
        state=self.registry.read_state()
        import skeleton.ai.game_builder.game_reviewer_registry as reg
        original=reg._atomic
        def interrupted(path,body):
            if path.name=="state.json":
                raise InterruptedError("simulated power failure after journal fsync")
            return original(path,body)
        from unittest.mock import patch
        with patch.object(reg,"_atomic",side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                self.registry.abort(
                    "Original reviewer model deliberately rolled back.",
                    authorized=True)
        with self.assertRaises(PromotionError):
            self.registry.read_state()
        repaired=self.registry.recover_interrupted(authorized=True)
        self.assertEqual(repaired["phase"],"rolled_back")
        self.assertEqual(repaired["revision"],state["revision"]+1)
        self.assertIsNone(repaired["active"])

if __name__=="__main__":
    unittest.main()
