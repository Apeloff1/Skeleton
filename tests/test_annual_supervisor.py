"""Three-plane bounded scheduling under year-long heterogeneous workloads."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from skeleton.automation.annual_production import AnnualProductionStore
from skeleton.automation.annual_supervisor import AnnualProductionSupervisor
from skeleton.automation.annual_worker import AnnualWorkRunner, VerifiedWork

D=lambda s:sha256(s.encode()).hexdigest()
NOW=1_800_000_000.0
DAY=86400


class AnnualSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=AnnualProductionStore(Path(self.temp.name)/"jobs.db")
        self.now=NOW
        self.effects=[]
        for system in ("jeeves","builder","dragon"):
            self.db.enroll(production_id=system,system=system,horizon_days=366,
                           objective_digest=D("world-vision"),authority_digest=D("scope"),
                           authority_expires_at=NOW+400*DAY,now=NOW)

    def tearDown(self):self.temp.cleanup()

    def supervisor(self, builders=None, resolver=None):
        builders=builders or {}
        runners={}
        for domain in ("jeeves","builder","dragon"):
            worker=builders.get(domain) or (
                lambda q, subsystem=domain: (
                    self.effects.append(subsystem),
                    VerifiedWork(D(subsystem+"-state"), D(subsystem+"-evidence")),
                )[1]
            )
            runners[domain]=AnnualWorkRunner(self.db,system=domain,
                worker=worker,verify=lambda q,r:True,clock=lambda:self.now)
        return AnnualProductionSupervisor(
            self.db,runners,resolver or (lambda _id,_sys:D("scope")))

    def test_one_sweep_processes_three_independent_work_planes(self):
        report=self.supervisor().sweep(owner="host",now=self.now)
        self.assertEqual(report.examined,3)
        self.assertEqual(report.checkpointed,3)
        self.assertEqual(report.errors,())
        self.assertEqual(set(self.effects),{"jeeves","builder","dragon"})
        for subsystem in self.effects:
            self.assertEqual(self.db.verify_chain(subsystem),1)

    def test_bounded_sweep_does_not_claim_all_backlog_at_once(self):
        report=self.supervisor().sweep(owner="host",now=self.now,limit=1)
        self.assertEqual(report.examined,1)
        self.assertEqual(report.checkpointed,1)
        self.assertEqual(sum(self.db.read(s).sequence
            for s in ("jeeves","builder","dragon")),1)

    def test_fast_worker_yields_admission_before_repeating(self):
        service=self.supervisor()
        service.sweep(owner="host",now=self.now,limit=1)
        other=service.sweep(owner="host",now=self.now,limit=1)
        self.assertEqual(other.checkpointed,1)
        self.assertEqual(sum(self.db.read(s).sequence
            for s in ("jeeves","builder","dragon")),2)

    def test_grant_resolver_failure_cannot_launch_any_subsystem(self):
        def denied(*args):raise PermissionError("authorization unavailable")
        report=self.supervisor(resolver=denied).sweep(owner="host",now=self.now)
        self.assertEqual(report.checkpointed,0)
        self.assertEqual(len(report.errors),3)
        self.assertEqual(self.effects,[])

    def test_one_untrusted_worker_does_not_block_two_valid_workers(self):
        def error(_q):raise RuntimeError("dragon crawler crashed")
        report=self.supervisor(builders={"dragon":error}).sweep(
            owner="host",now=self.now)
        self.assertEqual(report.checkpointed,2)
        self.assertEqual(report.deferred,1)
        self.assertEqual(self.db.read("dragon").sequence,0)
        self.assertEqual(set(self.effects),{"jeeves","builder"})

    def test_only_authorized_domain_can_run_canonical_status(self):
        service=self.supervisor()
        for domain in ("jeeves","builder","dragon"):
            self.db.enroll(
                production_id="extra-"+domain,system=domain,horizon_days=183,
                objective_digest=D("x"),authority_digest=D("other-grant"),
                authority_expires_at=NOW+200*DAY,now=NOW)
        report=service.sweep(owner="host",now=self.now)
        self.assertEqual(report.checkpointed,3)
        self.assertEqual(len(report.errors),3)

    def test_restarted_service_can_resume_saved_progress_after_months(self):
        service=self.supervisor()
        service.sweep(owner="host",now=self.now)
        self.now+=190*DAY
        reopened=AnnualProductionStore(self.db.path)
        runners={}
        for system in ("jeeves","builder","dragon"):
            runners[system]=AnnualWorkRunner(reopened,system=system,
                worker=lambda q:VerifiedWork(D("state2"),D("evidence2")),
                verify=lambda q,r:True,clock=lambda:self.now)
        next_host=AnnualProductionSupervisor(
            reopened,runners,lambda *_:D("scope"))
        report=next_host.sweep(owner="replacement",now=self.now)
        self.assertEqual(report.checkpointed,3)
        self.assertEqual(reopened.verify_chain("jeeves"),2)
        self.assertEqual(reopened.verify_chain("dragon"),2)

    def test_six_month_grant_expiry_blocks_year_end_sweep(self):
        db=AnnualProductionStore(Path(self.temp.name)/"expired.db")
        for subsystem in ("jeeves","builder","dragon"):
            db.enroll(production_id=subsystem,system=subsystem,horizon_days=183,
                objective_digest=D("game"),authority_digest=D("scope"),
                authority_expires_at=NOW+183*DAY,now=NOW)
        runners={s:AnnualWorkRunner(db,system=s,
            worker=lambda q:VerifiedWork(D("state"),D("receipt")),
            verify=lambda q,r:True,clock=lambda:NOW+200*DAY)
            for s in ("jeeves","builder","dragon")}
        host=AnnualProductionSupervisor(db,runners,lambda *_:D("scope"))
        self.assertEqual(host.sweep(owner="host",now=NOW+200*DAY).examined,0)

    def test_reject_missing_critical_production_plane(self):
        all_runners=self.supervisor().runners
        all_runners.pop("dragon")
        with self.assertRaises(ValueError):
            AnnualProductionSupervisor(self.db,all_runners,lambda *_:D("scope"))

    def test_malformed_sweep_limits_rejected_without_mutations(self):
        host=self.supervisor()
        with self.assertRaises(ValueError):
            host.sweep(owner="host",now=self.now,limit=100000)
        self.assertEqual(self.effects,[])


if __name__=="__main__":unittest.main()
