"""End-to-end bounded production quantums across Jeeves, Builder, Dragon."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from skeleton.automation.annual_production import (
    AnnualProductionStore, ProductionConflict,
)
from skeleton.automation.annual_worker import (
    AnnualWorkRunner, VerifiedWork,
)
from skeleton.jeeves.annual_production import make_jeeves_annual_runner
from skeleton.automation.builder_annual_production import make_builder_annual_runner
from skeleton.ai.webcrawler.dragon_annual_production import make_dragon_annual_runner

D = lambda s: sha256(s.encode()).hexdigest()
T0 = 1_800_000_000.0


class AnnualWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=AnnualProductionStore(Path(self.tmp.name)/"control.db")
        self.now=T0
        for domain in ("jeeves", "builder", "dragon"):
            self.store.enroll(
                production_id="project-"+domain, system=domain, horizon_days=366,
                objective_digest=D("game-plan"), authority_digest=D("grant"),
                authority_expires_at=T0+400*86400, now=T0,
            )

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, domain, worker, verifier):
        return AnnualWorkRunner(self.store, system=domain, worker=worker,
                                verify=verifier, clock=lambda: self.now)

    def test_all_three_canonical_planes_execute_separately(self):
        makers = [
            ("jeeves", lambda fn: make_jeeves_annual_runner(
                self.store, run_authorized_step=fn,
                verify_canonical_receipt=lambda q,r: True,
                clock=lambda: self.now)),
            ("builder", lambda fn: make_builder_annual_runner(
                self.store, run_build_graph_quantum=fn,
                verify_build_artifacts=lambda q,r: True,
                clock=lambda: self.now)),
            ("dragon", lambda fn: make_dragon_annual_runner(
                self.store, run_reviewed_research_quantum=fn,
                verify_reviewed_knowledge=lambda q,r: True,
                clock=lambda: self.now)),
        ]
        for system, maker in makers:
            output=maker(lambda q: VerifiedWork(D(system+"-state"),D(system+"-evidence"))).run_one(
                "project-"+system, owner="worker", authority_digest=D("grant"))
            self.assertEqual(output.state, "checkpointed")
            self.assertEqual(self.store.read("project-"+system).sequence,1)
            self.assertEqual(self.store.verify_chain("project-"+system),1)

    def test_host_verifier_rejection_does_not_persist_forged_progress(self):
        run=self.runner("jeeves",
            lambda q: VerifiedWork(D("state"),D("unverified")),
            lambda q,r: False)
        with self.assertRaises(PermissionError):
            run.run_one("project-jeeves",owner="worker",authority_digest=D("grant"))
        self.assertEqual(self.store.read("project-jeeves").sequence,0)

    def test_no_default_canonical_worker_or_verifier_is_invented(self):
        with self.assertRaises(ValueError):
            AnnualWorkRunner(self.store,system="builder",worker=lambda q: None,
                             verify=None)

    def test_worker_exception_leaves_fenced_lease_not_unsafe_immediate_retry(self):
        run=self.runner("builder",lambda q: (_ for _ in ()).throw(RuntimeError("disk uncertain")),
                        lambda q,r: True)
        with self.assertRaises(RuntimeError):
            run.run_one("project-builder",owner="worker",authority_digest=D("grant"))
        with self.assertRaises(ProductionConflict):
            run.run_one("project-builder",owner="second",authority_digest=D("grant"))
        self.assertEqual(self.store.read("project-builder").sequence,0)

    def test_one_idempotency_key_is_stable_across_lease_replacement(self):
        keys=[]
        def worker(q):
            keys.append(q.idempotency_key)
            if len(keys)==1: raise RuntimeError("ambiguous backend response")
            return VerifiedWork(D("state"), D("evidence"))
        runner=self.runner("dragon",worker,lambda q,r:True)
        with self.assertRaises(RuntimeError):
            runner.run_one("project-dragon",owner="one",authority_digest=D("grant"))
        self.now += 121
        runner.run_one("project-dragon",owner="two",authority_digest=D("grant"))
        self.assertEqual(keys[0],keys[1])
        self.assertEqual(self.store.read("project-dragon").sequence,1)

    def test_slow_worker_cannot_commit_using_start_time_after_expiry(self):
        def worker(q):
            self.now += 121
            return VerifiedWork(D("state"),D("evidence"))
        runner=self.runner("jeeves",worker,lambda q,r:True)
        with self.assertRaises(ProductionConflict):
            runner.run_one("project-jeeves",owner="worker",authority_digest=D("grant"))
        self.assertEqual(self.store.read("project-jeeves").sequence,0)

    def test_worker_may_heartbeat_while_processing_long_chapter(self):
        def worker(q):
            self.now += 90
            q.heartbeat(120)
            self.now += 90
            q.heartbeat(120)
            self.now += 20
            return VerifiedWork(D("manuscript"),D("canon-reviewed"))
        report=self.runner("jeeves",worker,lambda q,r:True).run_one(
            "project-jeeves",owner="worker",authority_digest=D("grant"))
        self.assertEqual(report.state,"checkpointed")
        self.assertEqual(self.store.verify_chain("project-jeeves"),1)

    def test_invalid_return_from_production_runtime_is_not_accepted(self):
        runner=self.runner("dragon",lambda q: {"done":True},lambda q,r:True)
        with self.assertRaises(ValueError):
            runner.run_one("project-dragon",owner="worker",authority_digest=D("grant"))
        self.assertEqual(self.store.read("project-dragon").sequence,0)

    def test_explicit_verified_termination_records_real_terminal_evidence(self):
        def work(q):
            return VerifiedWork(D("released-game"),D("build-tested"),"completed",
                                D("verified-final-package"))
        out=self.runner("builder",work,lambda q,r:True).run_one(
            "project-builder",owner="worker",authority_digest=D("grant"))
        self.assertEqual(out.terminal,"completed")
        self.assertEqual(self.store.read("project-builder").status,"completed")
        self.assertEqual(self.store.due(now=self.now,system="builder"),())

    def test_failed_terminal_requires_verifiable_evidence_digest(self):
        runner=self.runner("dragon",
            lambda q: VerifiedWork(D("state"),D("receipt"),"failed","invalid"),
            lambda q,r:True)
        with self.assertRaises(ValueError):
            runner.run_one("project-dragon",owner="worker",authority_digest=D("grant"))
        self.assertEqual(self.store.read("project-dragon").sequence,0)

    def test_subsystem_confusion_does_not_advance_other_agent(self):
        runner=self.runner("dragon",
            lambda q:VerifiedWork(D("state"),D("receipt")),
            lambda q,r:True)
        with self.assertRaises(ProductionConflict):
            runner.run_one("project-jeeves",owner="worker",authority_digest=D("grant"))
        self.assertEqual(self.store.read("project-jeeves").sequence,0)

    def test_verifier_cannot_silently_synthesize_terminal_outcome(self):
        runner=self.runner("jeeves",lambda q:VerifiedWork(D("state"),D("evidence")),
                           lambda q,r:True)
        report=runner.run_one("project-jeeves",owner="worker",authority_digest=D("grant"))
        self.assertIsNone(report.terminal)
        self.assertEqual(self.store.read("project-jeeves").status,"waiting")


if __name__=="__main__":
    unittest.main()
