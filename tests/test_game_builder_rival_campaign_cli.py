"""Real executable rival work campaigns, no-copy gates and local CLI custody."""
from __future__ import annotations

from contextlib import redirect_stdout,redirect_stderr
from dataclasses import replace
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.rival_convergence_observatory import (
    CompetitiveError,DeliveryVerification,QualityMeasurement,
    evaluate_convergence,
)
from skeleton.ai.game_builder.rival_delivery_campaign import (
    STAGES,TaskEvidence,plan_competitive_campaign,
    reconcile_competitive_campaign,
)
from skeleton.ai.game_builder.rival_watch_cli import main
from tests.test_game_builder_rival_convergence import (
    original_plan,competitor,notice,H,T2,q,
)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.plan=original_plan()
        self.rival=competitor()
        self.signals=(notice("a",("causal-npc-memory",)),
                      notice("b",("witness-quest-branching",)),
                      notice("c",("era-adaptive-npcs",)))
        self.benchmarks=tuple(value for axis,original,rival in (
            ("narrative_coherence",77,85),
            ("replayability",70,79),
            ("performance",80,83),
        ) for value in (q(self.plan.project_id,axis,original),
                        q(self.rival.title_id,axis,rival)))
        self.report=evaluate_convergence(
            self.plan,self.rival,self.signals,self.benchmarks,authorized=True)
        self.campaign=plan_competitive_campaign(
            self.plan,self.report,authorized=True)

    def samples(self,*,approved=True):
        return tuple(TaskEvidence(
            task_id=t.task_id,evidence_digest=H("proof-"+t.task_id),
            actor_id=t.lane.replace("_","-"),
            original_game_digest=H("actual original playable game"),
            approved_by_independent_reviewer=approved,
            protected_identity_digest=self.plan.distinctive_signature_digest)
            for t in self.campaign.tasks)

    def delivery(self,*,rights=True):
        return DeliveryVerification(
            project_id=self.plan.project_id,plan_digest=self.plan.digest,
            protected_identity_digest=self.plan.distinctive_signature_digest,
            independently_reviewed=True,protected_axes_passed=True,
            originality_review_passed=True,rights_review_passed=rights,
            measurements=(
                q(self.plan.project_id,"narrative_coherence",93),
                q(self.plan.project_id,"replayability",89),
                q(self.plan.project_id,"performance",91)),
            new_gameplay_evidence_digest=H("new replay after original full build"))

    def test_six_substantive_work_stages_for_each_competitor_axis(self):
        self.assertEqual(len(self.report.orders),4)
        self.assertEqual(len(self.campaign.tasks),24)
        self.assertEqual(len(STAGES),6)
        self.assertEqual(len(self.campaign.open_orders),4)
        self.assertEqual(len({t.task_id for t in self.campaign.tasks}),24)
        self.assertTrue(all(t.source_report_digest==self.report.digest
                            for t in self.campaign.tasks))
        self.assertTrue(all(t.protected_identity_digest==
                            self.plan.distinctive_signature_digest
                            for t in self.campaign.tasks))
        self.assertEqual(plan_competitive_campaign(
            self.plan,self.report,authorized=True).digest,self.campaign.digest)
        with self.assertRaises(PermissionError):
            plan_competitive_campaign(self.plan,self.report,authorized=False)

    def test_no_shortcut_from_unreviewed_receipts_to_fake_release(self):
        missing=self.samples()[:-1]
        outcome=reconcile_competitive_campaign(
            self.plan,self.report,self.campaign,missing,
            self.delivery(),authorized=True)
        self.assertEqual(outcome["status"],"work_required")
        self.assertEqual(outcome["incomplete_task_count"],1)
        self.assertTrue(any("unfinished:" in b for b in outcome["blockers"]))
        rejected=reconcile_competitive_campaign(
            self.plan,self.report,self.campaign,self.samples(approved=False),
            self.delivery(),authorized=True)
        self.assertEqual(rejected["accepted_task_receipts"],0)
        self.assertEqual(rejected["status"],"work_required")
        with self.assertRaisesRegex(CompetitiveError,"unknown"):
            reconcile_competitive_campaign(
                self.plan,self.report,self.campaign,
                self.samples()[:-1]+(replace(
                    self.samples()[-1],task_id=H("nonnative-work-task")),),
                self.delivery(),authorized=True)
        badrights=reconcile_competitive_campaign(
            self.plan,self.report,self.campaign,self.samples(),
            self.delivery(rights=False),authorized=True)
        self.assertIn("release:rights_review_passed",badrights["blockers"])

    def test_actual_campaign_can_be_reconciled_but_never_auto_publishes(self):
        result=reconcile_competitive_campaign(
            self.plan,self.report,self.campaign,self.samples(),
            self.delivery(),authorized=True)
        self.assertEqual(result["status"],"qualified_for_operator_release_decision")
        self.assertEqual(result["accepted_task_receipts"],24)
        self.assertEqual(result["blockers"],[])
        self.assertFalse(result["automatic_release"])
        self.assertNotEqual(result["original_signature_unchanged"],
                            self.rival.title_id)
        forged=replace(self.campaign,protected_identity_digest=H("stolen look"))
        with self.assertRaisesRegex(CompetitiveError,"modified"):
            reconcile_competitive_campaign(
                self.plan,self.report,forged,self.samples(),
                self.delivery(),authorized=True)
        with self.assertRaises(PermissionError):
            reconcile_competitive_campaign(
                self.plan,self.report,self.campaign,self.samples(),
                self.delivery(),authorized=False)

    def test_protected_plan_revisions_never_retroactively_transfer_campaign(self):
        altered=replace(self.plan,plan_revision=H("future rewrite"))
        with self.assertRaisesRegex(CompetitiveError,"redirect|identity"):
            plan_competitive_campaign(altered,self.report,authorized=True)
        watch=evaluate_convergence(
            self.plan,self.rival,(self.signals[0],),authorized=True)
        low=plan_competitive_campaign(self.plan,watch,authorized=True)
        self.assertEqual(low.tasks,())
        self.assertEqual(low.open_orders,())


