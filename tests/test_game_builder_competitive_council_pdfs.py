"""Full 102-facet constructive user critique and three-round model council tests."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
import unittest
import zipfile

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.competitive_deep_analysis import ALL_FACETS,FACETS
from skeleton.ai.game_builder.competitive_delivery_gate import TrustedCompetitionJudge
from skeleton.ai.game_builder.competitive_user_critique import (
    UserGameSnapshot,ReviewedUserProjectEvidence,
    sign_project_evidence,critique_current_user_game,
)
from skeleton.ai.game_builder.competitive_tri_council import (
    ROLES,RoleFinding,AgentDeliberation,sign_deliberation,
    admit_crawler_round,deliberate_verified_round,begin_battle_plan,
    add_verified_round,record_user_plan_decision,
)
from skeleton.ai.game_builder.competitive_pdf_pack import publish_three_ai_pdfs
from skeleton.ai.game_builder.competitive_title_radar import ThreatRadarError
from skeleton.ai.game_builder.competitive_deep_service import examine_enemy_genre_portfolio
from skeleton.ai.game_builder.competitive_watch_service import review_competitive_frontier
from skeleton.ai.game_builder.competitive_watch_book import CompetitionWatchBook
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore,ReviewedDocument,ReviewedNote
from skeleton.ai.game_builder.knowledge_rights_bridge import clear_research_for_design
from skeleton.ai.game_builder.rights import RightsLedger
from tests.test_game_builder_competitive_deep import DeepEnemyCases,T0
from tests.test_game_builder_knowledge_rights_bridge import record


class CompetitiveUserCouncilCases(DeepEnemyCases):
    def setUp(self):
        super().setUp()
        self.reviewers=(
            TrustedCompetitionJudge("serv_adversarial",b"a"*32),
            TrustedCompetitionJudge("serv_dragon",b"d"*32),
            TrustedCompetitionJudge("serv_jeeves",b"j"*32),
        )
        self.research_store=ReviewedKnowledgeStore(":memory:")
        self.research_source_count=0
        self.addCleanup(self.research_store.close)
        self.research_rights=RightsLedger()
        with TemporaryDirectory() as t:
            ws=GameWorkspace.create(Path(t)/"game",authorized=True)
            with CompetitionWatchBook(ws.root) as book:
                scan=review_competitive_frontier(
                    book,self.original,(self.competitor,),tuple(self.links),
                    self.brief,self.packet,self.db,self.rights,as_of=T0,authorized=True)
        self.dossier=examine_enemy_genre_portfolio(
            scan,self.original,(self.competitor,),self.titles,self.edges,
            tuple(self.deep_links),self.deep_brief,self.deep_packet,
            self.deep_db,self.deep_rights,platform="pc",authorized=True).enemy_dossiers[0]
        self.snapshot=UserGameSnapshot(
            "original_world",self.original.design_digest,"b"*64,"c"*64,"pc",T0)
        self.critique=critique_current_user_game(
            self.original,self.snapshot,self.dossier,(),evidence=None,
            trusted_reviewer=None,as_of=T0,authorized=True)

    def research(self,epoch=0):
        outcomes=[]
        # 2, 4, 6 genuinely independently reviewed citations; exact fresh
        # roots grow with each round and all sources remain rights-cleared.
        for round_no in (1,2,3):
            required=(2,4,6)[round_no-1]*(1+epoch)
            while self.research_source_count<required:
                i=self.research_source_count
                sid=f"round_game_source_{i:02d}"
                text=f"Independent original game study {i} on input, play, visuals and audio."
                doc=ReviewedDocument(
                    owner="game_studio",source_id=sid,
                    source_url=f"https://example.org/lawful-studio-research/{sid}",
                    title=f"Independently reviewed games study {i}",
                    text=text,observed_at="2026-10-10T10:00:00Z",
                    license_id="licensed-for-reference",
                    allowed_scopes=("design_reference","research"),
                    reviewer_id="research_editor",approved=True,
                    notes=(ReviewedNote(
                        note_id="study_mechanic",mechanic="npc_agency",
                        statement="Game-design research requires separate original evaluation",
                        start=0,end=len(text),stance="supports",
                        confidence_ppm=900000,
                        dependence_group=f"peer_group_{i:02d}"),))
                self.research_store.import_document(
                    doc,expected_parent_digest=None,authorized=True)
                self.research_rights.register_source(record(
                    source_id=sid,digest=sha256(text.encode()).hexdigest()))
                self.research_source_count+=1
            brief=self.research_store.build_brief(
                "game_studio","games study",authorized=True,
                max_hits=40,min_independent_groups=2)
            packet=clear_research_for_design(
                self.research_store,brief,self.research_rights,
                project_id="original_world",artifact_digest="a"*64,
                human_approved=True,authorized=True)
            stamp=f"2026-10-{10+round_no:02d}T12:00:00Z"
            admission=admit_crawler_round(
                self.research_store,brief,packet,self.research_rights,
                epoch=epoch,round_number=round_no,
                as_of=stamp,authorized=True)
            outcomes.append((admission,brief,packet))
        return outcomes

    def signed_reviews(self,admission,*,qual_bp=9100,veto=False):
        reviews=[]
        challenged={"dragon":"jeeves","jeeves":"adversarial",
                    "adversarial":"dragon"}
        source_digest=admission.reviewed_citation_digests[0]
        for role,key in zip(ROLES,self.reviewers):
            findings=(
                RoleFinding(
                    "npc_agency",9400,"missing",
                    "The uninstrumented player project has no verified witness-to-quest causality benchmarks.",
                    "Build a new witnessed-event graph with credible NPC knowledge and title-specific outcomes.",
                    "Replay 20 independent witnessed, absent-witness, rumor and false-memory game runs.",
                    source_digest),
                RoleFinding(
                    "audio_fallback",8100,"hypothesis",
                    "The current game build lacks an independently replayed mono-audio accessibility evaluation.",
                    "Add original caption and mono accessibility cues with measured spatial fallback reliability.",
                    "Compare 20 original game runs on mono output and two different headphones.",
                    source_digest),
            )
            memo=AgentDeliberation(
                role,admission.epoch,admission.round_number,
                self.critique.digest,admission.digest,
                tuple(sorted(ALL_FACETS)),admission.source_ids,findings,
                challenged[role],
                f"{role.upper()} challenges {challenged[role]} to prove that "
                "unknown current-title quality claims do not substitute for independent replay.",
                "The previous criticism was answered by requesting distinct signed matched experiments "
                "rather than copying any genre reference, with an explicit source rights check.",
                qual_bp,("Unresolved legal source similarity risk requiring stop.",)
                if veto and role=="dragon" else (),
                key.judge_id,admission.researched_at,"0"*64)
            reviews.append(sign_deliberation(memo,key))
        return tuple(reviews)

    def complete_battle(self):
        steps=self.research()
        state=begin_battle_plan(self.critique,authorized=True)
        for research,_,_ in steps:
            result=deliberate_verified_round(
                self.critique,research,self.signed_reviews(research),
                self.reviewers,authorized=True)
            state=add_verified_round(state,result,authorized=True)
        return state,steps

    def test_doubled_scrutiny_and_current_project_critique_are_complete_not_fake(self):
        self.assertEqual(len(ALL_FACETS),102)
        self.assertEqual(tuple(len(FACETS[a]) for a in
                               ("gameplay","graphics","sound","storyline")),
                         (28,24,22,28))
        self.assertEqual(self.critique.all_facet_count,102)
        self.assertEqual(self.critique.missing_live_measurements,102)
        self.assertFalse(self.critique.actual_build_measurement_qualified)
        self.assertTrue(all(x.status=="unmeasured" for x in self.critique.criticisms))
        self.assertTrue(all("handcrafted_encounters" in x.corrective_action
                            for x in self.critique.criticisms))
        self.assertEqual(len({x.facet for x in self.critique.criticisms}),102)

    def test_signed_user_game_evidence_required_for_claims(self):
        with self.assertRaises(ThreatRadarError):
            critique_current_user_game(
                self.original,replace(self.snapshot,frozen_design_digest="f"*64),
                self.dossier,(),evidence=None,trusted_reviewer=None,
                as_of=T0,authorized=True)
        bogus=ReviewedUserProjectEvidence(
            self.snapshot.digest,(),"qa",T0,"0"*64)
        with self.assertRaises(ThreatRadarError):
            critique_current_user_game(
                self.original,self.snapshot,self.dossier,(),
                evidence=bogus,trusted_reviewer=self.reviewers[0],
                as_of=T0,authorized=True)

    def test_three_verified_widening_rounds_and_all_three_roles(self):
        battle,steps=self.complete_battle()
        self.assertTrue(battle.ready_for_pdf_review)
        self.assertEqual(len(battle.rounds),3)
        self.assertEqual([len(x[0].source_ids) for x in steps],[2,4,6])
        self.assertTrue(all(x.accepted for x in battle.rounds))
        self.assertEqual({x.role for x in battle.rounds[-1].role_reviews},set(ROLES))
        self.assertNotEqual(battle.rounds[0].research.digest,battle.rounds[2].research.digest)

    def test_veto_and_forged_model_signatures_block_progress(self):
        research=self.research()[0][0]
        blocked=deliberate_verified_round(
            self.critique,research,self.signed_reviews(research,veto=True),
            self.reviewers,authorized=True)
        self.assertFalse(blocked.accepted)
        with self.assertRaises(ThreatRadarError):
            add_verified_round(
                begin_battle_plan(self.critique,authorized=True),
                blocked,authorized=True)
        forged=list(self.signed_reviews(research))
        forged[0]=replace(forged[0],quantified_quality_bp=9999)
        with self.assertRaisesRegex(ThreatRadarError,"forged"):
            deliberate_verified_round(
                self.critique,research,tuple(forged),
                self.reviewers,authorized=True)
        bad=replace(forged[0],reviewed_facets=tuple(sorted(ALL_FACETS))[:-1])
        with self.assertRaises(ThreatRadarError):
            deliberate_verified_round(
                self.critique,research,(bad,*forged[1:]),
                self.reviewers,authorized=True)

    def test_exact_three_page_pdf_per_role_and_multipart_manifest(self):
        state,_=self.complete_battle()
        with TemporaryDirectory() as d:
            root=Path(d)/"studio"
            GameWorkspace.create(root,authorized=True)
            receipt,awaiting=publish_three_ai_pdfs(
                root,state,self.critique,authorized=True)
            self.assertEqual(awaiting.user_decision,"awaiting_user")
            self.assertEqual(awaiting.packet_digest,receipt.digest)
            self.assertTrue(receipt.three_pages_each)
            folder=Path(receipt.folder)
            packet=json.loads((folder/"manifest.json").read_text())
            self.assertEqual(set(packet["role_document_sha256"]),set(ROLES))
            self.assertEqual(packet["role_pages"],{r:3 for r in ROLES})
            for role in ROLES:
                doc=folder/(role+".pdf")
                self.assertEqual(len(re.findall(rb"/Type /Page\\b",doc.read_bytes())),3)
                self.assertEqual(sha256(doc.read_bytes()).hexdigest(),
                                 packet["role_document_sha256"][role])
            with zipfile.ZipFile(folder/"complete-review-packet.zip") as z:
                self.assertEqual(set(z.namelist()),
                                 {"dragon.pdf","jeeves.pdf","adversarial.pdf","manifest.json"})
                for role in ROLES:
                    self.assertEqual(z.read(role+".pdf"),(folder/(role+".pdf")).read_bytes())
            with self.assertRaises(ThreatRadarError):
                publish_three_ai_pdfs(root,awaiting,self.critique,authorized=True)
            with self.assertRaises(ThreatRadarError):
                record_user_plan_decision(
                    awaiting,decision="approve",feedback="",
                    exact_packet_digest="f"*64,authorized=True)
            approved=record_user_plan_decision(
                awaiting,decision="approve",feedback="",
                exact_packet_digest=receipt.digest,authorized=True)
            self.assertEqual(approved.user_decision,"user_approved")

    def test_user_rejection_enforces_more_sources_and_new_three_round_review(self):
        state,research_steps=self.complete_battle()
        with TemporaryDirectory() as d:
            root=Path(d)/"studio";GameWorkspace.create(root,authorized=True)
            packet,awaiting=publish_three_ai_pdfs(
                root,state,self.critique,authorized=True)
        revised=record_user_plan_decision(
            awaiting,decision="revise",
            feedback="The counterproposal needs deeper sound restoration and specific NPC causal proof.",
            exact_packet_digest=packet.digest,authorized=True)
        self.assertEqual(revised.epoch,1)
        self.assertFalse(revised.ready_for_pdf_review)
        self.assertEqual(revised.rounds,())
        with self.assertRaises(ThreatRadarError):
            admit_crawler_round(
                self.research_store,research_steps[-1][1],research_steps[-1][2],
                self.research_rights,epoch=1,round_number=3,
                as_of="2026-10-14T12:00:00Z",authorized=True)


if __name__=="__main__":
    unittest.main()
