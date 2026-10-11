"""R3-18 actual relevance, sandbox, lawful crawler and idle safety regressions."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.competitive_delivery_gate import TrustedCompetitionJudge
from skeleton.ai.game_builder.competitive_evolution_chain import RivalEvolutionChain,LineageStage
from skeleton.ai.game_builder.competitive_title_radar import ThreatRadarError
from skeleton.ai.game_builder.game_dragon_peer_wisdom import DragonWisdomAlmanac
from skeleton.ai.game_builder.game_18round_relevance import (
    OriginalTaskFocus,RelevantKnowledge,SignedUtilityObservation,
    sign_utility_observation,score_task_knowledge,
)
from skeleton.ai.game_builder.game_18round_shadow_sandbox import (
    SandboxVerification,ModularShadowTicket,prepare_shadow_tickets,
    verify_shadow_in_sandbox,sign_sandbox_verification,order_verified_hyperweights,
)
from skeleton.ai.game_builder.game_18round_executor_extensions import (
    execute_idle_round,execute_round7_era_profile,
    execute_round8_engineering_gate,execute_round10_crawler_brief,
    execute_round13_sandbox,execute_round15_structure,
    execute_round16_load_order,execute_round17_report,
)
from skeleton.ai.game_builder.game_post_weight_dragon import PostWeightDragonMission
from skeleton.ai.webcrawler.dragon_research_missions import (
    ResearchInterest,MissionPolicy,plan_research,
)
from skeleton.ai.game_builder.game_18round_runtime import (
    execute_round3_relevance,execute_round4_shadow_backlog,
    derive_round11_reviewed_destinations,execute_round11_destinations,
    execute_round12_crawler_log_ingestion,execute_round18_adjacent_recrawl,
)
from skeleton.ai.game_builder.game_dragon_peer_wisdom import (
    SourceMediaReceipt,distill_dragon_peer_wisdom,
)
from tests.test_game_builder_optimizer_and_wisdom import ActualPeerWisdomTests
from skeleton.ai.game_builder.game_18round_journal import GameEvolutionJournal
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_18round_evolution import (
    ROUND_DESCRIPTIONS,EvolutionRoundReceipt,sign_round_receipt,
    begin_18round_evolution,accept_round,report_remaining_rounds,
    CrawlerDestination,CrawlerLogObservation,sign_crawler_log,
    qualify_crawler_log_handoff,next_dragon_adjacency_mission,
)
from skeleton.ai.game_builder.game_reviewer_optimizer import OptimizerSchedule
from skeleton.ai.game_builder.game_model_promotion import PromotionStandard,PromotionError
from skeleton.ai.game_builder.game_training_flow import plan_training_flow
from tests.test_game_builder_reviewer_promotion import promotion_corpus

STAMP=datetime(2026,10,11,12,0,0,tzinfo=timezone.utc)

class EighteenRoundCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=plan_training_flow(promotion_corpus(),authorized=True)
    def setUp(self):
        self.task=OriginalTaskFocus(
            "owned_game","a"*64,"b"*64,"platformer","retro",
            ("warm","handcrafted"),("npc_agency","gameplay_quality"),8000,2048)
        self.almanac=DragonWisdomAlmanac(
            "game_studio","owned_game","a"*64,"b"*64,"c"*64,
            "d"*64,(),({"mechanic":"npc_agency","conflict":False},),
            (),(),2)
        self.key=TrustedCompetitionJudge("review_authority",b"r"*32)
        self.verifier=TrustedCompetitionJudge("sandbox_verifier",b"v"*32)
        self.subject=RelevantKnowledge(
            "original_npc_witness","npc_agency",self.almanac.digest,
            ("platformer",),("retro",),("warm",),("npc_agency",),
            ("prev_a","prev_b"),False,4,"d"*64)
        stages=tuple(LineageStage(
            x,1980+i,"retro",(),(),("npc_agency",),False,
            "a"*64) for i,x in enumerate(("prev_a","prev_b","rival_c")))
        self.lineage=RivalEvolutionChain(
            "rival_c",("platformer",),True,3,stages,(),(),
            (),"f"*64,False)

    def priority(self):
        rows=tuple(sign_utility_observation(
            SignedUtilityObservation(
                self.subject.topic_id,sha256(
                    f"original-world-{i}".encode()).hexdigest(),
                sha256(f"independent-replay-{i}".encode()).hexdigest(),
                f"sourcegroup_{i}",True,self.key.judge_id,"0"*64),
            self.key) for i in range(4))
        priority=score_task_knowledge(
            self.task,self.almanac,(self.subject,),rows,(self.key,),
            lineage=self.lineage,authorized=True)
        return priority,rows

    def receipt(self,state,status,*,report=None,root="e"*64,when=None):
        round_no=len(state.rounds)+3
        if when is None:when=(STAMP+timedelta(minutes=round_no)).isoformat().replace("+00:00","Z")
        r=EvolutionRoundReceipt(
            round_no,ROUND_DESCRIPTIONS[round_no-3][1],state.task.task_digest,
            state.rounds[-1].digest if state.rounds else state.task.task_digest,
            report or canonical_digest(["evidence",round_no]),
            (root,),status,True,self.key.judge_id,when,"0"*64)
        return sign_round_receipt(r,self.key)

    def test_independently_measured_task_relevance_with_predecessors(self):
        values,rows=self.priority()
        self.assertEqual(len(values),1)
        item=values[0]
        self.assertEqual(item.topic_id,self.subject.topic_id)
        self.assertEqual(item.mode,"experimental_shadow_candidate")
        self.assertGreater(item.estimated_usefulness_bp,0)
        self.assertGreater(item.posterior_mean_bp,item.conservative_utility_bp)
        bad=list(rows);bad[0]=replace(bad[0],improved=False)
        with self.assertRaises(ThreatRadarError):
            score_task_knowledge(self.task,self.almanac,(self.subject,),
                                 tuple(bad),(self.key,),lineage=self.lineage,
                                 authorized=True)
        with self.assertRaises(ThreatRadarError):
            score_task_knowledge(self.task,self.almanac,(self.subject,),
                                 rows+(rows[0],),(self.key,),lineage=self.lineage,
                                 authorized=True)
        recycled=replace(rows[0],independence_group="different_group",
                         signature="0"*64)
        recycled=sign_utility_observation(recycled,self.key)
        with self.assertRaises(ThreatRadarError):
            score_task_knowledge(self.task,self.almanac,(self.subject,),
                                 (rows[0],recycled),(self.key,),
                                 lineage=self.lineage,authorized=True)
        reference=replace(self.subject,reference_only=True)
        query=score_task_knowledge(self.task,self.almanac,(reference,),
                                   rows,(self.key,),lineage=self.lineage,
                                   authorized=True)
        self.assertEqual(query[0].mode,"research_queue_only")

    def test_bounded_module_priority_and_preapproval_stays_queued(self):
        values,_=self.priority()
        queue=prepare_shadow_tickets(self.task,values,self.plan,
             original_code_review_digest="1"*64,allocated_memory_mb=12,
             authorized=True)
        self.assertEqual(len(queue),1)
        self.assertFalse(queue[0].payload()["automatically_activated"])
        result,optimization=verify_shadow_in_sandbox(
            queue[0],self.plan,PromotionStandard(),None,(),(),
            authorized=True,consent=True,
            original_code_quality_approved=True,
            original_code_quality_receipt="1"*64)
        self.assertIsNone(optimization)
        self.assertFalse(result.permission_to_stage)
        self.assertIn("no_installed_champion_for_proven_uplift",result.blockers)
        order=order_verified_hyperweights(self.task,queue,(result,),authorized=True)
        self.assertEqual(order.cached_ticket_ids,())
        self.assertEqual(order.deferred_ticket_ids,(queue[0].ticket_id,))
        with self.assertRaises(PermissionError):
            verify_shadow_in_sandbox(queue[0],self.plan,PromotionStandard(),
                None,(),(),authorized=True,consent=False,
                original_code_quality_approved=True,
                original_code_quality_receipt="1"*64)

    def test_all_sixteen_rounds_are_ordered_and_host_idle_preemptible(self):
        self.assertEqual(len(ROUND_DESCRIPTIONS),16)
        state=begin_18round_evolution(self.task,authorized=True)
        with self.assertRaises(ThreatRadarError):
            accept_round(state,replace(self.receipt(state,"research_recorded"),
                    round_number=4),self.key,authorized=True)
        for target in range(3,19):
            status=("idle_assessed" if target in (5,6) else
                    "shadow_queued" if target in (4,7,8,13,14,15,16) else
                    "research_recorded")
            row=self.receipt(state,status)
            kwargs={}
            if target in (5,6):
                kwargs=dict(host_consented=True,host_idle=lambda:True,
                            thermal_safe=lambda:True)
            state=accept_round(state,row,self.key,authorized=True,**kwargs)
            self.assertEqual(state.rounds[-1].round_number,target)
        self.assertEqual(len(state.rounds),16)
        self.assertEqual(report_remaining_rounds(state,authorized=True).pending_rounds,())
        self.assertIsNone(state.payload()["next_round"])
        self.assertFalse(state.user_model_activation_granted)
        self.assertFalse(state.shadow_approved_for_stage)
        with self.assertRaises(ThreatRadarError):
            accept_round(state,state.rounds[-1],
                         self.key,authorized=True)

    def test_idle_rounds_fail_closed_when_active_unsafe_or_probe_crashes(self):
        state=begin_18round_evolution(self.task,authorized=True)
        state=accept_round(state,self.receipt(state,"research_recorded"),self.key,
                           authorized=True)
        state=accept_round(state,self.receipt(state,"shadow_queued"),self.key,
                           authorized=True)
        pending=self.receipt(state,"idle_assessed")
        with self.assertRaises(PermissionError):
            accept_round(state,pending,self.key,authorized=True)
        with self.assertRaises(ThreatRadarError):
            accept_round(state,pending,self.key,authorized=True,
                         host_consented=True,host_idle=lambda:False,
                         thermal_safe=lambda:True)
        with self.assertRaises(ThreatRadarError):
            accept_round(state,pending,self.key,authorized=True,
                         host_consented=True,host_idle=lambda:True,
                         thermal_safe=lambda:False)
        with self.assertRaises(ThreatRadarError):
            accept_round(state,pending,self.key,authorized=True,
                         host_consented=True,
                         host_idle=lambda:(_ for _ in ()).throw(OSError("probe")),
                         thermal_safe=lambda:True)

    def test_double_signed_sandbox_cannot_be_forged_as_model_promotion(self):
        state=begin_18round_evolution(self.task,authorized=True)
        state=accept_round(state,self.receipt(state,"research_recorded"),self.key,
                           authorized=True)
        proof=SandboxVerification("ticket_a","a"*64,"b"*64,"c"*64,
                    canonical_digest(self.plan.payload()),"d"*64,(),
                    (),True,True,True)
        signed=sign_sandbox_verification(proof,self.verifier)
        receipt=self.receipt(state,"verified_sandbox",report=signed.digest)
        with self.assertRaises(ThreatRadarError):
            accept_round(state,receipt,self.key,authorized=True,
                         shadow_proof=signed)
        with self.assertRaises(ThreatRadarError):
            accept_round(state,receipt,self.key,authorized=True,
                         shadow_proof=replace(signed,strict_measured_gain=False),
                         shadow_verifier=self.verifier)
        accepted=accept_round(state,receipt,self.key,authorized=True,
                             shadow_proof=signed,shadow_verifier=self.verifier)
        self.assertTrue(accepted.shadow_approved_for_stage)
        self.assertFalse(accepted.user_model_activation_granted)

    def test_crawler_destinations_public_https_reviewed_and_sanitized(self):
        for bad in ("http://games.example.org/x","https://localhost/x",
                    "https://127.0.0.1/data","https://user:pass@example.org/x",
                    "https://data.example.org:1000/x","https://intranet.local/x"):
            with self.assertRaises(ThreatRadarError):
                CrawlerDestination("source_a",bad,"a"*64,"b"*64,"c"*64,
                                   "facts_ideas_reference")
        destinations=(CrawlerDestination(
            "source_a","https://games.example.org/research","a"*64,
            "b"*64,"c"*64,"facts_ideas_reference"),)
        log=sign_crawler_log(CrawlerLogObservation(
            "source_a","c"*64,"d"*64,"e"*64,"a"*64,
            "verified_research","training_cleared",self.key.judge_id,"0"*64),
            self.key)
        output=qualify_crawler_log_handoff(destinations,(log,),(self.key,),
                                          authorized=True)
        self.assertEqual(output["research_admissible_sources"],["source_a"])
        self.assertEqual(output["potential_train_rights_sources"],[])
        with self.assertRaises(ThreatRadarError):
            qualify_crawler_log_handoff(destinations,(log,log),(self.key,),
                                        authorized=True)
        with self.assertRaises(ThreatRadarError):
            qualify_crawler_log_handoff(destinations,(replace(log,rights="reference_only"),),
                                        (self.key,),authorized=True)

    def test_adjacency_search_uses_real_dragon_planner_not_faked_fetch(self):
        mission=next_dragon_adjacency_mission(
            self.task,("save recovery",),
            ("npc witness rumor chain","sound mix spatial accessibility"),
            authorized=True,consent=True)
        self.assertEqual(len(mission.queries),8)
        self.assertEqual(
            set(q.sources[0].value for q in mission.queries),
            {"wikipedia","crossref","openalex","europe_pmc"})
        with self.assertRaises(PermissionError):
            next_dragon_adjacency_mission(
                self.task,(),("npc witness rumor chain",),
                authorized=True,consent=False)
        with self.assertRaises(ThreatRadarError):
            next_dragon_adjacency_mission(
                self.task,(),("http://127.0.0.1/private",),
                authorized=True,consent=True)

    def test_custody_persists_stale_head_and_tampered_sqlite_are_rejected(self):
        with TemporaryDirectory() as folder:
            ws=GameWorkspace.create(Path(folder)/"studio",authorized=True)
            before=begin_18round_evolution(self.task,authorized=True)
            with GameEvolutionJournal(ws.root,task=self.task) as journal:
                self.assertEqual(journal.read(signers=(self.key,),authorized=True).digest,
                                 before.digest)
                receipt=self.receipt(before,"research_recorded")
                after=accept_round(before,receipt,self.key,authorized=True)
                journal.append(before,after,signers=(self.key,),authorized=True)
                self.assertEqual(journal.read(
                    signers=(self.key,),authorized=True).digest,after.digest)
                with self.assertRaises(ThreatRadarError):
                    journal.append(before,after,signers=(self.key,),authorized=True)
                r4=self.receipt(after,"shadow_queued")
                next_state=accept_round(after,r4,self.key,authorized=True)
                journal.append(after,next_state,signers=(self.key,),authorized=True)
                self.assertEqual(journal.read(
                    signers=(self.key,),authorized=True).digest,next_state.digest)
                journal.db.execute(
                    "UPDATE ai_evolution_rounds SET receipt_json=? WHERE sequence=1",
                    ('{}',))
                with self.assertRaises(ThreatRadarError):
                    journal.read(signers=(self.key,),authorized=True)


    def test_real_wiki_rights_revision_r3_to_shadow_and_safe_crawler_destinations(self):
        existing=ActualPeerWisdomTests(
            "test_video_article_blog_become_rights_bound_wisdom_without_illegal_training")
        existing.setUp()
        self.addCleanup(existing.db.close)
        almanac=distill_dragon_peer_wisdom(
            existing.db,existing.brief,existing.packet,existing.ledger,
            tuple(existing.medium),authorized=True)
        task=replace(self.task,original_id="original-platformer")
        candidate=RelevantKnowledge(
            "platforming_evidence","platforming",almanac.digest,
            ("platformer",),("retro",),("warm",),
            ("gameplay_quality",),(),True,4,None)
        state=begin_18round_evolution(task,authorized=True)
        stage3,priorities=execute_round3_relevance(
            state,existing.db,existing.brief,existing.packet,existing.ledger,
            tuple(existing.medium),(candidate,),(),(),None,
            reviewer=self.key,as_of="2026-10-11T18:00:00Z",authorized=True)
        self.assertEqual(stage3.rounds[0].round_number,3)
        self.assertEqual(priorities[0].mode,"research_queue_only")
        self.assertEqual(priorities[0].rights,"reference_only")
        stage4,shadow=execute_round4_shadow_backlog(
            stage3,priorities,self.plan,"f"*64,100,
            reviewer=self.key,as_of="2026-10-11T18:01:00Z",
            authorized=True)
        self.assertEqual(shadow,())
        self.assertFalse(stage4.shadow_approved_for_stage)
        self.assertEqual(stage4.rounds[-1].round_number,4)
        destinations=derive_round11_reviewed_destinations(
            existing.db,existing.brief,existing.packet,existing.ledger,
            authorized=True)
        self.assertEqual(len(destinations),3)
        self.assertTrue(all(x.url.startswith("https://") for x in destinations))
        self.assertTrue(all(x.license_use=="facts_ideas_reference"
                            for x in destinations))
        with self.assertRaises(PermissionError):
            derive_round11_reviewed_destinations(
                existing.db,existing.brief,existing.packet,existing.ledger,
                authorized=False)
        for round_no in range(5,11):
            status=("idle_assessed" if round_no in (5,6) else
                    "shadow_queued" if round_no in (7,8) else
                    "research_recorded")
            row=self.receipt(stage4,status,
                             when=f"2026-10-11T18:{round_no:02d}:00Z")
            stage4=accept_round(stage4,row,self.key,authorized=True,
                **(dict(host_consented=True,host_idle=lambda:True,
                        thermal_safe=lambda:True)
                   if round_no in (5,6) else {}))
        with self.assertRaises(ThreatRadarError):
            execute_round11_destinations(
                stage4,existing.db,existing.brief,existing.packet,
                existing.ledger,reviewer=self.key,
                as_of="2026-10-11T18:11:00Z",authorized=True,
                expected_crawler_brief_digest="f"*64)
        stage11,verified=execute_round11_destinations(
            stage4,existing.db,existing.brief,existing.packet,
            existing.ledger,reviewer=self.key,
            as_of="2026-10-11T18:11:00Z",authorized=True,
            expected_crawler_brief_digest=stage4.rounds[-1].report_digest)
        logs=tuple(sign_crawler_log(CrawlerLogObservation(
            dest.source_id,dest.reviewed_metadata_digest,
            "a"*64,"b"*64,dest.source_revision_digest,
            "verified_research","reference_only",
            self.key.judge_id,"0"*64),self.key)
            for dest in verified)
        stage12,received=execute_round12_crawler_log_ingestion(
            stage11,verified,logs,(self.key,),reviewer=self.key,
            as_of="2026-10-11T18:12:00Z",authorized=True)
        self.assertEqual(stage12.rounds[-1].round_number,12)
        self.assertEqual(received["potential_train_rights_sources"],[])
        self.assertEqual(len(received["research_admissible_sources"]),3)

    def test_round18_runtime_produces_real_native_new_crawler_mission(self):
        state=begin_18round_evolution(self.task,authorized=True)
        for round_no in range(3,18):
            status=("idle_assessed" if round_no in (5,6) else
                    "shadow_queued" if round_no in (4,7,8,13,14,15,16)
                    else "research_recorded")
            state=accept_round(
                state,self.receipt(state,status),self.key,authorized=True,
                **(dict(host_consented=True,host_idle=lambda:True,
                        thermal_safe=lambda:True)
                   if round_no in (5,6) else {}))
        completed,mission=execute_round18_adjacent_recrawl(
            state,("known historical mechanics",),
            ("incomplete witness evidence","unknown era graphics quality"),
            reviewer=self.key,as_of="2026-10-12T12:00:00Z",
            authorized=True,consent=True)
        self.assertEqual(len(completed.rounds),16)
        self.assertEqual(completed.rounds[-1].round_number,18)
        self.assertEqual(len(mission.queries),8)
        self.assertFalse(completed.user_model_activation_granted)


    def test_operational_18_round_pipeline_executes_bounded_host_and_module_stages(self):
        values,_=self.priority()
        stage=begin_18round_evolution(self.task,authorized=True)
        r3_digest=canonical_digest([v.payload() for v in values])
        stage=accept_round(stage,self.receipt(stage,"research_recorded",
                                              report=r3_digest),
                           self.key,authorized=True)
        stage,queue=execute_round4_shadow_backlog(
            stage,values,self.plan,"1"*64,24,
            reviewer=self.key,as_of="2026-10-11T12:04:00Z",
            authorized=True)
        self.assertEqual(len(queue),1)
        stage,background=execute_idle_round(
            stage,queue,reviewer=self.key,
            as_of="2026-10-11T12:05:00Z",consent=True,authorized=True,
            host_idle=lambda:True,hardware_safe=lambda:True)
        self.assertEqual(background.game_replays_completed,0)
        self.assertFalse(background.foundation_model_trained)
        stage,general=execute_idle_round(
            stage,queue,reviewer=self.key,
            as_of="2026-10-11T12:06:00Z",consent=True,authorized=True,
            host_idle=lambda:True,hardware_safe=lambda:True)
        self.assertEqual(general.planned_topic_ids,
                         ("gameplay_foundations","graphics_materials",
                          "sound_accessibility","narrative_agency"))
        stage,profile=execute_round7_era_profile(
            stage,queue,reviewer=self.key,
            as_of="2026-10-11T12:07:00Z",authorized=True)
        self.assertEqual(profile.shadow_ids,(queue[0].ticket_id,))
        stage,professional=execute_round8_engineering_gate(
            stage,"1"*64,reviewer=self.key,
            as_of="2026-10-11T12:08:00Z",authorized=True)
        self.assertFalse(professional.quality_certified)
        self.assertEqual(professional.minimum_facet_coverage,102)
        native=plan_research(
            self.task.original_id,(ResearchInterest(
                "player game agency archival evidence",1.0),),
            authorized=True,policy=MissionPolicy(max_interests=1,max_queries=4))
        frontier=PostWeightDragonMission(
            "d"*64,self.almanac.digest,"second_glance",
            ("player game agency archival evidence",),native,1)
        stage=accept_round(stage,self.receipt(
            stage,"research_recorded",
            report=canonical_digest(frontier.payload()),
            when="2026-10-11T12:09:00Z"),self.key,authorized=True)
        stage,brief=execute_round10_crawler_brief(
            stage,frontier,reviewer=self.key,
            as_of="2026-10-11T12:10:00Z",authorized=True)
        self.assertEqual(brief.newly_fetched_sources,0)
        for r in (11,12):
            stage=accept_round(stage,self.receipt(
                stage,"research_recorded",
                when=f"2026-10-11T12:{r:02d}:00Z"),
                self.key,authorized=True)
        stage,sandbox,optimization=execute_round13_sandbox(
            stage,queue[0],queue,self.plan,PromotionStandard(),
            None,(),(),reviewer=self.key,
            independent_verifier=self.verifier,
            as_of="2026-10-11T12:13:00Z",
            authorized=True,consent=True,
            professional_code_review_approved=True,
            professional_code_review_digest="1"*64)
        self.assertIsNone(optimization)
        self.assertFalse(sandbox.permission_to_stage)
        self.assertEqual(stage.rounds[-1].status,"blocked")
        stage=accept_round(stage,self.receipt(
            stage,"blocked",when="2026-10-11T12:14:00Z"),
            self.key,authorized=True)
        stage,structure=execute_round15_structure(
            stage,queue,(sandbox,),reviewer=self.key,
            as_of="2026-10-11T12:15:00Z",authorized=True)
        self.assertEqual(structure.staged_candidates,())
        self.assertEqual(structure.research_only_candidates,
                         (queue[0].ticket_id,))
        stage,loading=execute_round16_load_order(
            stage,queue,(sandbox,),reviewer=self.key,
            as_of="2026-10-11T12:16:00Z",authorized=True)
        self.assertEqual(loading.cached_ticket_ids,())
        stage,report=execute_round17_report(
            stage,None,reviewer=self.key,
            as_of="2026-10-11T12:17:00Z",authorized=True)
        self.assertEqual(report.approved_sandbox_events,0)
        self.assertEqual(report.genuine_model_improvement_claims,0)
        stage,mission=execute_round18_adjacent_recrawl(
            stage,("archived reading",),("npc witnessed rumors",),
            reviewer=self.key,as_of="2026-10-11T12:18:00Z",
            authorized=True,consent=True)
        self.assertEqual(stage.rounds[-1].round_number,18)
        self.assertEqual(len(mission.queries),4)
        self.assertFalse(stage.user_model_activation_granted)



if __name__=="__main__":
    unittest.main()