class OperatorCLITests(unittest.TestCase):
    @staticmethod
    def run_cli(*args):
        stdout,stderr=StringIO(),StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            code=main(list(args))
        return code,stdout.getvalue(),stderr.getvalue()

    def test_opt_in_config_stays_offline_and_records_no_fake_results(self):
        with TemporaryDirectory() as directory:
            config=Path(directory)/"watchlist.json"
            config.write_text(json.dumps(dict(
                schema="skeleton.game_builder.competitor_watch_config.v1",
                polling_enabled=False,titles=[])),encoding="utf-8")
            code,stdout,error=self.run_cli("poll","--config",str(config))
            self.assertEqual(code,0,error)
            observed=json.loads(stdout)
            self.assertEqual(observed["signals"],[])
            self.assertEqual(observed["title_ids"],[])
            config.write_text(json.dumps(dict(
                schema="skeleton.game_builder.competitor_watch_config.v1",
                polling_enabled=True,titles=[competitor().payload()])),encoding="utf-8")
            code,_,err=self.run_cli("poll","--config",str(config))
            self.assertEqual(code,2)
            self.assertIn("explicit network permission",err)
            config.write_text('{"schema":"x","schema":"y","titles":[]}',encoding="utf-8")
            code,_,err=self.run_cli("poll","--config",str(config))
            self.assertEqual(code,2)
            self.assertIn("repeated key",err)

    def test_campaign_cli_requires_complete_original_evidence(self):
        plan=original_plan()
        rival=competitor()
        signals=(notice("a",("causal-npc-memory",)),
                 notice("b",("witness-quest-branching",)),
                 notice("c",("era-adaptive-npcs",)))
        report=evaluate_convergence(plan,rival,signals,authorized=True)
        with TemporaryDirectory() as folder:
            filepath=Path(folder)/"rival-campaign.json"
            filepath.write_text(json.dumps({
                "schema":"skeleton.game_builder.competitive_campaign_request.v1",
                "plan":plan.payload(),"report":report.payload()}),encoding="utf-8")
            code,_,err=self.run_cli("campaign","--evidence",str(filepath))
            self.assertEqual(code,2)
            self.assertIn("authenticated creators",err)
            code,result,err=self.run_cli(
                "campaign","--evidence",str(filepath),"--trusted-reviewer")
            self.assertEqual(code,0,err)
            campaign=json.loads(result)
            self.assertEqual(len(campaign["tasks"]),24)
            proof={
                "schema":"skeleton.game_builder.competitive_campaign_reconciliation_request.v1",
                "plan":plan.payload(),"report":report.payload(),
                "campaign":campaign,"task_evidence":[],
                "delivery":None,
            }
            filepath.write_text(json.dumps(proof),encoding="utf-8")
            code,out,err=self.run_cli("reconcile","--evidence",str(filepath),
                                      "--trusted-reviewer")
            self.assertEqual(code,0,err)
            pending=json.loads(out)
            self.assertEqual(pending["status"],"work_required")
            self.assertEqual(pending["incomplete_task_count"],24)
            self.assertIn("independent_release_evidence_not_submitted",
                          pending["blockers"])
            proof["campaign"]["tasks"]=proof["campaign"]["tasks"][:-1]
            filepath.write_text(json.dumps(proof),encoding="utf-8")
            code,_,err=self.run_cli("reconcile","--evidence",str(filepath),
                                    "--trusted-reviewer")
            self.assertEqual(code,2)
            self.assertIn("altered",err)

    def test_operator_analysis_ledger_and_delivery_are_verifiable(self):
        plan=original_plan()
        title=competitor()
        signals=(notice("a",("causal-npc-memory",)),
                 notice("b",("witness-quest-branching",)),
                 notice("c",("era-adaptive-npcs",)))
        with TemporaryDirectory() as folder:
            review=Path(folder)/"review.json"
            review.write_text(json.dumps({
                "schema":"skeleton.game_builder.competitor_analysis_request.v1",
                "plan":plan.payload(),"rival":title.payload(),
                "signals":[s.payload() for s in signals],
                "benchmarks":[]}),encoding="utf-8")
            ledger=Path(folder)/"journal.db"
            code,_,err=self.run_cli("analyze","--evidence",str(review))
            self.assertEqual(code,2)
            self.assertIn("authentic source review",err)
            code,out,err=self.run_cli(
                "analyze","--evidence",str(review),"--trusted-reviewer",
                "--ledger",str(ledger))
            self.assertEqual(code,0,err)
            report=json.loads(out)
            self.assertEqual(report["status"],"enemy")
            self.assertIn("audit_head",report)
            from skeleton.ai.game_builder.rival_convergence_observatory import CompetitiveLedger
            with CompetitiveLedger(ledger) as storage:
                self.assertEqual(storage.history()[1],report["audit_head"])
            # A completed title can still not pass with missing benchmarks.
            from skeleton.ai.game_builder.rival_convergence_observatory import (
                ConvergenceReport,DeliveryOrder)
            raw={k:v for k,v in report.items() if k not in (
                "audit_head","report_digest","schema",
                "strategic_enemy_label_is_not_an_accusation",
                "no_competitor_expression_or_assets_copied",
                "protected_original_identity_unchanged",
                "competitor_scores_are_not_inferred_from_news",
                "automatic_delivery_or_model_promotion")}
            raw["orders"]=tuple(DeliveryOrder(**o) for o in raw["orders"])
            raw["convergent_features"]=tuple(raw["convergent_features"])
            raw["watch_reasons"]=tuple(raw["watch_reasons"])
            original=ConvergenceReport(**raw).payload()
            verify=Path(folder)/"delivery.json"
            verify.write_text(json.dumps(dict(
                schema="skeleton.game_builder.competitor_delivery_request.v1",
                plan=plan.payload(),report=original,delivery={
                    "project_id":plan.project_id,
                    "plan_digest":plan.digest,
                    "protected_identity_digest":plan.distinctive_signature_digest,
                    "independently_reviewed":True,
                    "protected_axes_passed":True,
                    "originality_review_passed":True,
                    "rights_review_passed":True,
                    "measurements":[],
                    "new_gameplay_evidence_digest":H("fresh actually built world"),
                })),encoding="utf-8")
            code,out,err=self.run_cli(
                "signoff","--evidence",str(verify),"--trusted-reviewer")
            self.assertEqual(code,0,err)
            self.assertEqual(json.loads(out)["status"],"blocked")
            forged=json.loads(verify.read_text())
            forged["report"]["status"]="unconfirmed"
            verify.write_text(json.dumps(forged))
            code,out,err=self.run_cli(
                "signoff","--evidence",str(verify),"--trusted-reviewer")
            self.assertEqual(code,2)
            self.assertIn("tampered",err)


if __name__=="__main__":
    unittest.main()
