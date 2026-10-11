"""R3-18 actual relevance, sandbox, lawful crawler and idle safety regressions."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from unittest.mock import patch
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
            round_no,ROUND_DESCRIPTIONS[round_no-3][1],self.task.task_digest,
            state.rounds[-1].digest if state.rounds else self.task.task_digest,
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


if __name__=="__main__":
    unittest.main()
