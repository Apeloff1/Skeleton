"""Owner-isolated campaign custody, replay, budget and graph readiness."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.dragon_navigation_federation import NavigationFederation
from core import dragon_navigation_graph as graph
from core import dragon_navigation_intelligence as intelligence
from core.dragon_game_corpus import owner_key
from test_dragon_navigation_federation import fixture,SCOPE,OTHER,NOW


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"corpus.sqlite3"
        self.federation=NavigationFederation(self.path)
        self.grants=[]
        for i in range(3):
            receipt=self.federation.publish(SCOPE,session_id=f"campaign-source-{i}",
                snapshot=fixture(i+100,32).snapshot(),rights_reference="fixture-source-rights",
                retention_seconds=7200,acknowledged=True,now=NOW)
            self.grants.append(receipt["grant_id"])
        self.query="flight manual"
        self.create_args=dict(query=self.query,operation="campaign-create-0001",
            budget=48,retention_seconds=3600,acknowledged=True,now=NOW)
        self.campaign=self.federation.campaign(SCOPE,action="create",**self.create_args)
        self.identifier=self.campaign["campaign_id"]

    def advance(self,revision,operation,budget=8,now=NOW,scope=SCOPE,query=None):
        return self.federation.campaign(scope,action="advance",campaign_id=self.identifier,
            query=self.query if query is None else query,operation=operation,
            expected_revision=revision,budget=budget,now=now)

    def test_restart_and_idempotent_rounds_with_budget(self):
        self.assertTrue(self.federation.campaign(SCOPE,action="create",**self.create_args)["replayed"])
        first=self.advance(1,"round-operation-0001")
        self.assertTrue(first["targets"])
        self.assertEqual(first["campaign"]["remaining"],48-first["spent"])
        self.assertEqual(first["spent"],sum(x["cost"] for x in first["targets"]))
        self.federation=NavigationFederation(self.path)
        replay=self.advance(1,"round-operation-0001")
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["plan_digest"],replay["plan_digest"])
        self.assertEqual(first["targets"],replay["targets"])
        self.assertEqual(replay["campaign"]["revision"],2)
        second=self.advance(2,"round-operation-0002")
        before={x["target_id"] for x in first["targets"]}
        after={x["target_id"] for x in second["targets"]}
        self.assertTrue(after)
        self.assertFalse(before&after)
        self.assertEqual(second["campaign"]["remaining"],48-first["spent"]-second["spent"])
        with self.assertRaises(ValueError):
            self.advance(2,"round-operation-0003")
        with self.assertRaises(ValueError):
            self.advance(1,"round-operation-0001",budget=9)
        with self.assertRaises(ValueError):
            self.advance(3,"round-operation-0004",query="different")
        with self.assertRaises(ValueError):
            self.advance(3,"round-operation-0004",scope=OTHER)
        history=self.federation.campaign(SCOPE,action="inspect",campaign_id=self.identifier,limit=1,now=NOW)
        self.assertEqual(history["next_cursor"],1)
        second_page=self.federation.campaign(SCOPE,action="inspect",campaign_id=self.identifier,after=1,now=NOW)
        self.assertEqual(second_page["rounds"][0]["ordinal"],2)

    def test_revocation_and_expiry_hide_saved_target_metadata(self):
        first=self.advance(1,"round-operation-0001")
        self.assertTrue(first["targets"])
        for grant in self.grants:self.federation.revoke(SCOPE,grant)
        replay=self.advance(1,"round-operation-0001")
        self.assertEqual(replay["targets"],[])
        self.assertEqual(replay["plan_digest"],first["plan_digest"])
        self.assertEqual(replay["spent"],first["spent"])
        self.assertEqual(self.advance(2,"round-operation-0002")["targets"],[])
        self.assertEqual(self.advance(1,"round-operation-0001",now=NOW+3600)["targets"],[])
        with self.assertRaises(ValueError):
            self.advance(3,"round-operation-0003",now=NOW+3600)
        purged=self.federation.campaign(SCOPE,action="purge",now=NOW+3600)
        self.assertEqual(purged["purged"],1)
        with self.assertRaises(ValueError):
            self.federation.campaign(SCOPE,action="create",**self.create_args)

    def test_owner_close_clears_target_memory_but_preserves_receipt(self):
        first=self.advance(1,"round-operation-0001")
        with self.assertRaises(ValueError):
            self.federation.campaign(OTHER,action="close",campaign_id=self.identifier,expected_revision=2,now=NOW)
        closed=self.federation.campaign(SCOPE,action="close",campaign_id=self.identifier,expected_revision=2,now=NOW)
        self.assertEqual(closed["state"],"closed")
        self.assertEqual(self.advance(1,"round-operation-0001")["targets"],[])
        with self.federation._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_campaign_targets").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM navigation_campaign_rounds").fetchone()[0],1)
            self.assertNotIn("flight manual",str(dict(db.execute("SELECT * FROM navigation_campaigns").fetchone())))

    def test_graph_certificate_does_not_scan_on_each_facet(self):
        with self.federation._db() as db:
            owner=owner_key(SCOPE)
            self.assertFalse(graph.index_incomplete(db,owner))
            db.execute("DELETE FROM navigation_indexed WHERE owner=? AND target=(SELECT MIN(id) FROM navigation_nodes WHERE owner=?)",(owner,owner))
            self.assertTrue(graph.index_incomplete(db,owner))
        self.federation.reindex(SCOPE)
        with self.federation._db() as db:self.assertFalse(graph.index_incomplete(db,owner_key(SCOPE)))

    def test_stale_plan_no_budget_debit(self):
        original=intelligence.plan
        def invalid(*args,**kwargs):
            result=original(*args,**kwargs)
            result["remaining"]=-1
            return result
        with patch.object(intelligence,"plan",side_effect=invalid):
            with self.assertRaises(ValueError):self.advance(1,"round-operation-0001")
        status=self.federation.campaign(SCOPE,action="inspect",campaign_id=self.identifier,now=NOW)
        self.assertEqual(status["campaign"]["remaining"],48)
        self.assertEqual(status["campaign"]["revision"],1)
        self.assertEqual(status["rounds"],[])


if __name__=="__main__":unittest.main()
