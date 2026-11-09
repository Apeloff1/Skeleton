"""Externally verified year-scale approval extensions; old workers never inherit grants."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from skeleton.automation.annual_production import AnnualProductionStore, ProductionConflict

D=lambda s:sha256(s.encode()).hexdigest()
T0=1_800_000_000.0
DAY=86_400.0


class AnnualAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"year.db"
        self.db=AnnualProductionStore(self.path)
        self.db.enroll(production_id="world-1",system="jeeves",
                       objective_digest=D("scope"),authority_digest=D("grant-1"),
                       authority_expires_at=T0+183*DAY,horizon_days=183,now=T0)

    def tearDown(self):self.temp.cleanup()

    def renew(self, *, old="grant-1", new="grant-2", now=T0+182*DAY,
              expiry=T0+550*DAY, verifier=None):
        return self.db.renew_authority(
            "world-1",expected_authority_digest=D(old),
            new_authority_digest=D(new),approval_digest=D(new+":approval"),
            new_expires_at=expiry,now=now,
            verify_approval=verifier or (lambda *args: True),
        )

    def test_operator_verified_extension_allows_six_month_job_to_reach_year(self):
        self.renew()
        self.assertEqual(self.db.verify_authority_chain("world-1"),1)
        self.assertEqual(len(self.db.due(now=T0+366*DAY)),1)
        self.db.claim("world-1",worker="year-worker",
                      authority_digest=D("grant-2"),now=T0+366*DAY)

    def test_old_grant_invalidated_immediately(self):
        old=self.db.claim("world-1",worker="old",
                          authority_digest=D("grant-1"),now=T0+10)
        self.renew()
        with self.assertRaises((ProductionConflict,PermissionError)):
            self.db.heartbeat(old,now=T0+182*DAY+1)
        with self.assertRaises(PermissionError):
            self.db.claim("world-1",worker="rogue",
                          authority_digest=D("grant-1"),now=T0+182*DAY+1)

    def test_unverified_approval_must_fail_closed(self):
        with self.assertRaises(PermissionError):
            self.renew(verifier=lambda *args:False)
        self.assertEqual(self.db.verify_authority_chain("world-1"),0)
        self.assertEqual(self.db.read("world-1").authority_expires_at,T0+183*DAY)

    def test_attestor_receives_exact_project_grants_expiry_and_receipt(self):
        observed=[]
        self.renew(verifier=lambda *args:observed.append(args) or True)
        self.assertEqual(observed[0],
                         ("world-1",D("grant-1"),D("grant-2"),
                          D("grant-2:approval"),T0+550*DAY))

    def test_expired_authority_can_resume_only_after_explicit_verified_approval(self):
        self.assertEqual(self.db.due(now=T0+220*DAY),())
        self.renew(now=T0+220*DAY)
        self.assertEqual(len(self.db.due(now=T0+220*DAY)),1)

    def test_duplicate_old_grant_cannot_override_newer_approval(self):
        self.renew()
        with self.assertRaises(ProductionConflict):
            self.renew(new="grant-3",expiry=T0+900*DAY)

    def test_second_explicit_renewal_extends_to_following_year(self):
        self.renew()
        self.renew(old="grant-2",new="grant-3",now=T0+545*DAY,
                   expiry=T0+900*DAY)
        self.assertEqual(self.db.verify_authority_chain("world-1"),2)
        self.assertEqual(len(self.db.due(now=T0+720*DAY)),1)

    def test_false_grant_history_is_detected_before_next_work(self):
        self.renew()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE annual_authority_rotations SET approval_digest=?",
                         (D("fake"),))
        with self.assertRaises(ProductionConflict):
            self.db.verify_authority_chain("world-1")

    def test_tampered_active_grant_head_is_detected(self):
        self.renew()
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE annual_productions SET authority_digest=?",
                         (D("fake"),))
        with self.assertRaises(ProductionConflict):
            self.db.verify_authority_chain("world-1")

    def test_shorter_renewal_is_rejected(self):
        with self.assertRaises(ProductionConflict):
            self.renew(now=T0+10,expiry=T0+180*DAY)

    def test_identical_grant_identity_cannot_be_reused_for_fake_extension(self):
        with self.assertRaises(ValueError):
            self.renew(new="grant-1")

    def test_terminal_campaign_does_not_restart_on_approval(self):
        lease=self.db.claim("world-1",worker="worker",
                            authority_digest=D("grant-1"),now=T0)
        self.db.checkpoint(lease,sequence=1,state_digest=D("state"),
                           evidence_digest=D("evidence"),now=T0+1)
        self.db.terminal(lease,state="completed",
                         verified_evidence_digest=D("release"),
                         verify_evidence=lambda *_: True, now=T0+2)
        with self.assertRaises(ProductionConflict): self.renew()
        self.assertEqual(self.db.read("world-1").status,"completed")

    def test_bad_approval_input_rejected_before_lease_changes(self):
        with self.assertRaises(ValueError):
            self.renew(expiry=float("nan"))
        with self.assertRaises(ValueError):
            self.renew(verifier="yes")
        self.assertEqual(self.db.verify_authority_chain("world-1"),0)


if __name__=="__main__":unittest.main()
