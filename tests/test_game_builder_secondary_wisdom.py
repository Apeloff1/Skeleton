"""Real fitted reviewer weight forensics and governed second wisdom scrutiny."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.game_post_weight_forensics import (
    analyze_post_weight_change,
)
from skeleton.ai.game_builder.game_post_weight_dragon import (
    plan_post_weight_dragon_research,
)
from skeleton.ai.game_builder.game_wisdom_report_archive import (
    publish_secondary_wisdom_report,verify_secondary_wisdom_report,
)
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_secondary_wisdom_loop import (
    ANGLES,ROLES,_full_tasks,WisdomPassAttestation,sign_wisdom_pass,
    run_secondary_wisdom_cycle,
)
from skeleton.ai.game_builder.game_integrated_learning import (
    run_integrated_learning_cycle,
)
from skeleton.ai.game_builder.game_reviewer_optimizer import (
    OptimizerSchedule,optimize_review_weights,
)
from skeleton.ai.game_builder.game_model_promotion import (
    PromotionError,PromotionStandard,
)
from skeleton.ai.game_builder.game_training_flow import CandidateBatch,plan_training_flow
from skeleton.ai.game_builder.game_dragon_peer_wisdom import SourceMediaReceipt,distill_dragon_peer_wisdom
from skeleton.ai.game_builder.competitive_delivery_gate import TrustedCompetitionJudge
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedDocument,ReviewedNote
from skeleton.ai.game_builder.knowledge_rights_bridge import clear_research_for_design
from tests.test_game_builder_optimizer_and_wisdom import ActualPeerWisdomTests
from tests.test_game_builder_reviewer_promotion import promotion_corpus
from skeleton.ai.game_builder.competitive_mirror_training import split_project
from tests.test_game_builder_knowledge_rights_bridge import record

CHECKS=("evidence_trace","legal_source_scope","logical_consistency",
        "measurement_limitations","originality","test_leakage")


class SecondaryWisdomIntegrationTests(ActualPeerWisdomTests):
    @classmethod
    def setUpClass(cls):
        cls.standard=PromotionStandard(min_counterfactual_accuracy=0.0)
        cls.schedule=OptimizerSchedule(learning_rates=(0.12,),epochs=(10,))
        batches=[]
        for batch in promotion_corpus():
            examples=tuple(replace(
                x,evidence=dict(x.evidence,mechanic="platforming"))
                for x in batch.examples)
            batches.append(CandidateBatch(
                batch.source_project,batch.original_almanac,examples))
        cls.plan=plan_training_flow(tuple(batches),authorized=True)
        cls.optimized=optimize_review_weights(
            cls.plan,schedule=cls.schedule,standard=cls.standard,
            authorized=True)
        cls.post=analyze_post_weight_change(
            cls.plan,cls.optimized,standard=cls.standard,
            champion=None,authorized=True)

    def context(self):
        first=distill_dragon_peer_wisdom(
            self.db,self.brief,self.packet,self.ledger,
            tuple(self.medium),authorized=True)
        mission=plan_post_weight_dragon_research(
            self.post,first,authorized=True,consent=True)
        return first,mission

    def expand_sources(self):
        for index in (3,4):
            sid=f"peer-{index}"
            text=f"Independent original platforming challenge study {index}: measured landing controls."
            doc=ReviewedDocument(
                owner="studio-one",source_id=sid,
                source_url=f"https://example.org/independent-original-paper-{index}",
                title=f"Independent platformer analysis {index}",
                text=text,observed_at="2026-10-11T14:00:00Z",
                license_id="licensed-for-reference",
                allowed_scopes=("design_reference","research"),
                reviewer_id=f"reviewer-{index}",approved=True,
                notes=(ReviewedNote(
                    note_id=f"note-{index}",mechanic="platforming",
                    statement="Compare original jumping and landing uncertainty",
                    start=0,end=len(text),stance="supports",
                    confidence_ppm=930000,
                    dependence_group=f"publisher-{index}"),))
            revision=self.db.import_document(
                doc,expected_parent_digest=None,authorized=True)
            self.ledger.register_source(record(
                sid,license_id="licensed-for-reference",
                digest=sha256(text.encode()).hexdigest()))
            self.medium.append(SourceMediaReceipt(
                sid,revision.revision_digest,"paper"))
        brief=self.db.build_brief(
            "studio-one","platforming",authorized=True,
            max_hits=12,min_independent_groups=3)
        packet=clear_research_for_design(
            self.db,brief,self.ledger,
            project_id="original-platformer",
            artifact_digest="a"*64,human_approved=True,authorized=True)
        second=distill_dragon_peer_wisdom(
            self.db,brief,packet,self.ledger,
            tuple(self.medium),authorized=True)
        return brief,packet,second

    def reviews(self,first,second,mission,packet):
        tasks=_full_tasks(first,second,mission)
        keys=tuple((role,TrustedCompetitionJudge(
            role+"_runtime",bytes([n+21])*32))
                   for n,role in enumerate(ROLES))
        rows=[]
        for rnd in (1,2,3):
            selected=tuple(sorted(
                task.digest for task in tasks if task.round_number==rnd))
            for role,key in keys:
                notes=(f"{role.upper()} independently checked stage {rnd}: "
                       "source revisions are distinct, reference licensing is "
                       "inspected, original game replay is needed before gradient "
                       "learning, and uncertainty remains explicit when proof "
                       "is incomplete. Each legal rights decision must remain "
                       "current with the evidence root.")
                row=WisdomPassAttestation(
                    role,rnd,selected,packet.to_payload()["packet_digest"],
                    self.post.digest,canonical_digest(notes),notes,CHECKS,
                    0,0,9100,key.judge_id,
                    "2026-10-11T17:00:00Z","0"*64)
                rows.append(sign_wisdom_pass(row,key))
        return tasks,tuple(rows),keys

    def process(self,first,mission,brief,packet,reviews,keys,
                second_games=None,first_post=None):
        return run_secondary_wisdom_cycle(
            first_almanac=first,
            first_post_weight=first_post or self.post,
            prior_original_games=self.plan,
            previous_candidate_policy=self.optimized.selected_fit["symbolic_policy"],
            first_optimization=self.optimized,first_champion=None,
            mission=mission,wiki=self.db,brief=brief,packet=packet,
            rights=self.ledger,media=tuple(self.medium),
            reviews=reviews,reviewer_keys=keys,
            second_original_games=second_games,
            authorized=True,standard=self.standard,schedule=self.schedule)

    def test_actual_sgd_post_weight_report_and_source_safe_dragon_repeat(self):
        result=self.post
        self.assertEqual(result.model_after_digest,
                         self.optimized.selected_fit["fitted_policy_digest"])
        self.assertEqual(result.dimensionality,256)
        self.assertGreater(result.changed_coordinates,0)
        self.assertEqual(result.evaluation_digest,
                         self.optimized.promotion_evaluation.digest)
        self.assertFalse(result.actual_active_installation_verified)
        self.assertFalse(result.payload()["protected_eval_data_reused_for_training"])
        self.assertFalse(result.payload()["no_core_jeeves_dragon_weight_update"] is False)
        self.assertEqual(result.payload(),analyze_post_weight_change(
            self.plan,self.optimized,standard=self.standard,
            champion=None,authorized=True).payload())
        first,mission=self.context()
        self.assertEqual(len(mission.native_mission.queries),
                         4*len(mission.topics))
        self.assertTrue(all(
            entry in mission.topics for entry in
            ("gameplay npc witnessed event quest causality original world replay",
             "game graphics frame pacing accessibility original art identity",
             "game sound interactive audio caption spatial hearing validation",
             "game story branching causal nonterminal world player agency")))
        self.assertFalse(mission.payload()["protected_holdout_content_never_queried"] is False)
        self.assertEqual(mission.actual_fetches,0)
        with self.assertRaises(PermissionError):
            plan_post_weight_dragon_research(
                result,first,authorized=True,consent=False)

    def test_three_research_passes_are_distinct_reviewed_and_second_training_is_blocked_without_games(self):
        first,mission=self.context()
        brief,packet,second=self.expand_sources()
        tasks,reviews,keys=self.reviews(first,second,mission,packet)
        self.assertEqual(len(tasks),3*len(second.lenses))
        self.assertEqual({x.wisdom_angle for x in tasks},
                         {x[0] for x in ANGLES})
        self.assertEqual(len({x.digest for x in tasks}),len(tasks))
        result=self.process(first,mission,brief,packet,reviews,keys)
        self.assertEqual(result.digested_knowledge_digest,second.digest)
        self.assertTrue(result.source_breadth_increased)
        self.assertEqual(len(result.verification_receipts),9)
        self.assertIsNone(result.second_training)
        self.assertIn("new_original_train_validation_test_worlds_not_present",
                      result.blockers)
        self.assertFalse(result.payload()["real_second_reviewer_sgd_executed"])
        self.assertFalse(result.payload()["foundation_llm_weights_updated"])

        with TemporaryDirectory() as folder:
            ws=GameWorkspace.create(Path(folder)/"studio",authorized=True)
            digest=publish_secondary_wisdom_report(
                ws.root,result,authorized=True)
            self.assertEqual(digest,result.digest)
            self.assertEqual(publish_secondary_wisdom_report(
                ws.root,result,authorized=True),digest)
            archived=verify_secondary_wisdom_report(
                ws.root,digest,authorized=True)
            self.assertEqual(archived,result.payload())
            target=ws.root/"training"/"post_weight_wisdom"/(digest+".json")
            target.write_text("{}\n",encoding="utf-8")
            with self.assertRaises(PromotionError):
                verify_secondary_wisdom_report(
                    ws.root,digest,authorized=True)
            with self.assertRaises(PromotionError):
                publish_secondary_wisdom_report(
                    ws.root,result,authorized=True)

    def test_unsigned_forged_and_incomplete_proofread_reviews_fail_closed(self):
        first,mission=self.context()
        brief,packet,second=self.expand_sources()
        _,reviews,keys=self.reviews(first,second,mission,packet)
        forged=list(reviews)
        forged[0]=replace(forged[0],quality_bp=9999)
        with self.assertRaises(PromotionError):
            self.process(first,mission,brief,packet,tuple(forged),keys)
        with self.assertRaises(PromotionError):
            self.process(first,mission,brief,packet,reviews[:-1],keys)
        with self.assertRaises(PromotionError):
            self.process(first,mission,brief,packet,reviews,keys,
                         first_post=replace(self.post,shadow_fit_qualified=True))
        with self.assertRaises(PromotionError):
            self.process(first,mission,brief,packet,reviews,keys,
                         second_games=self.plan)
        # The six-check proofread is a real signed input, not a fabricated
        # model-supplied Boolean or an unexamined document digest.
        with self.assertRaises(PromotionError):
            replace(reviews[0],proofread_notes="The result is obviously fine.")

    def independent_second_projects(self):
        fresh=[]
        existing=set(self.plan.source_projects)
        for batch in promotion_corpus():
            split=split_project(batch.source_project)
            n=0
            while True:
                project=sha256(
                    f"fresh-independent-original-game-world-{batch.source_project}-{n}".encode()
                ).hexdigest()
                n+=1
                if (project not in existing and
                        split_project(project)==split):
                    break
                if n>200:
                    raise RuntimeError("unable to create independent fixed-split regression world")
            existing.add(project)
            new_examples=[]
            for j,source in enumerate(batch.examples):
                changed_input=dict(source.input)
                if "source_campaign_digest" in changed_input:
                    changed_input["source_campaign_digest"]=project
                if "canonical_witness" in changed_input:
                    changed_input["canonical_witness"]=dict(
                        changed_input["canonical_witness"],
                        source_world=project)
                changed_evidence=dict(source.evidence,
                    mechanic="platforming",
                    source_almanac=canonical_digest({"p":project}))
                new_examples.append(replace(
                    source,project_digest=project,split=split,
                    example_id=canonical_digest(
                        {"new_original_game":project,"case":j}),
                    input=changed_input,evidence=changed_evidence))
            fresh.append(CandidateBatch(
                project,canonical_digest({"independent_second_game":project}),
                tuple(new_examples)))
        plan=plan_training_flow(tuple(fresh),authorized=True)
        self.assertFalse(
            set(plan.source_projects)&set(self.plan.source_projects))
        return plan

    def test_real_secondary_sgd_only_if_first_shadow_and_new_games_qualify(self):
        first,mission=self.context()
        brief,packet,second=self.expand_sources()
        _,reviews,keys=self.reviews(first,second,mission,packet)
        fresh=self.independent_second_projects()
        result=self.process(first,mission,brief,packet,reviews,keys,
                            second_games=fresh)
        self.assertTrue(result.new_train_worlds_independent)
        if self.post.shadow_fit_qualified:
            self.assertIsNotNone(result.second_training)
            self.assertEqual(result.second_training.eligible_mechanics,
                             ("platforming",))
            self.assertIsNotNone(result.second_training.optimization)
            self.assertTrue(result.second_training.optimization.selected_fit[
                "training_performed"])
            self.assertIsNotNone(result.post_second_weights)
            self.assertTrue(result.payload()["real_second_reviewer_sgd_executed"])
            self.assertFalse(result.post_second_weights.actual_active_installation_verified)
            self.assertFalse(result.payload()["secondary_model_staged_or_activated"])
        else:
            self.assertIn("first_weight_candidate_not_independently_qualified",
                          result.blockers)
            self.assertIsNone(result.second_training)
            self.assertFalse(result.payload()["real_second_reviewer_sgd_executed"])

    def test_reference_retraction_or_no_new_sources_blocks_secondary_wisdom(self):
        first,mission=self.context()
        # Merely rereading original Wiki entries cannot count as new wisdom.
        _,reviews,keys=self.reviews(first,first,mission,self.packet)
        with self.assertRaises(PromotionError):
            self.process(first,mission,self.brief,self.packet,reviews,keys)
        brief,packet,second=self.expand_sources()
        _,reviews,keys=self.reviews(first,second,mission,packet)
        # A replacement rights ledger loses the history of old licenses.
        from skeleton.ai.game_builder.rights import RightsLedger
        stale=RightsLedger()
        with self.assertRaises(Exception):
            run_secondary_wisdom_cycle(
                first_almanac=first,first_post_weight=self.post,
                prior_original_games=self.plan,
                previous_candidate_policy=self.optimized.selected_fit["symbolic_policy"],
                first_optimization=self.optimized,first_champion=None,
                mission=mission,wiki=self.db,brief=brief,packet=packet,
                rights=stale,media=tuple(self.medium),
                reviews=reviews,reviewer_keys=keys,
                second_original_games=None,authorized=True,
                standard=self.standard,schedule=self.schedule)


if __name__=="__main__":
    unittest.main()
