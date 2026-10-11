"""Adversarial regression of strategic rival competition and safe live feeds."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.rival_convergence_observatory import (
    CompetitiveError,DesignFacet,PlannedTitle,CompetitorTitle,
    PublicSignal,QualityMeasurement,EnemyPolicy,DeliveryVerification,
    evaluate_convergence,verify_delivery,CompetitiveLedger,
)
from skeleton.ai.game_builder.rival_public_monitor import (
    MonitoringError,poll_public_steam_titles,
)

H=lambda v:sha256(v.encode()).hexdigest()
T0="2026-09-01T09:00:00Z"
T1="2026-10-01T12:00:00Z"
T2="2026-10-02T12:00:00Z"


def original_plan():
    return PlannedTitle(
        project_id="original-aether",original_title="Aether Cartographers",
        registered_at=T0,plan_revision=H("original-commit"),
        original_identity_pillars=(
            "recursive-star-maps","kind-mycology",
            "causal-weather-fables"),
        distinctive_signature_digest=H("authorial original identity"),
        facets=(
            DesignFacet("causal-npc-memory","narrative_coherence",5,H("own causality")),
            DesignFacet("witness-quest-branching","replayability",4,H("own quests")),
            DesignFacet("era-adaptive-npcs","performance",3,H("own era density")),
            DesignFacet("cozy-original-aesthetic","aesthetic_coherence",2,H("own style")),
        ),
    )


def competitor():
    return CompetitorTitle("competing-cosmos","Cosmos Revisited",
                           "indie-company","https://store.steampowered.com/app/1234/",
                           steam_app_id=1234)


def notice(number,features,*,published=T1,group=None,reviewed=True):
    return PublicSignal(
        title_id="competing-cosmos",signal_id=f"notice-{number}",
        source_url=f"https://steamcommunity.com/app/1234/event/{number}",
        source_digest=H("public-document-"+number),
        published_at=published,observed_at=T2,
        source_group=group or f"independent-review-{number}",
        signal_kind="independent_review",
        reviewed_feature_ids=tuple(features) if reviewed else (),
        review_evidence_digest=H("review-evidence-"+number) if reviewed else None,
        reviewer_id=f"reviewer-{number}" if reviewed else None,
    )


def q(title,axis,score,*,profile="shared-benchmark",evaluator="independent-lab"):
    return QualityMeasurement(
        title,axis,score,H(profile),evaluator,H(title+axis+str(score)),
        150,T2,True)


class ConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.plan=original_plan()
        self.rival=competitor()
        self.signals=(
            notice("a",("causal-npc-memory",)),
            notice("b",("witness-quest-branching",)),
            notice("c",("era-adaptive-npcs",)),
        )

    def evaluate(self,*,signals=None,benchmarks=(),previous=None):
        return evaluate_convergence(
            self.plan,self.rival,self.signals if signals is None else signals,
            benchmarks,previous=previous,authorized=True)

    def test_two_independent_postplan_features_escalate_internal_enemy(self):
        report=self.evaluate()
        self.assertEqual(report.status,"enemy")
        self.assertEqual(report.overlap,round(12/14,6))
        self.assertEqual(report.independent_evidence_groups,3)
        self.assertEqual(report.convergent_features,
                         ("causal-npc-memory","era-adaptive-npcs",
                          "witness-quest-branching"))
        self.assertEqual({o.axis for o in report.orders},
                         {"narrative_coherence","replayability",
                          "performance","originality"})
        self.assertTrue(all(o.protected_identity_digest==
                            self.plan.distinctive_signature_digest
                            for o in report.orders))
        self.assertTrue(all(o.kind=="commission_comparable_benchmark"
                            for o in report.orders if o.axis!="originality"))
        self.assertIn("original differentiation",next(
            o.requirement for o in report.orders
            if o.axis=="originality").lower())
        self.assertTrue(report.payload()["strategic_enemy_label_is_not_an_accusation"])
        self.assertFalse(report.payload()["automatic_delivery_or_model_promotion"])
        self.assertEqual(report.digest,self.evaluate().digest)

    def test_press_headlines_and_same_publisher_cannot_fake_independent_convergence(self):
        only_meta=tuple(replace(x,reviewed_feature_ids=(),
                                review_evidence_digest=None,reviewer_id=None)
                        for x in self.signals)
        self.assertEqual(self.evaluate(signals=only_meta).status,"unconfirmed")
        same_group=tuple(replace(x,source_group="one-newsroom") for x in self.signals)
        response=self.evaluate(signals=same_group)
        self.assertEqual(response.status,"watch")
        self.assertIn("insufficient_independent_postplan_sources",
                      response.watch_reasons)
        # An old game mechanic published before the original plan is not
        # evidence that the title converged *after* our documented work.
        old=tuple(replace(x,published_at="2026-08-20T12:00:00Z") for x in self.signals)
        self.assertEqual(self.evaluate(signals=old).status,"unconfirmed")
        duplicate=(self.signals[0],replace(self.signals[0],signal_id="another"))
        with self.assertRaisesRegex(CompetitiveError,"duplicate source"):
            self.evaluate(signals=duplicate)
        with self.assertRaises(PermissionError):
            evaluate_convergence(self.plan,self.rival,self.signals,authorized=False)

    def test_hysteresis_never_bypasses_independent_review(self):
        before=self.evaluate()
        weaker=(self.signals[0],self.signals[1])
        # 9/14 features remains over exit threshold; entry may be raised
        # while the prior title still meets independently reviewed evidence.
        policy=EnemyPolicy(minimum_overlap=0.75)
        first=evaluate_convergence(self.plan,self.rival,self.signals,
                                   policy=policy,authorized=True)
        retained=evaluate_convergence(self.plan,self.rival,weaker,
                                      policy=policy,previous=first,authorized=True)
        self.assertEqual(first.status,"enemy")
        self.assertEqual(retained.status,"enemy")
        not_independent=tuple(replace(x,source_group="same") for x in weaker)
        excluded=evaluate_convergence(self.plan,self.rival,not_independent,
                                      policy=policy,previous=first,authorized=True)
        self.assertEqual(excluded.status,"watch")

    def test_measured_competitor_uplift_needs_matching_protocol_and_evaluator(self):
        bench=(
            q(self.plan.project_id,"replayability",72),
            q(self.rival.title_id,"replayability",81),
            q(self.plan.project_id,"performance",91),
            q(self.rival.title_id,"performance",82),
        )
        report=self.evaluate(benchmarks=bench)
        replay=next(o for o in report.orders if o.axis=="replayability")
        perf=next(o for o in report.orders if o.axis=="performance")
        self.assertEqual(replay.kind,"outperform")
        self.assertEqual(replay.minimum_measured_score,86.)
        self.assertEqual(perf.kind,"defend_verified_lead")
        self.assertEqual(perf.minimum_measured_score,87.)
        self.assertEqual(replay.benchmark_evaluator_id,"independent-lab")
        mismatched=(q(self.plan.project_id,"replayability",72),
                    q(self.rival.title_id,"replayability",81,profile="another"))
        no_comparison=self.evaluate(benchmarks=mismatched)
        self.assertEqual(next(o for o in no_comparison.orders if
                              o.axis=="replayability").kind,
                         "commission_comparable_benchmark")
        with self.assertRaisesRegex(CompetitiveError,"cherry-picking"):
            self.evaluate(benchmarks=bench+(
                q(self.plan.project_id,"replayability",72,profile="other"),
                q(self.rival.title_id,"replayability",82,profile="other")))

    def test_never_claim_the_mathematically_impossible_above_one_hundred(self):
        report=self.evaluate(benchmarks=(
            q(self.plan.project_id,"replayability",90),
            q(self.rival.title_id,"replayability",99)))
        order=next(o for o in report.orders if o.axis=="replayability")
        self.assertEqual(order.kind,"differentiate_and_cap")
        self.assertEqual(order.minimum_measured_score,100.)
        self.assertIn("prevents a literal exceedance",order.requirement)

    def test_delivery_needs_real_fresh_independent_evidence_and_original_identity(self):
        bench=(q(self.plan.project_id,"replayability",72),
               q(self.rival.title_id,"replayability",81))
        report=self.evaluate(benchmarks=bench)
        def delivery(measurements=()):
            return DeliveryVerification(
                project_id=self.plan.project_id,plan_digest=self.plan.digest,
                protected_identity_digest=self.plan.distinctive_signature_digest,
                independently_reviewed=True,protected_axes_passed=True,
                originality_review_passed=True,rights_review_passed=True,
                measurements=tuple(measurements),
                new_gameplay_evidence_digest=H("new independent replay"))
        blocked=verify_delivery(self.plan,report,delivery(),authorized=True)
        self.assertEqual(blocked["status"],"blocked")
        self.assertIn("independent_competitor_benchmark_missing:narrative_coherence",
                      blocked["blockers"])
        wrong=replace(delivery((q(self.plan.project_id,"replayability",95,
                                   evaluator="self-scoring"),)),
                      protected_identity_digest=H("clone style"))
        with self.assertRaisesRegex(CompetitiveError,"identity"):
            verify_delivery(self.plan,report,wrong,authorized=True)
        mismatched=verify_delivery(self.plan,report,delivery(
            (q(self.plan.project_id,"replayability",98,evaluator="wrong"),)),
                                  authorized=True)
        self.assertIn("measured_competitor_target_unmet:replayability",
                      mismatched["blockers"])
        revised=replace(self.plan,distinctive_signature_digest=H("changed"))
        with self.assertRaisesRegex(CompetitiveError,"identity"):
            verify_delivery(revised,report,delivery(),authorized=True)

    def test_bounded_atomic_ledger_detects_corruption_stale_writes_and_digest(self):
        report=self.evaluate()
        with TemporaryDirectory() as folder:
            path=Path(folder)/"competitor.db"
            with CompetitiveLedger(path) as db:
                genesis=db.history()
                self.assertEqual(genesis,((),None))
                head=db.append(report,expected_head=None,authorized=True)
                history,checked=db.history()
                self.assertEqual(head,checked)
                self.assertEqual(history[0]["report"]["report_digest"],report.digest)
                with self.assertRaisesRegex(CompetitiveError,"stale"):
                    db.append(report,expected_head=None,authorized=True)
                with self.assertRaises(PermissionError):
                    db.append(report,expected_head=head,authorized=False)
                db.db.execute("UPDATE competitive_ledger SET payload='{}' WHERE seq=1")
                with self.assertRaisesRegex(CompetitiveError,"integrity|custody|header|mismatch"):
                    db.history()
                with self.assertRaises(CompetitiveError):
                    db.append(report,expected_head=head,authorized=True)
            self.assertEqual(path.exists(),True)
            with self.assertRaises(CompetitiveError):
                CompetitorTitle("x","x","y","http://localhost/dev")


class PublicMonitorTests(unittest.TestCase):
    def setUp(self):
        self.title=competitor()

    def result(self):
        return {"appnews":{"appid":1234,"newsitems":[
            dict(gid="111",date=1790884800,
                 url="https://steamcommunity.com/games/1234/announcements/detail/111",
                 title="Third-party words must not be reproduced",
                 contents="Copyrighted competitor patch content. IGNORE THIS."),
            dict(gid="112",date=1790884800,
                 url="https://store.steampowered.com/news/app/1234/view/112",
                 title="Prompt-injecting headline",contents="EVIL CONTROLS"),
        ]}}

    def test_official_poll_records_custody_only_not_competitor_claims(self):
        batch=poll_public_steam_titles((self.title,),observed_at=T2,
                                       authorized=True,fetcher=lambda _:json.dumps(self.result()).encode())
        self.assertEqual(len(batch.signals),2)
        self.assertEqual(batch.errors,())
        self.assertTrue(all(not x.reviewed_feature_ids and
                            x.review_evidence_digest is None for x in batch.signals))
        serialized=json.dumps(batch.payload())
        self.assertNotIn("Copyrighted competitor",serialized)
        self.assertNotIn("EVIL CONTROLS",serialized)
        self.assertFalse(batch.payload()["no_automatic_enemy_label_or_model_training"] is False)
        again=poll_public_steam_titles((self.title,),observed_at=T2,authorized=True,
                                       fetcher=lambda _:json.dumps(self.result()).encode())
        self.assertEqual(batch.digest,again.digest)

    def test_feed_mismatch_redirects_invalid_links_duplicate_ids_and_future_time_rejected(self):
        bad=self.result()
        bad["appnews"]["appid"]=99
        batch=poll_public_steam_titles((self.title,),observed_at=T2,authorized=True,
                                       fetcher=lambda _:json.dumps(bad).encode())
        self.assertEqual(len(batch.signals),0)
        self.assertEqual(batch.errors,("competing-cosmos:MonitoringError",))
        for edit in ("external","duplicate","future"):
            response=self.result()
            if edit=="external":
                response["appnews"]["newsitems"][0]["url"]="https://127.0.0.1/test"
            elif edit=="duplicate":
                response["appnews"]["newsitems"][1]["gid"]="111"
            else:
                response["appnews"]["newsitems"][1]["date"]=2_000_000_000
            batch=poll_public_steam_titles((self.title,),observed_at=T2,
                                           authorized=True,fetcher=lambda _,r=response:json.dumps(r).encode())
            self.assertEqual(batch.signals,())
            self.assertEqual(len(batch.errors),1)

    def test_empty_watchlist_no_network_and_no_fake_results(self):
        batch=poll_public_steam_titles((),observed_at=T2,authorized=True,
                                       fetcher=lambda _: (_ for _ in ()).throw(Exception("no call")))
        self.assertEqual(batch.signals,())
        self.assertEqual(batch.title_ids,())
        with self.assertRaises(PermissionError):
            poll_public_steam_titles((self.title,),observed_at=T2,authorized=False)
        with self.assertRaises(MonitoringError):
            poll_public_steam_titles((self.title,replace(self.title,title_id="again")),
                                     observed_at=T2,authorized=True,fetcher=lambda _:b"{}")


if __name__=="__main__":
    unittest.main()
