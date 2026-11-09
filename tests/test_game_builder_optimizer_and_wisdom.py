"""Real optimizer competitions and rights-bound peer source distillation."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.game_dragon_peer_wisdom import (
    SourceMediaReceipt, WisdomFusionError, distill_dragon_peer_wisdom,
    publish_dragon_almanac,
)
from skeleton.ai.game_builder.game_reviewer_optimizer import (
    OptimizerSchedule,OptimizationResult,optimize_review_weights,
)
from skeleton.ai.game_builder.game_integrated_learning import run_integrated_learning_cycle
from skeleton.ai.game_builder.game_reviewer_v2 import train_robust_game_reviewer
from skeleton.ai.game_builder.game_model_promotion import PromotionError,PromotionStandard,PromotionEvaluation
from skeleton.ai.game_builder.game_model_cli import parser as model_parser
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_training_flow import (
    CandidateBatch,plan_training_flow,TrainingFlowError,
)
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedKnowledgeStore,ReviewedDocument,ReviewedNote,
)
from skeleton.ai.game_builder.knowledge_rights_bridge import (
    clear_research_for_design,
)
from skeleton.ai.game_builder.rights import (
    RightsLedger,RightsState,UseKind,
)
from tests.test_game_builder_knowledge_rights_bridge import provenance,record
from tests.test_game_builder_reviewer_promotion import promotion_corpus


class ActualWeightOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=plan_training_flow(promotion_corpus(),authorized=True)

    def test_competes_real_sgd_without_leaking_test_into_selection(self):
        schedule=OptimizerSchedule(learning_rates=(0.12,0.24),epochs=(10,),max_trials=2)
        selected=[]
        actual=train_robust_game_reviewer
        def tracked(*a,**kw):
            result=actual(*a,**kw)
            selected.append((kw["evaluate_test"],result.get("test") is not None))
            return result
        from skeleton.ai.game_builder import game_reviewer_optimizer as module
        with patch.object(module,"train_robust_game_reviewer",side_effect=tracked):
            result=optimize_review_weights(self.plan,schedule=schedule,authorized=True)
        self.assertEqual(selected,[(False,False),(False,False),(True,True)])
        self.assertEqual(result.winner_index in (0,1),True)
        self.assertEqual(len(result.trial_receipts),2)
        self.assertTrue(all(not row["protected_test_opened"]
                            for row in result.trial_receipts))
        self.assertTrue(result.selected_fit["training_performed"])
        self.assertEqual(result.promotion_evaluation.candidate_digest,
                         result.selected_fit["fitted_policy_digest"])
        self.assertFalse(result.payload()["deployment_authorized"])
        self.assertFalse(result.payload()["independent_test_used_for_search"])
        self.assertEqual(result.payload(),optimize_review_weights(
            self.plan,schedule=schedule,authorized=True).payload())

    def test_only_measured_non_regressing_champion_uplift_is_improvement(self):
        metrics={"test":{"balanced_accuracy":0.95,"brier":0.04},
                 "champion":{"test":{"balanced_accuracy":0.95,"brier":0.04}}}
        equal=PromotionEvaluation("a"*64,"b"*64,"c"*64,
                                  metrics,(),"d"*64,"e"*64)
        result=OptimizationResult(
            "f"*64,"1"*64,(),0,{"fitted_policy_digest":"a"*64},
            equal,"d"*64)
        self.assertFalse(result.candidate_improved)
        self.assertFalse(result.ready_for_stage)
        better=dict(metrics,test={"balanced_accuracy":0.96,"brier":0.03})
        improved=replace(result,promotion_evaluation=replace(
            equal,metrics=better))
        self.assertTrue(improved.candidate_improved)
        self.assertTrue(improved.ready_for_stage)
        bootstrap=replace(result,champion_digest=None)
        self.assertFalse(bootstrap.candidate_improved)
        self.assertTrue(bootstrap.ready_for_stage)
        worse=dict(metrics,test={"balanced_accuracy":0.96,"brier":0.05})
        degraded=replace(result,promotion_evaluation=replace(
            equal,metrics=worse))
        self.assertFalse(degraded.candidate_improved)
        self.assertFalse(degraded.ready_for_stage)
        self.assertTrue(result.payload()["deployment_authorized"] is False)

    def test_optimizer_cli_has_explicit_staging_not_active_deployment(self):
        parsed=model_parser().parse_args([
            "optimize-stage","--root","local-studio",
            "--trusted-local-operator","--epoch-candidates","10",
            "--learning-rates","0.12"])
        self.assertEqual(parsed.action,"optimize-stage")
        self.assertEqual(parsed.epoch_candidates,[10])
        self.assertEqual(parsed.learning_rates,[0.12])

    def test_unqualified_or_partial_optimizer_configurations_fail_closed(self):
        with self.assertRaises(PromotionError):
            OptimizerSchedule(learning_rates=(0.1,0.1),epochs=(10,))
        with self.assertRaises(PromotionError):
            OptimizerSchedule(learning_rates=(0.2,),epochs=(2,))
        with self.assertRaises(PermissionError):
            optimize_review_weights(self.plan,authorized=False)
        original=next(x for x in self.plan.selected if x.split=="test")
        altered=replace(original,expected={"decision":"unreviewed_invalid_label"})
        changed=replace(self.plan,selected=tuple(
            altered if x.example_id==original.example_id else x
            for x in self.plan.selected))
        untouched=train_robust_game_reviewer(changed,epochs=10,authorized=True,
                                             evaluate_test=False)
        self.assertEqual(untouched["status"],"validation_selection_only")
        self.assertIsNone(untouched["test"])
        with self.assertRaises(TrainingFlowError):
            train_robust_game_reviewer(changed,epochs=10,authorized=True,
                                      evaluate_test=True)


class ActualPeerWisdomTests(unittest.TestCase):
    def setUp(self):
        self.db=ReviewedKnowledgeStore(":memory:")
        self.addCleanup(self.db.close)
        self.ledger=RightsLedger()
        self.doc=[]
        self.medium=[]
        for index,kind in enumerate(("video","article","blog")):
            source_id=f"peer-{index}"
            text=f"Original platforming control study {index}: measure landing drift."
            stamp=f"2026-10-{8+index:02d}T12:00:00Z"
            self.doc.append(ReviewedDocument(
                owner="studio-one",source_id=source_id,
                source_url=f"https://example.org/independent-{kind}-{index}",
                title=f"Peer {kind} study for platforming",
                text=text,observed_at=stamp,
                license_id="licensed-for-reference",
                allowed_scopes=("design_reference","research"),
                reviewer_id=f"reviewer-{index}",approved=True,
                notes=(ReviewedNote(
                    note_id=f"note-{index}",mechanic="platforming",
                    statement="Independently measure landing control and drift",
                    start=0,end=len(text),stance="supports",
                    confidence_ppm=860000,
                    dependence_group=f"publisher-{index}",
                    tags=("control","platforming"),
                ),),
            ))
            receipt=self.db.import_document(
                self.doc[-1],expected_parent_digest=None,authorized=True)
            self.medium.append(SourceMediaReceipt(
                source_id,receipt.revision_digest,kind,
                peer_review_receipt_digest=(sha256(f"review-{index}".encode()).hexdigest()
                                            if index<2 else None),
            ))
            rights=record(
                source_id,license_id="licensed-for-reference",
                digest=sha256(text.encode("utf-8")).hexdigest())
            self.ledger.register_source(rights)
        self.brief=self.db.build_brief(
            "studio-one","platforming",authorized=True,max_hits=12,
            min_independent_groups=3)
        self.packet=clear_research_for_design(
            self.db,self.brief,self.ledger,
            project_id="original-platformer",
            artifact_digest="a"*64,human_approved=True,authorized=True)

    def distill(self,*,medium=None,packet=None):
        return distill_dragon_peer_wisdom(
            self.db,self.brief,packet or self.packet,self.ledger,
            tuple(self.medium if medium is None else medium),
            authorized=True)

    def test_video_article_blog_become_rights_bound_wisdom_without_illegal_training(self):
        result=self.distill()
        payload=result.payload()
        self.assertEqual(payload["source_kinds"],["article","blog","video"])
        self.assertEqual(payload["independent_source_groups"],3)
        self.assertEqual(payload["lenses"][0]["support_groups"],3)
        self.assertEqual(payload["lenses"][0]["hoag_competitive_readiness"],
                         "research_only")
        self.assertEqual(payload["lenses"][0]["jeeves_conditional_reasoning"],
                         "propose_original_experiment")
        self.assertFalse(payload["training_use_authorized"])
        self.assertFalse(payload["trained_llm_weights_modified"])
        self.assertFalse(payload["can_promote_model"])
        self.assertFalse(payload["source_copyrighted_text_or_video_copied"])
        self.assertNotIn(self.doc[0].text,json.dumps(payload))
        self.assertTrue(all(x["facts_ideas_reference_only"] for x in payload["sources"]))
        self.assertEqual(self.distill().digest,result.digest)
        with TemporaryDirectory() as folder:
            ws=GameWorkspace.create(Path(folder)/"original-games",authorized=True)
            first=publish_dragon_almanac(ws.root,result,authorized=True)
            self.assertEqual(first,result.digest)
            self.assertEqual(publish_dragon_almanac(ws.root,result,authorized=True),first)
            archive=ws.root/"training"/"dragon_peer_almanacs"/(first+".json")
            data=json.loads(archive.read_text())
            self.assertEqual(canonical_digest(data),first)
            with self.assertRaises(PermissionError):
                publish_dragon_almanac(ws.root,result,authorized=False)

    def test_wiki_jeeves_hoag_dragon_cannot_improve_without_new_original_games(self):
        standard=PromotionStandard(min_counterfactual_accuracy=0.0)
        schedule=OptimizerSchedule(learning_rates=(0.12,),epochs=(10,))
        untouched=plan_training_flow(promotion_corpus(),authorized=True)
        blocked=run_integrated_learning_cycle(
            self.db,self.brief,self.packet,self.ledger,tuple(self.medium),
            untouched,authorized=True,standard=standard,schedule=schedule)
        self.assertEqual(blocked.payload()["status"],
                         "await_independently_replayed_train_games")
        self.assertEqual(blocked.gaps[0]["reason"],
                         "missing_two_independent_original_train_worlds")
        self.assertIsNone(blocked.optimization)
        self.assertFalse(blocked.payload()["source_video_article_blog_data_directly_in_gradients"])
        batches=[]
        for batch in promotion_corpus():
            cases=tuple(replace(
                case,evidence=dict(case.evidence,mechanic="platforming"))
                        for case in batch.examples)
            batches.append(CandidateBatch(batch.source_project,
                                          batch.original_almanac,cases))
        plan=plan_training_flow(tuple(batches),authorized=True)
        reviewed=run_integrated_learning_cycle(
            self.db,self.brief,self.packet,self.ledger,tuple(self.medium),
            plan,authorized=True,standard=standard,schedule=schedule)
        self.assertEqual(reviewed.payload()["status"],"evaluated")
        self.assertEqual(reviewed.eligible_mechanics,("platforming",))
        self.assertEqual(reviewed.optimization.winner_index,0)
        self.assertTrue(reviewed.optimization.selected_fit["training_performed"])
        self.assertFalse(reviewed.optimization.payload()["deployment_authorized"])
        self.assertTrue(reviewed.payload()["hoag_predeclared_competitive_standard"])
        self.assertFalse(reviewed.payload()["automatic_model_deployment"])

    def test_wrong_medium_revision_or_repeated_source_does_not_launder_reviews(self):
        changed=list(self.medium)
        changed[0]=replace(changed[0],revision_digest="e"*64)
        with self.assertRaises(WisdomFusionError):
            self.distill(medium=changed)
        with self.assertRaises(WisdomFusionError):
            self.distill(medium=[self.medium[0],self.medium[0],self.medium[2]])
        with self.assertRaises(PermissionError):
            distill_dragon_peer_wisdom(
                self.db,self.brief,self.packet,self.ledger,
                tuple(self.medium),authorized=False)

    def test_retraction_and_rights_revision_invalidate_distilled_peer_data(self):
        last=self.doc[0]
        prior=self.db.history("studio-one",last.source_id,authorized=True)[-1]
        changed=replace(last,approved=False,status="retracted",notes=(),
                        text="",observed_at="2026-10-12T12:00:00Z")
        self.db.import_document(
            changed,expected_parent_digest=prior.revision_digest,authorized=True)
        with self.assertRaises(ValueError):
            self.distill()
        # Rights changes invalidate previous human clearance, even if they
        # happen without any change to the cited article text.
        other=ActualPeerWisdomTests("test_video_article_blog_become_rights_bound_wisdom_without_illegal_training")
        other.setUp()
        self.addCleanup(other.db.close)
        other.ledger.register_source(record(
            source_id="another",digest="a"*64,
            license_id="licensed-for-reference"))
        with self.assertRaises(ValueError):
            other.distill()


if __name__=="__main__":
    unittest.main()
