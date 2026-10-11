"""Adversarial competitor-watch and conservative original-title superiority tests."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
import sqlite3
import unittest

from skeleton.ai.game_builder.competitive_title_radar import (
    PlannedOriginalTitle,CompetingTitle,RivalSourceLink,RadarStandard,
    ThreatRadarError,inspect_competing_titles,
)
from skeleton.ai.game_builder.competitive_delivery_gate import (
    CORE_AXES,VerifiedQualitySample,OriginalIdentityReview,
    TrustedCompetitionJudge,SuperiorityStandard,
    sign_competitive_sample,sign_identity_review,
    compare_competitive_delivery,ratchet_superiority_standard,
)
from skeleton.ai.game_builder.competitive_watch_book import CompetitionWatchBook
from skeleton.ai.game_builder.competitive_watch_cli import main as watch_cli_main
from skeleton.ai.game_builder.competitive_dragon_recrawl import (
    ReviewedCrawlHistory,plan_dragon_competitor_recrawls,
)
from skeleton.ai.game_builder.competitive_watch_service import (
    compile_original_delivery_work,review_competitive_frontier,
)
from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedKnowledgeStore,ReviewedDocument,ReviewedNote,
)
from skeleton.ai.game_builder.knowledge_rights_bridge import (
    clear_research_for_design,
)
from skeleton.ai.game_builder.rights import RightsLedger,UseKind
from tests.test_game_builder_knowledge_rights_bridge import record,provenance

T0="2026-10-11T12:00:00Z"
T1="2026-10-12T12:00:00Z"
FEATURES=("dynamic_maze","npc_witness")
PILLARS=("branching_world_myth","handcrafted_encounters","quiet_horror")


class CompetitorRadarCases(unittest.TestCase):
    def setUp(self):
        self.original=PlannedOriginalTitle(
            "original_world","Hollow Atlas","a"*64,("pc",),
            ("adventure","simulation"),("explorers","story_players"),
            FEATURES,PILLARS)
        self.competitor=CompetingTitle(
            "other_atlas","Orbital Hearts",("pc",),
            ("adventure","simulation"),("explorers","story_players"))
        self.db=ReviewedKnowledgeStore(":memory:")
        self.addCleanup(self.db.close)
        self.rights=RightsLedger()
        self.links=[]
        self.receipts={}
        for feat in FEATURES:
            for group in ("review_a","review_b"):
                sid=f"{feat}-{group}"
                body=f"Orbital Hearts observed a public {feat} design pattern."
                note=ReviewedNote(
                    note_id="claim_1",mechanic=feat,
                    statement=f"Observed original mechanics {feat}",
                    start=0,end=len(body),stance="supports",
                    confidence_ppm=850000,dependence_group=group)
                doc=ReviewedDocument(
                    owner="game_studio",source_id=sid,
                    source_url=f"https://example.org/research/{sid}",
                    title=f"Orbital Hearts independent review {feat}",
                    text=body,observed_at="2026-10-10T08:00:00Z",
                    license_id="licensed-for-reference",
                    allowed_scopes=("design_reference","research"),
                    reviewer_id="editor-1",approved=True,notes=(note,))
                receipt=self.db.import_document(
                    doc,expected_parent_digest=None,authorized=True)
                self.receipts[sid]=receipt
                self.links.append(RivalSourceLink(
                    self.competitor.title_id,sid,receipt.revision_digest))
                self.rights.register_source(record(
                    source_id=sid,digest=sha256(body.encode()).hexdigest()))
        self.brief=self.db.build_brief(
            "game_studio","dynamic_maze npc_witness",authorized=True,
            min_independent_groups=2)
        self.assertEqual(len(self.brief.citations),4)
        self.packet=clear_research_for_design(
            self.db,self.brief,self.rights,project_id="original_world",
            artifact_digest="a"*64,human_approved=True,authorized=True)

    def radar(self,at=T0,*,rivals=None,links=None,prior=(),standard=None,
              packet=None):
        return inspect_competing_titles(
            self.original,(self.competitor,) if rivals is None else rivals,
            tuple(self.links) if links is None else links,
            self.brief,packet or self.packet,self.db,self.rights,
            as_of=at,authorized=True,prior=prior,
            standard=standard or RadarStandard())

    def test_independent_reviewed_overlap_promotes_rival_to_enemy_not_accusation(self):
        rival,=self.radar()
        self.assertEqual(rival.status,"enemy")
        self.assertEqual(rival.overlap_bp,10000)
        self.assertEqual(rival.overlap_capabilities,FEATURES)
        self.assertEqual(rival.independent_groups,2)
        self.assertEqual(rival.next_review_hours,12)
        self.assertTrue(rival.source_grounded)
        self.assertTrue(rival.payload()["identity_pillars_untouched"])
        self.assertFalse(rival.payload()["accusation_or_hostility"])
        self.assertFalse(rival.payload()["permission_to_copy_competitor_assets"])
        self.assertEqual(self.radar(),(rival,))
        self.assertEqual(self.radar(T1,prior=(rival,))[0].status,"enemy")

    def test_weak_overlap_or_unrelated_game_does_not_get_enemy_badge(self):
        stranger=CompetingTitle(
            "unrelated_title","Starlight Bakery",("pc",),("puzzle",),
            ("family_players",))
        weak=inspect_competing_titles(
            self.original,(self.competitor,stranger),tuple(self.links),
            self.brief,self.packet,self.db,self.rights,
            as_of=T0,authorized=True)
        self.assertEqual(weak[0].status,"enemy")
        self.assertEqual(weak[1].status,"insufficient_evidence")
        self.assertIn("stale_or_missing_competitor_research",weak[1].blockers)

    def test_unsupported_source_or_source_revision_swap_never_marks_enemy(self):
        link=replace(self.links[0],revision_digest="0"*64)
        with self.assertRaisesRegex(ThreatRadarError,"stale"):
            self.radar(links=(link,*self.links[1:]))
        with self.assertRaises(ThreatRadarError):
            self.radar(links=tuple(self.links[:-1]))
        with self.assertRaises(ThreatRadarError):
            self.radar(links=(self.links[0],self.links[0],*self.links[1:]))
        with self.assertRaises(PermissionError):
            inspect_competing_titles(
                self.original,(self.competitor,),tuple(self.links),
                self.brief,self.packet,self.db,self.rights,
                as_of=T0,authorized=False)

    def test_retraction_blocks_previous_wiki_and_competitor_assessment(self):
        source_id=self.links[0].source_id
        doc=ReviewedDocument(
            owner="game_studio",source_id=source_id,
            source_url=f"https://example.org/research/{source_id}",
            title="Orbital Hearts withdrawal",text="",
            observed_at="2026-10-11T08:00:00Z",
            license_id="licensed-for-reference",
            allowed_scopes=("design_reference","research"),
            reviewer_id="editor-1",approved=False,notes=(),status="retracted")
        self.db.import_document(
            doc,expected_parent_digest=self.receipts[source_id].revision_digest,
            authorized=True)
        with self.assertRaises(ValueError):
            self.radar()

    def test_duplicate_rival_id_or_future_wiki_claim_rejected(self):
        with self.assertRaises(ThreatRadarError):
            self.radar(rivals=(self.competitor,self.competitor))
        with self.assertRaises(ThreatRadarError):
            self.radar("2026-10-01T12:00:00Z")
        with self.assertRaises(ThreatRadarError):
            self.radar(T0,prior=self.radar())


class CompetitiveDeliveryCases(CompetitorRadarCases):
    def setUp(self):
        super().setUp()
        self.threat=self.radar()[0]
        self.judges=tuple(TrustedCompetitionJudge(
            f"judge_{i}",bytes([i+1])*32) for i in range(2))
        self.identity_judge=TrustedCompetitionJudge("legal_qa",b"x"*32)
        self.proof=sign_identity_review(OriginalIdentityReview(
            self.original.title_id,"f"*64,self.original.design_digest,
            PILLARS,9200,400,"e"*64,"legal_qa",T0,True,"0"*64),
            self.identity_judge)

    def samples(self,at=T0,*,own=9000,rival=8200,
                protocol="1"*64,changed_protocol=False):
        result=[]
        for axis in sorted(CORE_AXES):
            for ours in (True,False):
                for judge in self.judges:
                    score=own if ours else rival
                    low=score-200
                    high=score+200
                    sample=VerifiedQualitySample(
                        self.original.title_id if ours else self.threat.rival_id,
                        axis,score,low,high,
                        "3"*64 if changed_protocol and ours else protocol,
                        "4"*64,"5"*64,
                        sha256(f"{axis}|{ours}|{judge.judge_id}".encode()).hexdigest(),
                        judge.judge_id,at,80,"pc","0"*64)
                    result.append(sign_competitive_sample(sample,judge))
        return tuple(result)

    def duel(self,samples=None,*,identity=None,as_of=T0,prior=None,
             standard=None,identity_judge=None,judges=None,threat=None):
        return compare_competitive_delivery(
            self.original,threat or self.threat,
            self.samples() if samples is None else samples,
            self.rights,as_of=as_of,authorized=True,
            identity=self.proof if identity is None else identity,
            trusted_identity_reviewer=identity_judge or self.identity_judge,
            trusted_judges=self.judges if judges is None else judges,
            standard=standard or SuperiorityStandard(),preceding=prior)

    def test_confident_original_outperformance_across_all_required_axes(self):
        outcome=self.duel()
        self.assertTrue(outcome.qualified_to_claim_superiority)
        self.assertEqual(len(outcome.quality_results),len(CORE_AXES))
        self.assertTrue(all(x["status"]=="outperformed"
                            for x in outcome.quality_results))
        self.assertFalse(outcome.demands)
        self.assertFalse(outcome.identity_blockers)
        self.assertTrue(outcome.payload()["no_claim_of_consumer_release"])

    def test_poor_polish_creates_prioritized_independent_work_not_clone_tasks(self):
        weak=self.duel(self.samples(own=7200,rival=8200))
        self.assertFalse(weak.qualified_to_claim_superiority)
        self.assertEqual(len(weak.demands),len(CORE_AXES))
        self.assertGreater(weak.demands[0].priority,0)
        self.assertIn("accessibility",{x.axis for x in weak.demands})
        self.assertIn("originality",{x.axis for x in weak.demands})
        self.assertIn("quiet_horror",weak.demands[0].original_direction)
        self.assertNotIn("Orbital Hearts",weak.demands[0].original_direction)
        self.assertTrue(all(d.payload()["no_reimplementation_of_competitor_expression"]
                            for d in weak.demands))
        self.assertEqual(weak.quality_results[0]["status"],"improvement_required")

    def test_hard_guard_blocks_unsigned_benchmarks_or_forged_measurement(self):
        data=list(self.samples())
        data[0]=replace(data[0],score_bp=data[0].score_bp+1)
        with self.assertRaisesRegex(ThreatRadarError,"signature"):
            self.duel(tuple(data))
        with self.assertRaisesRegex(ThreatRadarError,"signature"):
            self.duel(judges=())
        bad=replace(self.proof,measured_originality_bp=9900)
        out=self.duel(identity=bad)
        self.assertFalse(out.qualified_to_claim_superiority)
        self.assertIn("missing_or_forged_independent_originality_signature",
                      out.identity_blockers)

    def test_protocol_population_mismatch_blocks_superiority(self):
        result=self.duel(self.samples(changed_protocol=True))
        self.assertFalse(result.qualified_to_claim_superiority)
        self.assertEqual(len(result.demands),len(CORE_AXES))
        self.assertTrue(all("protocol_scenario_platform_or_cohort_mismatch"
                            in row["blocker_codes"]
                            for row in result.quality_results))

    def test_originality_pillars_and_rights_block_even_strong_scores(self):
        changed=sign_identity_review(replace(
            self.proof,retained_pillars=("branching_world_myth",
                                         "generic_visuals",
                                         "handcrafted_encounters")),self.identity_judge)
        outcome=self.duel(identity=changed)
        self.assertIn("lost_originality_pillars",outcome.identity_blockers)
        self.assertFalse(outcome.qualified_to_claim_superiority)
        stale=replace(self.original,design_digest="d"*64)
        with self.assertRaises(PermissionError):
            compare_competitive_delivery(
                stale,self.threat,self.samples(),self.rights,
                as_of=T0,authorized=False)

    def test_weakening_quality_bar_is_rejected(self):
        with self.assertRaises(ThreatRadarError):
            ratchet_superiority_standard(
                SuperiorityStandard(),
                SuperiorityStandard(competitive_margin_bp=100),
                authorized=True)
        with self.assertRaises(ThreatRadarError):
            SuperiorityStandard(required_axes=("performance",))
        new=ratchet_superiority_standard(
            SuperiorityStandard(),
            SuperiorityStandard(competitive_margin_bp=300),
            authorized=True)
        self.assertEqual(new.competitive_margin_bp,300)

    def test_wide_intervals_are_not_spun_as_commercial_success(self):
        samples=list(self.samples())
        samples=[sign_competitive_sample(
            replace(x,lower_bp=3000,signature="0"*64),
            next(j for j in self.judges if j.judge_id==x.judge_id))
            if x.subject_id==self.original.title_id else x for x in samples]
        outcome=self.duel(tuple(samples))
        self.assertFalse(outcome.qualified_to_claim_superiority)
        self.assertEqual(len(outcome.demands),len(CORE_AXES))


class CompetitiveWatchCases(CompetitiveDeliveryCases):
    def test_journal_records_enemy_changes_and_detects_history_tampering(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/"my_games"
            GameWorkspace.create(root,authorized=True)
            with CompetitionWatchBook(root) as watch:
                first=watch.record(self.original,(self.threat,),
                                   (self.duel(),),as_of=T0,authorized=True)
                self.assertEqual(first.new_enemies,("other_atlas",))
                self.assertEqual(first.still_enemies,())
                self.assertEqual(first.recorded_reports,1)
                self.assertEqual(first.next_review_at,"2026-10-12T00:00:00Z")
                self.assertEqual(first.pending_delivery_axes,())
                second_assessment=self.radar(T1,prior=(self.threat,))[0]
                second_report=self.duel(
                    self.samples(at=T1,own=7300),as_of=T1,threat=second_assessment,
                    prior=self.duel())
                second=watch.record(self.original,(second_assessment,),
                                    (second_report,),as_of=T1,authorized=True)
                self.assertEqual(second.still_enemies,("other_atlas",))
                self.assertEqual(len(second.pending_delivery_axes),len(CORE_AXES))
                self.assertEqual(len(watch.history(self.original.title_id,authorized=True)),2)
                with self.assertRaises(ThreatRadarError):
                    watch.record(self.original,(second_assessment,),as_of=T1,authorized=True)
            with CompetitionWatchBook(root) as watch:
                self.assertEqual(len(watch.history(self.original.title_id,authorized=True)),2)
                watch.db.execute(
                    "UPDATE competitive_watch_events SET digest=? "
                    "WHERE original_id=? AND revision=0",
                    ("0"*64,self.original.title_id))
                with self.assertRaisesRegex(ThreatRadarError,"digest"):
                    watch.history(self.original.title_id,authorized=True)
                with self.assertRaises(ThreatRadarError):
                    watch.record(self.original,(self.threat,),as_of="2026-10-13T12:00:00Z",
                                 authorized=True)

    def test_duplicate_scope_or_mismatched_delivery_is_not_written(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)/"workspace"
            GameWorkspace.create(root,authorized=True)
            with CompetitionWatchBook(root) as watch:
                with self.assertRaises(ThreatRadarError):
                    watch.record(self.original,(self.threat,self.threat),
                                 as_of=T0,authorized=True)
                another=replace(self.duel(),rival_id="wrong_rival")
                with self.assertRaises(ThreatRadarError):
                    watch.record(self.original,(self.threat,), (another,),
                                 as_of=T0,authorized=True)
                self.assertEqual(watch.history(self.original.title_id,authorized=True),())


class CompleteRadarIntegrationCases(CompetitiveDeliveryCases):
    def test_evaluate_live_wiki_write_snapshot_then_ratchet_next_review(self):
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/"studio"
            GameWorkspace.create(path,authorized=True)
            with CompetitionWatchBook(path) as journal:
                first=review_competitive_frontier(
                    journal,self.original,(self.competitor,),tuple(self.links),
                    self.brief,self.packet,self.db,self.rights,as_of=T0,
                    measurements={self.competitor.title_id:self.samples(own=7200)},
                    identity=self.proof,
                    trusted_identity_reviewer=self.identity_judge,
                    trusted_judges=self.judges,
                    authorized=True)
                self.assertEqual(first.watch_delta.new_enemies,("other_atlas",))
                self.assertEqual(len(first.work_orders),len(CORE_AXES))
                self.assertEqual(
                    first.payload()["enemy_rivals_are_internal_benchmarks_only"],True)
                self.assertTrue(all(
                    x.protected_original_pillars==PILLARS for x in first.work_orders))
                self.assertEqual(first.work_orders[0].minimum_quality_floor_bp,8550)
                self.assertEqual(len(journal.history(self.original.title_id,authorized=True)),1)
                improved=review_competitive_frontier(
                    journal,self.original,(self.competitor,),tuple(self.links),
                    self.brief,self.packet,self.db,self.rights,as_of=T1,
                    measurements={self.competitor.title_id:self.samples(
                        at=T1,own=9100)},
                    identity=self.proof,
                    trusted_identity_reviewer=self.identity_judge,
                    trusted_judges=self.judges,
                    authorized=True)
                self.assertEqual(improved.watch_delta.still_enemies,("other_atlas",))
                self.assertFalse(improved.work_orders)
                self.assertTrue(improved.reports[0].qualified_to_claim_superiority)
                self.assertTrue(all(
                    row["target_floor_bp"]>=8550
                    for row in improved.reports[0].quality_results))
                self.assertEqual(len(journal.history(self.original.title_id,authorized=True)),2)

    def test_without_signed_quality_scenario_still_creates_work_not_fake_win(self):
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/"studio"
            GameWorkspace.create(path,authorized=True)
            with CompetitionWatchBook(path) as journal:
                scan=review_competitive_frontier(
                    journal,self.original,(self.competitor,),tuple(self.links),
                    self.brief,self.packet,self.db,self.rights,as_of=T0,
                    authorized=True)
                self.assertEqual(scan.assessments[0].status,"enemy")
                self.assertEqual(len(scan.work_orders),len(CORE_AXES))
                self.assertFalse(scan.reports[0].qualified_to_claim_superiority)
                self.assertIn("no_independent_original_identity_review",
                              scan.reports[0].identity_blockers)
                self.assertTrue(all(d.blocked_reason is not None
                                    for d in scan.reports[0].demands))
                self.assertEqual(scan.watch_delta.recorded_reports,1)

    def test_untrusted_scores_abort_without_partial_journal_commit(self):
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/"studio"
            GameWorkspace.create(path,authorized=True)
            with CompetitionWatchBook(path) as journal:
                evidence=list(self.samples())
                evidence[0]=replace(evidence[0],lower_bp=0)
                with self.assertRaisesRegex(ThreatRadarError,"signature"):
                    review_competitive_frontier(
                        journal,self.original,(self.competitor,),
                        tuple(self.links),self.brief,self.packet,
                        self.db,self.rights,as_of=T0,
                        measurements={self.competitor.title_id:tuple(evidence)},
                        identity=self.proof,
                        trusted_identity_reviewer=self.identity_judge,
                        trusted_judges=self.judges,authorized=True)
                self.assertEqual(journal.history(self.original.title_id,authorized=True),())

    def test_duplicate_rival_pressure_merges_highest_requirements(self):
        first=self.duel(self.samples(own=7000,rival=8200))
        other=replace(first,rival_id="other_benchmark")
        orders=compile_original_delivery_work(
            self.original,(first,other),authorized=True)
        self.assertEqual(len(orders),len(CORE_AXES))
        self.assertTrue(all(x.benchmark_ids==("other_atlas","other_benchmark")
                            for x in orders))
        self.assertTrue(all(x.minimum_quality_floor_bp==8550 for x in orders))
        self.assertTrue(all(x.payload()["requires_human_authored_solution"]
                            for x in orders))
        with self.assertRaises(PermissionError):
            compile_original_delivery_work(self.original,(first,),authorized=False)


class WatchCLIIntegrationCases(CompetitiveDeliveryCases):
    def test_cli_status_due_and_work_queue_are_grounded_in_saved_snapshots(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)/"studio"
            GameWorkspace.create(root,authorized=True)
            with CompetitionWatchBook(root) as journal:
                journal.record(self.original,(self.threat,),
                               (self.duel(self.samples(own=7000)),),
                               as_of=T0,authorized=True)
            prefix=["--root",str(root),"--original-id","original_world",
                    "--trusted-local-operator"]
            stdout=StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(watch_cli_main(["status",*prefix]),0)
            snapshot=json.loads(stdout.getvalue())
            self.assertEqual(snapshot["enemy_ids"],["other_atlas"])
            self.assertEqual(snapshot["history_length"],1)
            self.assertFalse(snapshot["background_monitor_running"])
            stdout=StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(watch_cli_main(["due",*prefix,
                                                 "--at","2026-10-11T18:00:00Z"]),0)
            self.assertFalse(json.loads(stdout.getvalue())["review_due"])
            stdout=StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(watch_cli_main(["due",*prefix,
                                                 "--at","2026-10-12T00:00:00Z"]),0)
            self.assertTrue(json.loads(stdout.getvalue())["review_due"])
            stdout=StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(watch_cli_main(["demands",*prefix]),0)
            tasks=json.loads(stdout.getvalue())["outstanding_work"]
            self.assertEqual(len(tasks),len(CORE_AXES))
            self.assertTrue(all("handcrafted_encounters" in x["original_direction"]
                                for x in tasks))
            errors=StringIO()
            with redirect_stderr(errors):
                self.assertEqual(watch_cli_main(
                    ["status","--root",str(root),"--original-id","original_world"]),2)
            self.assertIn("PermissionError",errors.getvalue())



class DragonCompetitorRecrawlCases(CompetitorRadarCases):
    def histories(self):
        return tuple(ReviewedCrawlHistory(
            link.source_id,1791622800,9000,0)
            for link in self.links)

    def plan(self,*,consent=True,host_safe=True,links=None,histories=None,
             time="2026-10-13T12:00:00Z",packet=None):
        return plan_dragon_competitor_recrawls(
            self.db,self.brief,packet or self.packet,self.rights,
            self.radar(),tuple(self.links) if links is None else links,
            self.histories() if histories is None else histories,
            as_of=time,authorized=True,crawl_consent=consent,
            host_safe_to_work=host_safe)

    def test_native_dragon_due_enemy_sources_are_proposed_not_automatically_crawled(self):
        plan=self.plan()
        self.assertEqual(len(plan.orders),4)
        self.assertTrue(all(x.due for x in plan.orders))
        self.assertEqual(len(plan.eligible_for_host_dispatch),4)
        self.assertEqual(plan.payload()["actual_network_fetches"],0)
        self.assertEqual(plan.payload()["actual_os_background_jobs_created"],0)
        self.assertTrue(all(
            not order.payload()["can_crawl_without_external_host_approval"]
            and not order.payload()["new_verified_knowledge_revision_created"]
            for order in plan.orders))
        self.assertEqual(plan.owner,"game_studio")

    def test_busy_thermal_or_missing_consent_preempts_without_claiming_acquisition(self):
        for consent,safe,blocked in (
            (False,True,"no_crawl_consent"),
            (True,False,"host_busy_or_thermal_limit"),
            (False,False,"no_crawl_consent"),
        ):
            with self.subTest(consent=consent,safe=safe):
                queue=self.plan(consent=consent,host_safe=safe)
                self.assertEqual(queue.eligible_for_host_dispatch,())
                self.assertIn(blocked,queue.dispatch_deferred_reasons)
                self.assertEqual(queue.payload()["actual_knowledge_promotions"],0)

    def test_stale_versions_future_changes_and_partial_sources_rejected(self):
        mismatch=replace(self.links[0],revision_digest="c"*64)
        with self.assertRaises(ThreatRadarError):
            self.plan(links=(mismatch,*self.links[1:]))
        with self.assertRaises(ThreatRadarError):
            self.plan(histories=self.histories()[:-1])
        with self.assertRaises(ThreatRadarError):
            self.plan(time="2026-10-01T12:00:00Z")
        with self.assertRaises(ThreatRadarError):
            self.plan(histories=tuple(replace(
                h,last_changed_epoch=1999999999) for h in self.histories()))
        with self.assertRaises(PermissionError):
            plan_dragon_competitor_recrawls(
                self.db,self.brief,self.packet,self.rights,
                self.radar(),tuple(self.links),self.histories(),
                as_of=T0,authorized=False,
                crawl_consent=True,host_safe_to_work=True)


if __name__=="__main__":
    unittest.main()
