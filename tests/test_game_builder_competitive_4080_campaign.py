"""Deterministic 4,080/12,240 campaign, no-overlap, no fake training or PDF loss."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.competitive_4080_scrutiny import (
    build_scrutiny_campaign,audit_scrutiny_campaign,
    CampaignCatalog,SIZES,TIMES,ProbeEvidenceReceipt,
)
from skeleton.ai.game_builder.competitive_4080_role_reviews import (
    AgentProbeJudgment,AgentCampaignRoundReport,sign_campaign_role_report,
    audit_council_scrutiny,
)
from skeleton.ai.game_builder.competitive_27page_pdf_campaign import (
    publish_27page_campaign,
)
from skeleton.ai.game_builder.competitive_27page_approval import (
    inspect_27page_packet,sign_user_27page_decision,
)
from skeleton.ai.game_builder.competitive_title_radar import ThreatRadarError
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.competitive_tri_council import ROLES
from tests.test_game_builder_competitive_council_pdfs import CompetitiveUserCouncilCases


class IntensiveCampaignCases(CompetitiveUserCouncilCases):
    def full_catalog(self,plan):
        return build_scrutiny_campaign(
            self.original.title_id,self.original.design_digest,
            tuple(x.research.digest for x in plan.rounds),
            authorized=True)

    def synthetic_unmeasured_reports(self,plan,catalog):
        # Strict, source-grounded ANNEX TEST DATA, not real model inference.
        # Every judgment is UNMEASURED, never an invented industry weakness.
        reports=[]
        keys=tuple(zip(ROLES,self.reviewers))
        for round_no in (1,2,3):
            probes=[x for x in catalog.probes if x.round_number==round_no]
            for role,signer in keys:
                judgments=tuple(AgentProbeJudgment(
                    p.digest,"not_yet_tested",0,None,
                    f"{role.upper()} historical uncertainty for {p.facet} "
                    f"under the independent lens {p.lens}. {p.hypothesis[:180]}",
                    f"Original work in {p.domain}: {p.integrity_rule[:240]} "
                    "Do not borrow competitor expression or mistake hypotheses for scores.",
                    f"Independent verification must replay {p.intervention[:250]} "
                    f"Measure {p.measurement[:260]} "
                    "and preserve a signed negative control.",
                ) for p in probes)
                report=AgentCampaignRoundReport(
                    role,round_no,plan.epoch,catalog.digest,
                    plan.rounds[round_no-1].research.digest,
                    judgments,self.critique.digest,(),
                    f"The {role} system MUST assess every {round_no} "
                    "round experiment individually with matched current-build "
                    "and independent source evidence. This synthetic test "
                    "produces no witnessed experiment or market success.",
                    plan.rounds[round_no-1].research.researched_at,
                    signer.judge_id,"0"*64)
                reports.append(sign_campaign_role_report(report,signer))
        return tuple(reports),keys

    def test_4080_unique_probes_across_three_nonoverlapping_narrative_times(self):
        plan,_=self.complete_battle()
        cat=self.full_catalog(plan)
        self.assertEqual(len(cat.probes),4080)
        self.assertEqual(cat.payload()["per_round"],list(SIZES))
        self.assertEqual(cat.payload()["total_role_probe_obligations"],12240)
        self.assertEqual(len({p.digest for p in cat.probes}),4080)
        self.assertEqual(len({p.protocol_digest for p in cat.probes}),4080)
        self.assertEqual(len({p.probe_id for p in cat.probes}),4080)
        by_round=[{p.probe_id for p in cat.probes if p.round_number==i} for i in (1,2,3)]
        self.assertFalse(by_round[0]&by_round[1])
        self.assertFalse(by_round[1]&by_round[2])
        self.assertFalse(by_round[0]&by_round[2])
        self.assertEqual(
            {p.time_window for p in cat.probes},set(TIMES))
        self.assertTrue(all(not p.tested for p in cat.probes))
        incomplete=audit_scrutiny_campaign(cat,(),authorized=True)
        self.assertEqual(incomplete.per_round_tested,(0,0,0))
        self.assertEqual(incomplete.per_round_missing,SIZES)
        self.assertFalse(incomplete.promotion_eligible)
        with self.assertRaises(ThreatRadarError):
            build_scrutiny_campaign(self.original.title_id,
                                    self.original.design_digest,
                                    ("a"*64,)*3,authorized=True)

    def test_all_nine_role_reports_are_exact_and_cannot_claim_unrun_probes(self):
        plan,_=self.complete_battle()
        cat=self.full_catalog(plan)
        reports,keys=self.synthetic_unmeasured_reports(plan,cat)
        verdict=audit_council_scrutiny(
            cat,plan,reports,keys,authorized=True)
        self.assertEqual(verdict.total_reviewed_obligations,12240)
        self.assertEqual(verdict.measured_obligations,0)
        self.assertEqual(verdict.unresolved_obligations,12240)
        self.assertTrue(verdict.all_nine_reports_attested)
        self.assertFalse(verdict.evidence_based_superiority)
        with self.assertRaises(ThreatRadarError):
            audit_council_scrutiny(cat,plan,reports[:-1],keys,authorized=True)
        forged=list(reports)
        forged[0]=replace(
            forged[0],independent_review_notes=forged[0].independent_review_notes+
            " Tampered external peer review after the expected signature.")
        with self.assertRaises(ThreatRadarError):
            audit_council_scrutiny(cat,plan,tuple(forged),keys,authorized=True)
        # A duplicate role bound to same signer cannot steal another model.
        stolen=list(keys)
        stolen[0]=("adversarial",stolen[1][1])
        with self.assertRaises(ThreatRadarError):
            audit_council_scrutiny(cat,plan,reports,tuple(stolen),authorized=True)

    def test_exact_27_page_packet_and_full_machine_probes_are_immutable(self):
        plan,_=self.complete_battle()
        cat=self.full_catalog(plan)
        reports,keys=self.synthetic_unmeasured_reports(plan,cat)
        with TemporaryDirectory() as folder:
            root=Path(folder)/"studio"
            GameWorkspace.create(root,authorized=True)
            packet=publish_27page_campaign(
                root,plan,self.critique,cat,reports,keys,authorized=True)
            self.assertEqual(packet.total_unique_pages,27)
            directory=Path(packet.folder)
            self.assertEqual(len(list(directory.glob("*_full_9pages.pdf"))),3)
            self.assertEqual(len(list(directory.glob("*_round_*.pdf"))),9)
            for role in ROLES:
                file=directory/(role+"_full_9pages.pdf")
                self.assertEqual(file.read_bytes().count(b"/Type /Page /Parent"),9)
            for file in directory.glob("*_round_*.pdf"):
                self.assertEqual(file.read_bytes().count(b"/Type /Page /Parent"),3)
            self.assertEqual(sum(
                1 for _ in (directory/"full_probe_catalog.jsonl").open()),4080)
            self.assertEqual(sum(
                1 for _ in (directory/"all_role_probe_judgments.jsonl").open()),12240)
            manifest=inspect_27page_packet(root,packet.digest,authorized=True)
            self.assertEqual(manifest["review_obligations"],12240)
            self.assertEqual(manifest["empirical_measurements_verified"],0)
            self.assertFalse(manifest["approved_by_user"])
            consent=sign_user_27page_decision(
                root,packet.digest,decision="revise",
                feedback="Missing actual signed player replays and contemporary "
                         "third party title comparisons on each original game facet.",
                signed_at="2026-10-20T12:00:00Z",
                user_session_key=b"s"*32,
                user_context_digest="d"*64,
                reviewed_roles=tuple(sorted(ROLES)),authorized=True)
            self.assertEqual(consent.decision,"revise")
            with self.assertRaises(ThreatRadarError):
                sign_user_27page_decision(
                    root,packet.digest,decision="approve",feedback="",
                    signed_at="2026-10-20T12:00:00Z",
                    user_session_key=b"s"*32,
                    user_context_digest="d"*64,
                    reviewed_roles=tuple(sorted(ROLES)),authorized=True)
            target=directory/"dragon_round_2.pdf"
            target.write_bytes(target.read_bytes()+b"% tampered")
            with self.assertRaises(ThreatRadarError):
                inspect_27page_packet(root,packet.digest,authorized=True)


if __name__=="__main__":
    unittest.main()
