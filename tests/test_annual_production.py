"""Real SQLite fault/restart regressions for 6- and 12-month production controls."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from skeleton.automation.annual_production import (
    AnnualProductionStore, ProductionConflict,
)

D = lambda value: sha256(value.encode()).hexdigest()
T0 = 1_800_000_000.0
DAY = 86400.0


class AnnualProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "production.db"
        self.db = AnnualProductionStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def enroll(self, system="jeeves", horizon=366, identity="project-1",
               now=T0, expires_at=None):
        return self.db.enroll(
            production_id=identity, system=system,
            objective_digest=D("original-game-plan"),
            authority_digest=D("approved-scope"),
            authority_expires_at=expires_at if expires_at is not None else now + 370 * DAY,
            horizon_days=horizon, now=now,
        )

    def claim(self, identity="project-1", now=T0, worker="node-a", seconds=120):
        return self.db.claim(identity, worker=worker,
                             authority_digest=D("approved-scope"),
                             now=now, lease_seconds=seconds)

    def cp(self, claim, sequence=1, now=T0 + 2):
        return self.db.checkpoint(
            claim, sequence=sequence, state_digest=D("state:"+str(sequence)),
            evidence_digest=D("receipt:"+str(sequence)), now=now,
        )

    def test_six_month_production_enrollment_survives_reopen(self):
        self.enroll(horizon=183)
        reopened = AnnualProductionStore(self.path)
        value = reopened.read("project-1")
        self.assertEqual(value.horizon_days, 183)
        self.assertEqual(value.sequence, 0)
        self.assertEqual(value.status, "queued")

    def test_one_year_production_has_no_arbitrary_step_limit(self):
        self.enroll()
        lease = self.claim()
        for n in range(1, 801):
            self.cp(lease, n, now=T0 + 1 + n / 1000)
        self.assertEqual(self.db.read("project-1").sequence, 800)
        self.assertEqual(self.db.verify_chain("project-1"), 800)

    def test_six_month_idle_still_due_with_valid_authority(self):
        self.enroll(expires_at=T0 + 500 * DAY)
        self.assertEqual([x.production_id for x in self.db.due(now=T0 + 183*DAY)],
                         ["project-1"])

    def test_year_idle_still_due_if_grant_remains_current(self):
        self.enroll(expires_at=T0 + 500 * DAY)
        self.assertEqual(len(AnnualProductionStore(self.path).due(now=T0+366*DAY)), 1)

    def test_no_pretend_autonomous_execution_after_authority_expires(self):
        self.enroll(expires_at=T0+3*DAY)
        self.assertEqual(self.db.due(now=T0+366*DAY), ())
        with self.assertRaises(PermissionError):
            self.claim(now=T0+366*DAY)

    def test_enrollment_is_idempotent_and_cannot_change_approved_scope(self):
        a = self.enroll()
        self.assertEqual(a, self.enroll())
        with self.assertRaises(ProductionConflict):
            self.db.enroll(production_id="project-1", system="dragon",
                objective_digest=D("original-game-plan"),
                authority_digest=D("approved-scope"),
                authority_expires_at=T0 + 370*DAY, horizon_days=366, now=T0)

    def test_three_systems_have_independent_production_ids(self):
        for system in ("jeeves", "builder", "dragon"):
            self.enroll(system=system, identity="game-"+system)
        self.assertEqual({x.system for x in self.db.due(now=T0)},
                         {"jeeves","builder","dragon"})

    def test_lease_claim_requires_current_authority_digest(self):
        self.enroll()
        with self.assertRaises(PermissionError):
            self.db.claim("project-1", worker="worker",
                          authority_digest=D("other"), now=T0)

    def test_active_lease_denies_second_worker_even_same_id(self):
        self.enroll()
        self.claim(worker="first")
        with self.assertRaises(ProductionConflict):
            self.claim(worker="second", now=T0+10)

    def test_expired_lease_can_be_reclaimed_with_higher_epoch(self):
        self.enroll()
        old = self.claim()
        newer = self.claim(now=T0+121, worker="replacement")
        self.assertEqual(newer.epoch, old.epoch+1)
        self.assertNotEqual(newer.token, old.token)
        with self.assertRaises(ProductionConflict):
            self.cp(old, now=T0+122)

    def test_old_worker_cannot_commit_after_expiry_even_without_reclaim(self):
        self.enroll()
        lease = self.claim()
        with self.assertRaises(ProductionConflict):
            self.cp(lease, now=T0+120)

    def test_attacker_cannot_forge_token_from_visible_claim_metadata(self):
        self.enroll()
        lease = self.claim()
        with self.assertRaises(ProductionConflict):
            self.cp(replace(lease, token="0"*64))

    def test_lease_heartbeat_extends_only_within_authorized_window(self):
        self.enroll(expires_at=T0+140)
        lease = self.claim()
        renew = self.db.heartbeat(lease, now=T0+119, lease_seconds=120)
        self.assertEqual(renew.expires_at, T0+140)
        self.cp(renew, now=T0+139)
        with self.assertRaises(PermissionError):
            self.db.heartbeat(renew, now=T0+141)

    def test_heartbeat_rejects_wall_clock_regression(self):
        self.enroll()
        lease = self.claim()
        with self.assertRaises(ProductionConflict):
            self.db.heartbeat(lease, now=T0-1)

    def test_clock_rollback_cannot_sign_an_old_checkpoint_after_heartbeat(self):
        self.enroll()
        original=self.claim()
        renewed=self.db.heartbeat(original,now=T0+100,lease_seconds=120)
        with self.assertRaises(ProductionConflict):
            self.cp(renewed,now=T0+90)
        self.assertEqual(self.db.read("project-1").sequence,0)

    def test_clock_rollback_cannot_claim_stale_lease_release(self):
        self.enroll()
        lease=self.claim()
        self.db.release(lease,now=T0+20,retry_seconds=10)
        with self.assertRaises(ProductionConflict):
            self.claim(now=T0+10)
        self.assertEqual(self.db.read("project-1").status,"waiting")

    def test_checkpoint_sequence_must_advance_exactly_one(self):
        self.enroll()
        lease = self.claim()
        self.cp(lease)
        for bad in (1, 3, 0, -1):
            with self.assertRaises((ValueError,ProductionConflict)):
                self.cp(lease, bad, now=T0+4)
        self.assertEqual(self.db.verify_chain("project-1"),1)

    def test_chained_checkpoints_persist_across_worker_turnover(self):
        self.enroll()
        first = self.claim()
        self.cp(first,1)
        self.db.release(first,now=T0+4,retry_seconds=0)
        second = self.claim(now=T0+5,worker="second")
        self.cp(second,2,now=T0+6)
        self.assertEqual(self.db.verify_chain("project-1"),2)
        self.assertEqual(self.db.read("project-1").lease_epoch,2)

    def test_separate_process_connections_compete_for_one_lease(self):
        self.enroll()
        a=AnnualProductionStore(self.path)
        b=AnnualProductionStore(self.path)
        a.claim("project-1",worker="A",authority_digest=D("approved-scope"),now=T0)
        with self.assertRaises(ProductionConflict):
            b.claim("project-1",worker="B",authority_digest=D("approved-scope"),now=T0)

    def test_work_wait_recovery_ignores_early_or_active_leases(self):
        self.enroll()
        lease=self.claim()
        self.assertEqual(self.db.due(now=T0+30),())
        self.db.release(lease,now=T0+50,retry_seconds=500)
        self.assertEqual(self.db.due(now=T0+549),())
        self.assertEqual(len(self.db.due(now=T0+550)),1)

    def test_failed_status_does_not_auto_mark_backend_failure(self):
        self.enroll()
        lease=self.claim()
        self.db.release(lease,now=T0+1)
        self.assertEqual(self.db.read("project-1").status,"waiting")
        self.assertEqual(self.db.read("project-1").checkpoint_digest,None)

    def test_complete_requires_real_checkpoint_receipt(self):
        self.enroll()
        lease=self.claim()
        with self.assertRaises(ProductionConflict):
            self.db.terminal(lease,state="completed",verified_evidence_digest=D("approved"),
                             verify_evidence=lambda *_: True, now=T0+2)

    def test_failed_and_cancelled_can_record_prework_terminal_evidence(self):
        for status in ("failed","cancelled"):
            identity="p-"+status
            self.enroll(identity=identity)
            lease=self.claim(identity=identity)
            self.db.terminal(lease,state=status,
                             verified_evidence_digest=D(status),
                             verify_evidence=lambda *_: True, now=T0+2)
            self.assertEqual(self.db.read(identity).status,status)
            self.assertNotIn(identity,[p.production_id for p in self.db.due(now=T0+5)])

    def test_terminal_evidence_requires_independent_backend_verification(self):
        self.enroll()
        lease=self.claim()
        self.cp(lease)
        with self.assertRaises(PermissionError):
            self.db.terminal(lease,state="completed",
                verified_evidence_digest=D("unreviewed"),
                verify_evidence=lambda *_: False,now=T0+3)
        self.assertEqual(self.db.read("project-1").status,"running")

    def test_completed_job_is_not_restarted_by_another_enrollment(self):
        self.enroll()
        lease=self.claim()
        self.cp(lease)
        self.db.terminal(lease,state="completed",
            verified_evidence_digest=D("canonical-success"),
            verify_evidence=lambda *_: True, now=T0+3)
        self.assertEqual(self.enroll().status,"completed")
        with self.assertRaises(ProductionConflict):
            self.claim(now=T0+4)

    def test_persisted_checkpoint_chain_rejects_sqlite_tamper(self):
        self.enroll()
        lease=self.claim()
        self.cp(lease)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE annual_checkpoint_receipts SET evidence_digest=?",
                       (D("forged"),))
        with self.assertRaises(ProductionConflict):
            self.db.verify_chain("project-1")

    def test_head_checkpoint_tampering_also_fails_integrity(self):
        self.enroll()
        lease=self.claim()
        self.cp(lease)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE annual_productions SET sequence=999")
        with self.assertRaises(ProductionConflict):
            self.db.verify_chain("project-1")

    def test_due_scan_is_bounded_and_sorted(self):
        for index in range(120):
            self.enroll(identity="job-%03d"%index)
        due=self.db.due(now=T0,limit=7)
        self.assertEqual(len(due),7)
        self.assertEqual([p.production_id for p in due],
                         ["job-%03d"%i for i in range(7)])

    def test_due_partition_by_subsystem(self):
        for system in ("dragon","builder","jeeves"):
            self.enroll(system=system,identity="id-"+system)
        self.assertEqual([r.system for r in self.db.due(now=T0,system="dragon")],
                         ["dragon"])

    def test_invalid_input_budgets_are_rejected(self):
        with self.assertRaises(ValueError):
            self.enroll(horizon=0)
        with self.assertRaises(ValueError):
            self.enroll(identity="../outside")
        self.enroll()
        with self.assertRaises(ValueError):
            self.db.due(now=T0, limit=10000)
        with self.assertRaises(ValueError):
            self.claim(seconds=3601)
        with self.assertRaises(ValueError):
            self.db.checkpoint(self.claim(),sequence=1,
                state_digest="not-digest",evidence_digest=D("e"),now=T0+2)


if __name__=="__main__":
    unittest.main()
