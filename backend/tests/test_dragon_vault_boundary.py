"""Cold-custody adapter regressions using actual witnessed crawler snapshots.

Mocked Mongo mutation receipts validate ordering and fences; these tests are
not a substitute for independent multi-process Mongo crash qualification.
"""
from __future__ import annotations

import copy
from datetime import timedelta
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.dragon_crawler import CrawlerError,DragonCrawlerApplication
from skeleton.ai.webcrawler.dragon_archive_grant import create_grant
from skeleton.ai.webcrawler.dragon_treasury_vault import make_marker
from test_dragon_sanctuary_boundary import application,fixture,SCOPE


class VaultBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def expired(self,*,stage="pending",released=False):
        row,captured=fixture()
        now=captured+timedelta(days=2)
        marker=make_marker(operation="a"*64,request_digest="b"*64,
            snapshot_digest=row["snapshot"]["snapshot_digest"],now=now.timestamp()-30)
        marker.update(state=stage,active_slot_released=released)
        row["treasury_vault"]=marker
        return row,now

    def app(self,row,*,reserve=True,publish=True,release=True,final=True):
        app=object.__new__(DragonCrawlerApplication)
        app.sessions=Mock()
        app.limits=Mock()
        app.sessions.find_one=AsyncMock(return_value=row)
        events=[]
        async def quota(query,update):
            if "$addToSet" in update:
                events.append(("reserve",query,update))
                return Mock(matched_count=int(reserve))
            events.append(("release",query,update))
            return Mock(matched_count=int(release))
        async def mutation(query,update):
            fields=update.get("$set",{})
            if fields.get("treasury_vault.state")=="vaulted":
                events.append(("publish",query,update))
                return Mock(modified_count=int(publish))
            if fields.get("treasury_vault.active_slot_released") is True:
                events.append(("receipt",query,update))
                return Mock(modified_count=int(final))
            events.append(("defer",query,update))
            return Mock(modified_count=1)
        app.sessions.update_one=AsyncMock(side_effect=mutation)
        app.limits.update_one=AsyncMock(side_effect=quota)
        return app,events

    async def test_actual_expired_primary_then_reserve_publish_release(self):
        row,now=self.expired()
        original=copy.deepcopy(row["snapshot"])
        app,events=self.app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app._finish_treasury_retirement(SCOPE,row["_id"])
        self.assertEqual(result,"vaulted")
        self.assertEqual([x[0] for x in events],["reserve","publish","release","receipt"])
        self.assertEqual(events[0][1]["owner_id"],SCOPE["owner_id"])
        self.assertEqual(events[1][1]["version"],row["version"])
        self.assertEqual(events[1][1]["treasury_vault.operation"],row["treasury_vault"]["operation"])
        self.assertEqual(events[2][1]["vault_ids"],row["_id"])
        self.assertEqual(events[3][1]["version"],row["version"]+1)
        self.assertNotIn("snapshot",events[1][2]["$set"])
        self.assertNotIn("archive_grant",events[1][2]["$set"])
        self.assertEqual(row["snapshot"],original)

    async def test_capacity_exhaustion_never_frees_active_quota(self):
        row,now=self.expired()
        app,events=self.app(row,reserve=False)
        with patch("core.dragon_crawler._now",return_value=now):
            outcome=await app._finish_treasury_retirement(SCOPE,row["_id"])
        self.assertEqual(outcome,"capacity_or_quota_held")
        self.assertEqual([x[0] for x in events],["reserve","defer"])

    async def test_lost_publication_or_owner_cas_does_not_release_active_slot(self):
        row,now=self.expired()
        app,events=self.app(row,publish=False)
        with patch("core.dragon_crawler._now",return_value=now):
            outcome=await app._finish_treasury_retirement(SCOPE,row["_id"])
        self.assertEqual(outcome,"superseded")
        self.assertEqual([x[0] for x in events],["reserve","publish"])

    async def test_recovery_after_publication_never_reserves_second_slot(self):
        row,now=self.expired(stage="vaulted")
        app,events=self.app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual(await app._finish_treasury_retirement(SCOPE,row["_id"]),"vaulted")
        self.assertEqual([x[0] for x in events],["release","receipt"])

    async def test_recovery_after_release_reply_loss_is_idempotent(self):
        row,now=self.expired(stage="vaulted")
        app,events=self.app(row,final=False)
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual(await app._finish_treasury_retirement(SCOPE,row["_id"]),"superseded")
        app,events=self.app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual(await app._finish_treasury_retirement(SCOPE,row["_id"]),"vaulted")
        self.assertEqual([x[0] for x in events],["release","receipt"])

    async def test_exact_completed_receipt_is_noop(self):
        row,now=self.expired(stage="vaulted",released=True)
        app,events=self.app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual(await app._finish_treasury_retirement(SCOPE,row["_id"]),"vaulted")
        self.assertEqual(events,[])

    async def test_missing_vault_reservation_never_claims_release(self):
        row,now=self.expired(stage="vaulted")
        app,events=self.app(row,release=False)
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual(await app._finish_treasury_retirement(SCOPE,row["_id"]),"quota_held")
        self.assertEqual([x[0] for x in events],["release","defer"])

    async def test_live_consent_worker_watch_or_corrupt_witness_blocks_retirement(self):
        original,now=self.expired()
        for field,value in (("worker_token","live"),("lease_until",now),
                            ("treasury_watch",{"enabled":True,"expires_at":now.timestamp()+60}),
                            ("checkpoint_identity",{}),("consent_expires_at",now+timedelta(hours=1))):
            row=copy.deepcopy(original)
            row[field]=value
            app,events=self.app(row)
            with patch("core.dragon_crawler._now",return_value=now):
                self.assertEqual(await app._finish_treasury_retirement(SCOPE,row["_id"]),"held")
            self.assertEqual([x[0] for x in events],["defer"])

    async def test_explicit_intent_precedes_quota_and_replay_does_not_reauthorize(self):
        row,now=self.expired()
        row.pop("treasury_vault")
        app,events=self.app(row)
        app._admit=AsyncMock(return_value={"fixture":"admitted"})
        app._finish_treasury_retirement=AsyncMock(return_value="capacity_or_quota_held")
        async def mutation(query,update):
            self.assertEqual(query["version"],7)
            self.assertEqual(query["$expr"],{"$lte":["$consent_expires_at","$$NOW"]})
            row.update(update["$set"])
            row["version"]+=1
            return Mock(modified_count=1)
        app.sessions.update_one=AsyncMock(side_effect=mutation)
        principal={"role":"editor"}
        command={"expected_version":7,"idempotency_key":"retire-fixture","retention_acknowledged":True}
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            first=await app.retire_treasury_session(SCOPE,row["_id"],command,principal=principal)
            second=await app.retire_treasury_session(SCOPE,row["_id"],command,principal=principal)
        self.assertEqual(first,second)
        self.assertEqual(first["vault"]["state"],"pending")
        self.assertFalse(first["vault"]["historical_grant_extended"])
        app._admit.assert_awaited_once()
        app.sessions.update_one.assert_awaited_once()
        self.assertEqual(app._finish_treasury_retirement.await_count,2)

    async def test_other_owner_or_viewer_cannot_retire(self):
        row,now=self.expired()
        app,events=self.app(row)
        command={"expected_version":7,"idempotency_key":"retire-fixture","retention_acknowledged":True}
        for scope,role in (({"tenant_id":"other","owner_id":"owner"},"editor"),(SCOPE,"viewer")):
            with patch("core.dragon_crawler.authenticated_scope",return_value=scope):
                with self.assertRaises(CrawlerError) as err:
                    await app.retire_treasury_session(SCOPE,row["_id"],command,principal={"role":role})
            self.assertEqual(err.exception.status,403)
        app.sessions.find_one.assert_not_awaited()

    async def test_selected_vault_reads_only_archival_permission_and_owner_filter(self):
        row,now=self.expired(stage="vaulted",released=True)
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp()-60,days=7)
        app=application(row)
        with patch("core.dragon_crawler._now",return_value=now):
            value=await app.companion_treasury(SCOPE,mode="historic_only",vault_sessions=[row["_id"]])
        self.assertEqual(value["vault_window"],[row["_id"]])
        self.assertEqual(value["historic_indexed"],1)
        self.assertEqual(value["current_indexed"],0)
        self.assertEqual(value["revisit_plan"],[])
        self.assertEqual(value["evolution"]["expedition_growth"],0)
        self.assertTrue(value["candidate_limit_reached"])
        for call in app.sessions.find.call_args_list:
            self.assertEqual(call.args[0]["owner_id"],SCOPE["owner_id"])
            self.assertEqual(call.args[0]["treasury_vault.state"],"vaulted")
            self.assertEqual(call.args[0]["_id"],{"$in":[row["_id"]]})
        app.sessions.update_one.assert_not_awaited()

    async def test_missing_selected_record_and_current_mode_fail_closed(self):
        row,now=self.expired(stage="vaulted",released=True)
        app=application(row)
        with patch("core.dragon_crawler._now",return_value=now):
            for mode,ids in (("current_only",[row["_id"]]),("historic_only",["foreign"])):
                with self.assertRaises(CrawlerError) as err:
                    await app.companion_treasury(SCOPE,mode=mode,vault_sessions=ids)
                self.assertIn(err.exception.code,{"crawler_vault_changed","crawler_vault_history_only"})

    async def test_erasure_releases_both_slots_and_erases_marker(self):
        row,now=self.expired(stage="vaulted",released=True)
        app,events=self.app(row)
        app.sessions.update_one=AsyncMock(return_value=Mock(modified_count=1))
        app.limits.update_one=AsyncMock(return_value=Mock(matched_count=1))
        app._drain=AsyncMock(return_value={"quiescent":True})
        with patch("core.dragon_crawler._now",return_value=now):
            value=await app.delete(SCOPE,row["_id"],{"idempotency_key":"erase-fixture","expected_version":row["version"]})
        self.assertEqual(value["status"],"deleted")
        mutation=app.sessions.update_one.await_args.args[1]
        self.assertIn("snapshot",mutation["$unset"])
        self.assertIn("treasury_vault",mutation["$unset"])
        self.assertIn("treasury_index",mutation["$unset"])
        self.assertEqual(app.limits.update_one.await_args.args[1],{"$pull":{"session_ids":row["_id"],"vault_ids":row["_id"]}})


if __name__=="__main__":
    unittest.main()
