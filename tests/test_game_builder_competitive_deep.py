"""Deep four-domain competitor scripts, three-generation ancestry, and real signed scores."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.competitive_deep_analysis import (
    FACETS,ALL_FACETS,FacetMeasurement,
    compose_deep_probe_scripts,score_deep_scripts,sign_facet_measurement,
)
from skeleton.ai.game_builder.competitive_evolution_chain import (
    ComparableEraTitle,EvidenceLineageEdge,build_rival_evolution_chain,
)
from skeleton.ai.game_builder.competitive_counterproposals import (
    propose_original_outclassing,evaluate_original_counterproposal,
    SignedImplementationReview,sign_implementation_review,
)
from skeleton.ai.game_builder.competitive_ancestry_frontier import evaluate_ancestral_outclassing
from skeleton.ai.game_builder.competitive_deep_service import (
    examine_enemy_genre_portfolio,
)
from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.competitive_title_radar import (
    ThreatRadarError,RivalSourceLink,
)
from skeleton.ai.game_builder.competitive_delivery_gate import TrustedCompetitionJudge
from skeleton.ai.game_builder.competitive_watch_service import (
    review_competitive_frontier,
)
from skeleton.ai.game_builder.competitive_watch_book import CompetitionWatchBook
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedKnowledgeStore,ReviewedDocument,ReviewedNote,
)
from skeleton.ai.game_builder.knowledge_rights_bridge import clear_research_for_design
from tests.test_game_builder_competitive_radar import CompetitorRadarCases,T0,T1
from tests.test_game_builder_knowledge_rights_bridge import record

PHASES=(
    ("rust_labyrinth","Rust Labyrinth",1999,"retro_3d"),
    ("clockwork_vale","Clockwork Vale",2010,"hd_console"),
    ("other_atlas","Orbital Hearts",2025,"modern_pc"),
)
D="a"*64


class DeepEnemyCases(CompetitorRadarCases):
    def setUp(self):
        super().setUp()
        self.threat=self.radar()[0]
        self.deep_db=ReviewedKnowledgeStore(":memory:")
        self.addCleanup(self.deep_db.close)
        from skeleton.ai.game_builder.rights import RightsLedger
        self.deep_rights=RightsLedger()
        self.deep_links=[]
        specs=[]
        for index,(older,newer) in enumerate(zip(PHASES[:-1],PHASES[1:])):
            for group in ("a","b"):
                specs.append((
                    f"link_{index}_{group}",
                    "lineage_comparable",
                    f"{older[1]} and {newer[1]} genre comparable source",
                    f"Independent genre comparable chronology for {older[1]} and {newer[1]}",
                    f"history_{index}_{group}",
                ))
        for group in ("a","b"):
            specs.append((
                f"npc_agency_{group}","npc_agency",
                "Orbital Hearts NPC witness agency review",
                "Independent measurement of NPC agency including witness memory and response.",
                f"npc_{group}",
            ))
        for source_id,mechanic,title,body,group in specs:
            document=ReviewedDocument(
                owner="game_studio",source_id=source_id,
                source_url=f"https://example.org/history/{source_id}",
                title=title,text=body,
                observed_at="2026-10-10T08:00:00Z",
                license_id="licensed-for-reference",
                allowed_scopes=("design_reference","research"),
                reviewer_id="research_editor",approved=True,
                notes=(ReviewedNote(
                    note_id="source_note",mechanic=mechanic,
                    statement=f"Reviewed {mechanic} evidence about {title}",
                    start=0,end=len(body),stance="supports",
                    confidence_ppm=920000,dependence_group=group),))
            receipt=self.deep_db.import_document(
                document,expected_parent_digest=None,authorized=True)
            self.deep_rights.register_source(record(
                source_id=source_id,digest=sha256(body.encode()).hexdigest()))
            self.deep_links.append(RivalSourceLink(
                self.threat.rival_id,source_id,receipt.revision_digest))
        self.deep_brief=self.deep_db.build_brief(
            "game_studio","lineage_comparable npc_agency",
            authorized=True,max_hits=12,min_independent_groups=2)
        self.assertEqual(len(self.deep_brief.citations),6)
        self.deep_packet=clear_research_for_design(
            self.deep_db,self.deep_brief,self.deep_rights,
            project_id="original_world",artifact_digest=D,
            human_approved=True,authorized=True)
        self.titles=tuple(ComparableEraTitle(
            ident,display,year,era,("pc",),("adventure","simulation"),
            ("npc_agency",),self.deep_brief.knowledge_root)
            for ident,display,year,era in PHASES)
        self.edges=(
            EvidenceLineageEdge(
                "rust_labyrinth","clockwork_vale","genre_comparable",
                ("link_0_a","link_0_b"),("npc_agency",)),
            EvidenceLineageEdge(
                "clockwork_vale","other_atlas","genre_comparable",
                ("link_1_a","link_1_b"),("npc_agency",)),
        )
        self.judges=(
            TrustedCompetitionJudge("external_a",b"a"*32),
            TrustedCompetitionJudge("external_b",b"b"*32),
        )

    def chain(self,edges=None,titles=None):
        return build_rival_evolution_chain(
            self.competitor,self.threat,
            self.titles if titles is None else titles,
            self.edges if edges is None else edges,
            self.deep_brief,self.deep_packet,
            self.deep_db,self.deep_rights,authorized=True)

    def scripts(self):
        return compose_deep_probe_scripts(
            self.original,self.threat,self.deep_brief,self.deep_packet,
            self.deep_db,self.deep_rights,tuple(self.deep_links),
            platform="pc",authorized=True)

    def measured(self,script,*,original_low=5000,with_industry=True):
        values=[]
        for subject,center,lower,upper in (
            (self.original.title_id,original_low+200,original_low,original_low+400),
            (self.threat.rival_id,6000,5800,6200),
            ("industry_cohort",8000,7700,8300),
        ):
            if subject=="industry_cohort" and not with_industry:
                continue
            for evaluator in self.judges:
                row=FacetMeasurement(
                    script.digest,subject,evaluator.judge_id,
                    center,lower,upper,60,
                    sha256(f"{script.digest}|{subject}|{evaluator.judge_id}|{original_low}".encode()).hexdigest(),
                    T0,"0"*64)
                values.append(sign_facet_measurement(row,evaluator))
        samples=tuple(x for x in values if x.subject_id!="industry_cohort")
        control=tuple(x for x in values if x.subject_id=="industry_cohort")
        return samples,control

    def scoring(self,*,original_low=5000,industry=True):
        scripts=self.scripts()
        script=next(s for s in scripts if s.facet=="npc_agency")
        measured,baselines=self.measured(
            script,original_low=original_low,with_industry=industry)
        verdicts=score_deep_scripts(
            scripts,self.threat.rival_id,self.original.title_id,
            measured,self.judges,as_of=T0,authorized=True,
            industry_baselines=baselines)
        return scripts,verdicts,measured,baselines

    def test_deep_gameplay_graphics_sound_storyline_are_all_explicitly_scripted(self):
        scripts=self.scripts()
        self.assertEqual(len(scripts),102)
        self.assertEqual(len({x.digest for x in scripts}),102)
        self.assertEqual({x.axis for x in scripts},set(FACETS))
        self.assertTrue(all(len(s.steps)>=8 and s.adverse_controls for s in scripts))
        self.assertTrue(all(s.measurement_is_verified is False for s in scripts))
        self.assertEqual(
            next(s for s in scripts if s.facet=="npc_agency").research_status,
            "grounded_hypothesis")
        self.assertEqual(
            next(s for s in scripts if s.facet=="spatial_audio").research_status,
            "await_independent_research")

    def test_chronological_genre_predecessors_and_provenance_not_invented(self):
        chain=self.chain()
        self.assertTrue(chain.complete_competitor_coverage)
        self.assertEqual(chain.verified_generations,3)
        self.assertEqual([s.title_id for s in chain.stages],
                         [t[0] for t in PHASES])
        self.assertFalse(chain.is_causal_ancestry_proof)
        self.assertEqual(len(chain.genre_comparable_edges),2)
        self.assertEqual(len(chain.direct_influence_edges),0)
        self.assertTrue(chain.payload()["comparable_older_games_are_not_automatically_ancestors"])
        self.assertEqual(self.chain().digest,chain.digest)

    def test_malformed_or_uncorroborated_ancestry_is_rejected(self):
        bad=replace(self.edges[0],source_ids=("link_0_a","link_1_a"))
        with self.assertRaises(ThreatRadarError):
            self.chain(edges=(bad,self.edges[1]))
        reversed_edge=EvidenceLineageEdge(
            "other_atlas","clockwork_vale","genre_comparable",
            ("link_1_a","link_1_b"),("npc_agency",))
        with self.assertRaises(ThreatRadarError):
            self.chain(edges=(self.edges[0],reversed_edge))
        incomplete=self.chain(edges=self.edges[:1])
        self.assertFalse(incomplete.complete_competitor_coverage)
        self.assertIn("insufficient_verified_independent_generations",
                      incomplete.unresolved_ancestry)

    def test_signed_real_control_cohort_is_required_before_weakspot_claim(self):
        scripts,verdicts,measured,baseline=self.scoring()
        known=next(v for v in verdicts if v.facet=="npc_agency")
        self.assertEqual(known.status,"verified_weakspot")
        self.assertEqual(known.rival_conservative_upper_bp,6200)
        self.assertEqual(known.gap_to_outperform_bp,1350)
        self.assertEqual(sum(v.status=="insufficient_evidence" for v in verdicts),101)
        missing=score_deep_scripts(
            scripts,self.threat.rival_id,self.original.title_id,
            measured,self.judges,as_of=T0,authorized=True)
        v=next(x for x in missing if x.facet=="npc_agency")
        self.assertEqual(v.status,"outwork_required")
        tampered=list(baseline)
        tampered[0]=replace(tampered[0],lower_bp=7701)
        with self.assertRaisesRegex(ThreatRadarError,"forged"):
            score_deep_scripts(
                scripts,self.threat.rival_id,self.original.title_id,
                measured,self.judges,as_of=T0,authorized=True,
                industry_baselines=tuple(tampered))

    def test_independent_peer_evidence_and_script_identity_cannot_be_spoofed(self):
        scripts,verdicts,measured,baseline=self.scoring()
        forged=list(measured)
        forged[0]=replace(forged[0],score_bp=5300)
        with self.assertRaises(ThreatRadarError):
            score_deep_scripts(
                scripts,self.threat.rival_id,self.original.title_id,
                tuple(forged),self.judges,as_of=T0,authorized=True)
        with self.assertRaises(PermissionError):
            self.chain() if False else build_rival_evolution_chain(
                self.competitor,self.threat,self.titles,self.edges,
                self.deep_brief,self.deep_packet,self.deep_db,self.deep_rights,
                authorized=False)
        wrong=replace(measured[0],script_digest="f"*64)
        with self.assertRaises(ThreatRadarError):
            score_deep_scripts(
                scripts,self.threat.rival_id,self.original.title_id,
                (wrong,),self.judges,as_of=T0,authorized=True)
        with self.assertRaises(ThreatRadarError):
            compose_deep_probe_scripts(
                self.original,self.threat,self.deep_brief,self.deep_packet,
                self.deep_db,self.deep_rights,tuple(self.deep_links[:-1]),
                platform="pc",authorized=True)

    def test_original_counterproposals_are_51_experiments_not_51_fake_upgrades(self):
        scripts,verdicts,_,_=self.scoring()
        tasks=propose_original_outclassing(
            self.original,self.threat,self.chain(),scripts,verdicts,
            authorized=True)
        self.assertEqual(len(tasks),len(scripts))
        self.assertEqual(len({x.facet for x in tasks}),102)
        self.assertEqual(sum(not t.needs_new_evidence for t in tasks),1)
        focus=next(t for t in tasks if t.facet=="npc_agency")
        self.assertEqual(focus.target_lower_bp,6350)
        self.assertIn("handcrafted_encounters"," ".join(focus.work_scripts))
        self.assertEqual(len(focus.lineage_chain_ids),3)
        self.assertFalse(focus.payload()["actual_game_implementation_completed"])
        self.assertFalse(focus.payload()["release_approved"])
        too_small=1
        with self.assertRaises(ThreatRadarError):
            propose_original_outclassing(
                self.original,self.threat,self.chain(),scripts,verdicts,
                authorized=True,max_tasks=too_small)

    def test_actual_counterproposal_qualification_needs_new_replay_gain(self):
        scripts,before,_,_=self.scoring()
        focus=next(t for t in propose_original_outclassing(
            self.original,self.threat,self.chain(),scripts,before,
            authorized=True) if t.facet=="npc_agency")
        after=self.scoring(original_low=7500)[1]
        old=next(x for x in before if x.facet=="npc_agency")
        new=next(x for x in after if x.facet=="npc_agency")
        fail=evaluate_original_counterproposal(
            focus,old,new,replay_implementation_digest=None,
            originality_review_passed=True,
            protected_quality_gates_passed=True,authorized=True)
        self.assertFalse(fail.fulfilled)
        self.assertIn("no_implemented_original_game_replay",fail.reasons)
        unsigned=evaluate_original_counterproposal(
            focus,old,new,replay_implementation_digest="b"*64,
            originality_review_passed=True,
            protected_quality_gates_passed=True,authorized=True)
        self.assertFalse(unsigned.fulfilled)
        self.assertIn("no_signed_build_and_measurement_qualification",unsigned.reasons)
        qa=TrustedCompetitionJudge("separate_qa",b"q"*32)
        reviewed=sign_implementation_review(SignedImplementationReview(
            focus.digest,"b"*64,canonical_digest(new.payload()),
            qa.judge_id,T0,True,True,"0"*64),qa)
        passed=evaluate_original_counterproposal(
            focus,old,new,replay_implementation_digest="b"*64,
            originality_review_passed=True,
            protected_quality_gates_passed=True,authorized=True,
            implementation_review=reviewed,trusted_evaluator=qa)
        self.assertTrue(passed.fulfilled)
        with self.assertRaisesRegex(ThreatRadarError,"signed"):
            evaluate_original_counterproposal(
                focus,old,new,replay_implementation_digest="b"*64,
                originality_review_passed=True,
                protected_quality_gates_passed=True,authorized=True,
                implementation_review=replace(reviewed,build_digest="c"*64),
                trusted_evaluator=qa)
        self.assertEqual(passed.quality_gain_bp,2500)
        self.assertFalse(passed.payload()["game_release_authorized"])

    def ancestral_samples(self,script,*,original_low=5000):
        rows=[]
        for subject,score,low,high in (
            ("rust_labyrinth",6200,6000,6400),
            ("clockwork_vale",6600,6400,6800),
        ):
            for judge in self.judges:
                row=FacetMeasurement(
                    script.digest,subject,judge.judge_id,
                    score,low,high,60,
                    sha256(f"era|{subject}|{judge.judge_id}|{original_low}".encode()).hexdigest(),
                    T0,"0"*64)
                rows.append(sign_facet_measurement(row,judge))
        return tuple(rows)

    def test_deep_evolution_must_outwork_strongest_verified_generation(self):
        scripts,verdicts,_,_=self.scoring()
        npc=next(x for x in scripts if x.facet=="npc_agency")
        ancestor=self.ancestral_samples(npc)
        frontier=evaluate_ancestral_outclassing(
            self.original,self.chain(),scripts,verdicts,ancestor,
            self.judges,as_of=T0,authorized=True)
        focus=next(x for x in frontier.studies if x.facet=="npc_agency")
        self.assertEqual(focus.strongest_predecessor_id,"clockwork_vale")
        self.assertEqual(focus.conservative_ancestry_ceiling_bp,6800)
        self.assertEqual(focus.target_floor_bp,6950)
        self.assertEqual(focus.covered_title_ids,
                         ("clockwork_vale","rust_labyrinth"))
        self.assertFalse(focus.proved_outclassing)
        self.assertFalse(frontier.complete_ancestry_outclassed)
        improved=self.scoring(original_low=7500)[1]
        greater=evaluate_ancestral_outclassing(
            self.original,self.chain(),scripts,improved,ancestor,
            self.judges,as_of=T0,authorized=True)
        self.assertTrue(next(x for x in greater.studies
                             if x.facet=="npc_agency").proved_outclassing)
        self.assertFalse(greater.complete_ancestry_outclassed)
        self.assertEqual(len(greater.studies),102)

    def test_missing_ancestor_or_forged_ancestry_score_cannot_be_winning(self):
        scripts,verdicts,_,_=self.scoring()
        npc=next(x for x in scripts if x.facet=="npc_agency")
        ancestor=self.ancestral_samples(npc)
        fewer=tuple(x for x in ancestor if x.subject_id=="rust_labyrinth")
        verdict=evaluate_ancestral_outclassing(
            self.original,self.chain(),scripts,verdicts,fewer,
            self.judges,as_of=T0,authorized=True)
        focus=next(x for x in verdict.studies if x.facet=="npc_agency")
        self.assertIn("clockwork_vale",focus.missing_title_ids)
        self.assertIn("unmeasured_or_single_source_predecessor",focus.blockers)
        forged=list(ancestor)
        forged[0]=replace(forged[0],score_bp=6300)
        with self.assertRaisesRegex(ThreatRadarError,"untrusted"):
            evaluate_ancestral_outclassing(
                self.original,self.chain(),scripts,verdicts,
                tuple(forged),self.judges,as_of=T0,authorized=True)

    def test_portfolio_composes_independent_source_and_quality_lanes(self):
        with TemporaryDirectory() as d:
            root=Path(d)/"studio"
            GameWorkspace.create(root,authorized=True)
            with CompetitionWatchBook(root) as journal:
                current=review_competitive_frontier(
                    journal,self.original,(self.competitor,),tuple(self.links),
                    self.brief,self.packet,self.db,self.rights,
                    as_of=T0,authorized=True)
            scripts=self.scripts()
            npc=next(s for s in scripts if s.facet=="npc_agency")
            measures,baseline=self.measured(npc)
            dossier=examine_enemy_genre_portfolio(
                current,self.original,(self.competitor,),self.titles,
                self.edges,tuple(self.deep_links),self.deep_brief,
                self.deep_packet,self.deep_db,self.deep_rights,
                platform="pc",measurements={"other_atlas":measures},
                industry_cohorts={"other_atlas":baseline},
                judges=self.judges,authorized=True)
            self.assertEqual(dossier.pending_analyzes,())
            self.assertEqual(len(dossier.enemy_dossiers),1)
            first=dossier.enemy_dossiers[0]
            self.assertEqual(len(first.analysis_scripts),102)
            self.assertEqual(len(first.counterproposals),102)
            self.assertEqual(first.evolution.verified_generations,3)
            self.assertEqual(
                next(v.status for v in first.facet_verdicts if v.facet=="npc_agency"),
                "verified_weakspot")
            self.assertIn("await_deep_signed_evidence:spatial_audio",
                          first.unresolved_research)
            self.assertFalse(first.payload()["actual_game_changes_performed"])


if __name__=="__main__":
    unittest.main()
