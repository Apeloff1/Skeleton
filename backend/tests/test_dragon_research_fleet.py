"""Actual SQLite ten-campaign orchestration, crash recovery and budget fences."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.dragon_navigation_federation import NavigationFederation
from core import dragon_research_fleet as fleet
from core import dragon_research_campaign as campaign
from core.dragon_hoarder_bulk import owner_key
from test_dragon_navigation_federation import fixture,SCOPE,OTHER,NOW


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"corpus.sqlite3"
        self.repo=NavigationFederation(self.path);self.query="flight manual"
        self.grant=self.repo.publish(SCOPE,session_id="fleet-source",
            snapshot=fixture(901,96).snapshot(),rights_reference="original-fixture-metadata",
            retention_seconds=7200,acknowledged=True,now=NOW)["grant_id"]
        self.members=[]
        for i in range(10):
            result=self.repo.campaign(SCOPE,action="create",query=self.query,
                operation=f"fleet-member-create-{i:04d}",budget=4096,
                retention_seconds=3600,acknowledged=True,now=NOW)
            self.members.append(result["campaign_id"])
        self.objectives=[{"campaign_id":x,"query":self.query} for x in self.members]
        self.args={"operation":"ten-campaign-fleet-0001",
            "members":[{"campaign_id":x,"weight":1} for x in self.members],
            "budget":40960,"retention_seconds":3600,"acknowledged":True,"now":NOW}
        self.record=self.repo.fleet(SCOPE,action="create",**self.args)
        self.id=self.record["fleet_id"]

    def pulse(self,revision,op,*,now=NOW,budget=4,scope=SCOPE,query=None):
        return self.repo.fleet(scope,action="pulse",fleet_id=self.id,expected_revision=revision,
            operation=op,budget=budget,objectives=self.objectives if query is None else query,now=now)

    def current(self,now=NOW):
        return self.repo.fleet(SCOPE,action="inspect",fleet_id=self.id,now=now)["fleet"]

    def test_actual_ten_campaign_fairness_and_exact_aggregate_debit(self):
        self.assertEqual(self.record["remaining"],40960)
        self.assertEqual(len(self.record["members"]),10)
        self.assertTrue(self.repo.fleet(SCOPE,action="create",**self.args)["replayed"])
        total=0;chosen=set();revision=1
        for i in range(10):
            receipt=self.pulse(revision,f"fleet-pulse-{i:08d}")
            self.assertEqual(receipt["state"],"complete")
            self.assertTrue(receipt["targets"])
            chosen.add(receipt["campaign_id"])
            total+=receipt["spent"]
            revision=receipt["fleet"]["revision"]
            self.assertFalse(receipt["network_authorized"])
        self.assertEqual(len(chosen),10)
        self.assertEqual(self.current()["remaining"],40960-total)
        self.assertEqual(sum(m["spent"] for m in self.current()["members"]),total)
        replay=self.pulse(1,"fleet-pulse-00000000")
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.current()["remaining"],40960-total)
        with self.assertRaises(ValueError):self.pulse(revision,"fleet-pulse-foreign",scope=OTHER)

    def test_crash_after_campaign_commit_recovers_exactly_once(self):
        with patch.object(fleet,"_finish",side_effect=RuntimeError("crash after round commit")):
            with self.assertRaises(RuntimeError):self.pulse(1,"fleet-crash-operation")
        self.repo=NavigationFederation(self.path)
        self.assertEqual(self.current()["remaining"],40960)
        with self.assertRaises(ValueError):self.pulse(1,"fleet-crash-operation")
        result=self.repo.fleet(SCOPE,action="reconcile",fleet_id=self.id,now=NOW+fleet.MAX_LEASE)
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["state"],"complete")
        self.assertGreater(result["spent"],0)
        self.assertEqual(result["fleet"]["remaining"],40960-result["spent"])
        replay=self.pulse(1,"fleet-crash-operation",now=NOW+fleet.MAX_LEASE)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["spent"],result["spent"])
        self.assertEqual(self.current(NOW+fleet.MAX_LEASE)["remaining"],40960-result["spent"])

    def test_expired_uncommitted_claim_does_not_debit(self):
        with patch.object(campaign,"advance",side_effect=RuntimeError("worker lost before publication")):
            with self.assertRaises(RuntimeError):self.pulse(1,"fleet-abandon-operation")
        held=self.repo.fleet(SCOPE,action="reconcile",fleet_id=self.id,now=NOW+fleet.MAX_LEASE)
        self.assertEqual(held["state"],"held")
        self.assertEqual(held["spent"],0)
        self.assertEqual(held["fleet"]["remaining"],40960)
        replay=self.pulse(1,"fleet-abandon-operation",now=NOW+fleet.MAX_LEASE)
        self.assertEqual(replay["targets"],[])
        self.assertTrue(replay["replayed"])

    def test_model_objective_fence_and_revoked_replay(self):
        altered=[dict(x) for x in self.objectives];altered[0]["query"]="unrelated"
        with self.assertRaises(ValueError):self.pulse(1,"fleet-invalid-objective",query=altered)
        first=self.pulse(1,"fleet-valid-objective")
        self.assertTrue(first["targets"])
        self.repo.revoke(SCOPE,self.grant)
        replay=self.pulse(1,"fleet-valid-objective")
        self.assertEqual(replay["targets"],[])
        self.assertEqual(replay["plan_digest"],first["plan_digest"])
        with self.repo._db() as db:
            owner=owner_key(SCOPE)
            text=str([dict(x) for x in db.execute("SELECT * FROM navigation_fleets WHERE owner=?",(owner,))])
            self.assertNotIn(self.query,text)
        closed=self.repo.fleet(SCOPE,action="close",fleet_id=self.id,expected_revision=2,now=NOW)
        self.assertEqual(closed["state"],"closed")
        purged=self.repo.fleet(SCOPE,action="purge",now=NOW+3600)
        self.assertEqual(purged["purged"],1)
        with self.assertRaises(ValueError):self.repo.fleet(SCOPE,action="create",**self.args)

    def test_expired_fleet_cannot_publish_late_round(self):
        from skeleton.ai.webcrawler.navigation_semantics import digest
        op=campaign._operation("fleet-late-publication")
        supplied,command=fleet._command(self.objectives,4,1)
        with self.repo._db() as db:
            owner=owner_key(SCOPE);db.execute("BEGIN IMMEDIATE")
            token,_=fleet._claim(db,owner,self.id,op,command,supplied,4,1,NOW)
            job=fleet._job(db,owner,self.id,op);db.execute("COMMIT")
            with self.assertRaises(ValueError):
                campaign.advance(db,owner,campaign_id=job["campaign"],query=self.query,
                    operation=digest(["fleet-round",self.id,op]),expected_revision=job["campaign_revision"],
                    budget=job["round_budget"],now=NOW+fleet.MAX_LEASE,_fleet_claim=(self.id,op,token))
        self.assertEqual(self.current(NOW+fleet.MAX_LEASE)["remaining"],40960)


if __name__=="__main__":unittest.main()
