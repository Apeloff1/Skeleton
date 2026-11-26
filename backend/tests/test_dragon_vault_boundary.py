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

    async def test_postpublication_witness_loss_does_not_release_active_capacity(self):
        row,now=self.expired(stage="vaulted")
        row["checkpoint_identity"]={}
        app,events=self.app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual(await app._finish_treasury_retirement(SCOPE,row["_id"]),"held")
        self.assertEqual([x[0] for x in events],["defer"])

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


class QuotaBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def harness(self,*,modified=1):
        from core.dragon_crawler import _digest
        app=object.__new__(DragonCrawlerApplication)
        app.ensure_indexes=AsyncMock()
        app.sessions=Mock()
        app.limits=Mock()
        _,now=fixture()
        document={"_id":_digest(SCOPE),**SCOPE,"session_ids":["gone","missing","live"],
                  "vault_ids":["gone"],"treasury_quota_due":0}
        rows=[{"_id":"gone",**SCOPE,"version":4,"status":"deleted",
               "deletion":{"operation":"a"*64,"request_digest":"b"*64}},
              {"_id":"live",**SCOPE,"version":2,"status":"queued"}]
        for collection,values in ((app.sessions,rows),(app.limits,[document])):
            cursor=collection.find.return_value
            cursor.sort.return_value=cursor
            cursor.limit.return_value=cursor
            cursor.max_time_ms.return_value=cursor
            cursor.to_list=AsyncMock(return_value=values)
        app.limits.update_one=AsyncMock(return_value=Mock(modified_count=modified))
        app.limits.find_one=AsyncMock(return_value=document)
        return app,document,rows,now

    async def test_only_exact_tombstone_released_no_source_mutations(self):
        app,doc,rows,now=self.harness()
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.reconcile_treasury_quotas()
        self.assertEqual(result["reclaimed"],1)
        self.assertEqual(result["missing_held"],1)
        query,update=app.limits.update_one.await_args.args
        self.assertEqual(query["session_ids"],doc["session_ids"])
        self.assertEqual(query["vault_ids"],doc["vault_ids"])
        self.assertEqual(query["owner_id"],SCOPE["owner_id"])
        self.assertEqual(update["$pull"],{"session_ids":{"$in":["gone"]},"vault_ids":{"$in":["gone"]}})
        app.sessions.update_one.assert_not_called()
        app.sessions.delete_one.assert_not_called()

    async def test_concurrent_quota_change_never_reports_reclaimed(self):
        app,doc,rows,now=self.harness(modified=0)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.reconcile_treasury_quotas()
        self.assertEqual(result["superseded"],1)
        self.assertEqual(result["reclaimed"],0)

    async def test_read_health_is_fenced_and_never_returns_ids(self):
        app,doc,rows,now=self.harness()
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.treasury_quota_status(SCOPE)
        self.assertEqual(result["distinct_reserved"],3)
        self.assertEqual(result["tombstoned"],1)
        self.assertEqual(result["missing"],1)
        self.assertFalse(result["missing_auto_reclaimed"])
        self.assertNotIn("session_ids",result)
        self.assertNotIn("gone",str(result))
        app.limits.update_one.assert_not_awaited()
        app.limits.find_one.side_effect=[doc,{**doc,"session_ids":["new"]}]
        with patch("core.dragon_crawler._now",return_value=now):
            with self.assertRaises(CrawlerError):
                await app.treasury_quota_status(SCOPE)


class DiscoveryBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def harness(self):
        row,now=VaultBoundaryTests().expired(stage="vaulted",released=True)
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp()-60,days=7)
        app=object.__new__(DragonCrawlerApplication)
        app.ensure_indexes=AsyncMock()
        app.sessions=Mock()
        cursor=app.sessions.find.return_value
        cursor.sort.return_value=cursor
        cursor.limit.return_value=cursor
        cursor.max_time_ms.return_value=cursor
        metadata={"_id":row["_id"],"version":row["version"],"archive_grant":{
            "issued_at":row["archive_grant"]["issued_at"],"expires_at":row["archive_grant"]["expires_at"]}}
        cursor.to_list=AsyncMock(return_value=[metadata])
        app.sessions.find_one=AsyncMock(return_value=row)
        return app,row,metadata,now

    async def test_actual_granted_source_scan_and_no_text_return(self):
        app,row,metadata,now=self.harness()
        from skeleton.ai.webcrawler.dragon_companion import _lexemes
        source=next(iter(row["snapshot"]["sources"].values()))
        query=_lexemes(source["text"])[0]
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.discover_treasury_vault(SCOPE,query=query)
        self.assertEqual(result["qualified"],1)
        self.assertEqual(result["matches"][0]["session_id"],row["_id"])
        self.assertEqual(result["matches"][0]["matched_sources"],1)
        self.assertFalse(result["source_text_returned"])
        self.assertFalse(result["model_context_permission"])
        self.assertEqual(result["earliest_expiry"],row["archive_grant"]["expires_at"])
        self.assertNotIn("text",result["matches"][0])
        self.assertEqual(app.sessions.find_one.await_args.args[0]["owner_id"],SCOPE["owner_id"])
        self.assertEqual(app.sessions.find_one.await_args.args[0]["version"],row["version"])
        app.sessions.update_one.assert_not_called()

    async def test_missing_archive_grant_never_reaches_text_scanner(self):
        app,row,metadata,now=self.harness()
        row.pop("archive_grant")
        metadata.pop("archive_grant")
        with patch("core.dragon_crawler._now",return_value=now),patch(
            "skeleton.ai.webcrawler.dragon_vault_discovery.summarize_sources") as scanner:
            result=await app.discover_treasury_vault(SCOPE,query="optical")
        self.assertEqual(result["no_grant"],1)
        self.assertEqual(result["matches"],[])
        scanner.assert_not_called()

    async def test_corrupt_primary_holds_even_with_grant(self):
        app,row,metadata,now=self.harness()
        row["checkpoint_identity"]={}
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.discover_treasury_vault(SCOPE,query="optical")
        self.assertEqual(result["held"],1)
        self.assertEqual(result["eligible_sources"],0)

    async def test_new_version_invalidates_catalogue(self):
        app,row,metadata,now=self.harness()
        app.sessions.find.return_value.to_list.side_effect=[[metadata],[{**metadata,"version":metadata["version"]+1}]]
        with patch("core.dragon_crawler._now",return_value=now):
            with self.assertRaises(CrawlerError) as err:
                await app.discover_treasury_vault(SCOPE,query="optical")
        self.assertEqual(err.exception.code,"crawler_vault_search_changed")


class PhysicalDiscoveryAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_request_does_not_refund_physical_cpu_permit(self):
        import asyncio
        import threading
        from core.dragon_vault import _bounded_discovery_cpu
        gate=threading.BoundedSemaphore(1)
        entered=threading.Event()
        release=threading.Event()
        def physical():
            entered.set()
            if not release.wait(3):
                raise RuntimeError("fixture timeout")
            return "finished"
        with patch("core.dragon_vault._DISCOVERY_CPU",gate):
            task=asyncio.create_task(_bounded_discovery_cpu(physical))
            try:
                for _ in range(200):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.005)
                self.assertTrue(entered.is_set())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.assertRaises(CrawlerError) as failure:
                    await _bounded_discovery_cpu(lambda: "must not run")
                self.assertEqual(failure.exception.code,"crawler_vault_busy")
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                # Allow the uncancelled executor future's done callback to
                # release the gate before the mock binding is restored.
                for _ in range(400):
                    if gate.acquire(blocking=False):
                        gate.release()
                        break
                    await asyncio.sleep(.005)
                else:
                    self.fail("physical discovery permit was not released")
            self.assertEqual(await _bounded_discovery_cpu(lambda: "ready"),"ready")

    async def test_busy_is_not_misreported_as_held_chamber(self):
        app,row,metadata,now=DiscoveryBoundaryTests().harness()
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_vault._bounded_discovery_cpu",
                side_effect=CrawlerError("crawler_vault_busy","busy",429)):
            with self.assertRaises(CrawlerError) as failure:
                await app.discover_treasury_vault(SCOPE,query="optical")
        self.assertEqual(failure.exception.code,"crawler_vault_busy")


class VaultRestoreTests(unittest.IsolatedAsyncioTestCase):
    def harness(self,damaged=True):
        from core.dragon_checkpoint_replica import checkpoint_fields
        row,now=VaultBoundaryTests().expired(stage="vaulted",released=True)
        row.update(checkpoint_fields(row["snapshot"]))
        # Mongo's JSON-compatible arrays replace Python tuples, without
        # changing canonical encoded bytes or the immutable digest.
        from core.dragon_crawler import _plain
        original=_plain(row["snapshot"])
        row["snapshot"]=copy.deepcopy(original)
        if damaged:
            row["snapshot"]={"damaged":True}
        row["archive_grant"]=create_grant(snapshot=original,policies={},now=now.timestamp()-4*86400,days=1)
        app,events=VaultBoundaryTests().app(row)
        app._admit=AsyncMock(return_value={"receipt":"admitted"})
        async def mutation(query,update):
            row.update(update["$set"])
            for key in update.get("$unset",{}):
                row.pop(key,None)
            row["version"]+=update["$inc"]["version"]
            return Mock(modified_count=1)
        app.sessions.update_one=AsyncMock(side_effect=mutation)
        command={"expected_version":row["version"],"idempotency_key":"restore-test","retention_acknowledged":True}
        return app,row,original,now,command

    async def test_exact_replica_restores_primary_without_renewing_expired_grant(self):
        app,row,original,now,command=self.harness()
        grant=copy.deepcopy(row["archive_grant"])
        row["treasury_index"]={"old":True}
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            receipt=await app.restore_treasury_vault(SCOPE,row["_id"],command,principal={"role":"editor"})
            replay=await app.restore_treasury_vault(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(receipt,replay)
        self.assertEqual(receipt["outcome"],"restored")
        self.assertEqual(row["snapshot"],original)
        self.assertEqual(row["archive_grant"],grant)
        self.assertNotIn("treasury_index",row)
        self.assertFalse(receipt["capture_consent_extended"])
        self.assertFalse(receipt["historical_grant_extended"])
        app._admit.assert_awaited_once()
        app.sessions.update_one.assert_awaited_once()
        fence,mutation=app.sessions.update_one.await_args.args
        self.assertEqual(fence["version"],command["expected_version"])
        self.assertEqual(fence["$expr"],{"$lte":["$consent_expires_at","$$NOW"]})
        self.assertEqual(fence["treasury_vault.snapshot_digest"],original["snapshot_digest"])
        self.assertNotIn("archive_grant",mutation["$set"])
        self.assertNotIn("consent",mutation["$set"])
        self.assertNotIn("checkpoint_identity",mutation["$set"])

    async def test_healthy_primary_is_noop_even_when_replica_is_damaged(self):
        app,row,original,now,command=self.harness(damaged=False)
        row["checkpoint_replica"]="corrupt"
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            receipt=await app.restore_treasury_vault(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(receipt["outcome"],"already_intact")
        app._admit.assert_not_awaited()
        app.sessions.update_one.assert_not_awaited()

    async def test_wrong_replica_witness_and_uncertain_worker_fail_closed(self):
        for field,value in (("checkpoint_replica","AAAA"),("checkpoint_identity",{}),
                            ("last_worker_exit_confirmed",False),("worker_token","inflight")):
            app,row,original,now,command=self.harness()
            row[field]=value
            with patch("core.dragon_crawler._now",return_value=now),patch(
                    "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
                with self.assertRaises(CrawlerError) as error:
                    await app.restore_treasury_vault(SCOPE,row["_id"],command,principal={"role":"editor"})
            self.assertEqual(error.exception.code,"crawler_vault_restore_held")
            app._admit.assert_not_awaited()
            app.sessions.update_one.assert_not_awaited()

    async def test_concurrent_erasure_or_grant_change_wins(self):
        app,row,original,now,command=self.harness()
        app.sessions.update_one=AsyncMock(return_value=Mock(modified_count=0))
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            with self.assertRaises(CrawlerError) as error:
                await app.restore_treasury_vault(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(error.exception.code,"crawler_conflict")
        self.assertEqual(row["snapshot"],{"damaged":True})

    async def test_redundancy_reports_exact_and_repairable_bytes_without_writes(self):
        for damaged,expected in ((True,"repairable_primary"),(False,"redundant")):
            app,row,original,now,command=self.harness(damaged=damaged)
            with patch("core.dragon_crawler._now",return_value=now):
                result=await app.treasury_vault_redundancy(SCOPE,row["_id"])
            self.assertEqual(result["state"],expected)
            self.assertEqual(result["snapshot_digest"],original["snapshot_digest"])
            self.assertFalse(result["source_text_returned"])
            self.assertFalse(result["independent_backup"])
            app._admit.assert_not_awaited()
            app.sessions.update_one.assert_not_awaited()

    async def test_corrupt_replica_with_intact_primary_is_primary_only(self):
        app,row,original,now,command=self.harness(damaged=False)
        row["checkpoint_replica"]="invalid"
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.treasury_vault_redundancy(SCOPE,row["_id"])
        self.assertEqual(result["state"],"primary_only")
        self.assertEqual(result["replica"],"held")

    async def test_malformed_restore_receipt_cannot_be_replayed(self):
        app,row,original,now,command=self.harness()
        row["treasury_vault_restore"]={"operation":"a"*64}
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            with self.assertRaises(CrawlerError) as error:
                await app.restore_treasury_vault(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(error.exception.code,"crawler_vault_restore_held")
        app._admit.assert_not_awaited()

    async def test_explicit_duplicate_repair_preserves_original_and_grant(self):
        app,row,original,now,command=self.harness(damaged=False)
        witness=copy.deepcopy(row["checkpoint_identity"])
        grant=copy.deepcopy(row["archive_grant"])
        row["checkpoint_replica"]="damaged"
        from core.dragon_checkpoint_replica import decode_exact_replica
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            first=await app.repair_treasury_vault_replica(SCOPE,row["_id"],command,principal={"role":"editor"})
            second=await app.repair_treasury_vault_replica(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(first,second)
        self.assertEqual(first["outcome"],"repaired")
        self.assertEqual(decode_exact_replica(row["checkpoint_replica"],witness),original)
        self.assertEqual(row["checkpoint_identity"],witness)
        self.assertEqual(row["archive_grant"],grant)
        _,update=app.sessions.update_one.await_args.args
        self.assertNotIn("snapshot",update["$set"])
        self.assertNotIn("checkpoint_identity",update["$set"])
        self.assertNotIn("archive_grant",update["$set"])
        app._admit.assert_awaited_once()
        app.sessions.update_one.assert_awaited_once()

    async def test_duplicate_repair_denies_unavailable_original_reservation(self):
        app,row,original,now,command=self.harness(damaged=False)
        row["checkpoint_identity"].update(replica_available=False,reason="write_envelope_capacity")
        row["checkpoint_replica"]=None
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            with self.assertRaises(CrawlerError) as error:
                await app.repair_treasury_vault_replica(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(error.exception.code,"crawler_vault_replica_held")
        app._admit.assert_not_awaited()

    async def test_duplicate_repair_cannot_use_corrupt_primary(self):
        app,row,original,now,command=self.harness()
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            with self.assertRaises(CrawlerError) as error:
                await app.repair_treasury_vault_replica(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(error.exception.code,"crawler_vault_replica_held")
        app._admit.assert_not_awaited()

    async def test_duplicate_repair_already_intact_is_noop(self):
        app,row,original,now,command=self.harness(damaged=False)
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            result=await app.repair_treasury_vault_replica(SCOPE,row["_id"],command,principal={"role":"editor"})
        self.assertEqual(result["outcome"],"already_intact")
        app._admit.assert_not_awaited()
        app.sessions.update_one.assert_not_awaited()

    async def test_viewer_cannot_restore(self):
        app,row,original,now,command=self.harness()
        with patch("core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            with self.assertRaises(CrawlerError) as error:
                await app.restore_treasury_vault(SCOPE,row["_id"],command,principal={"role":"viewer"})
        self.assertEqual(error.exception.status,403)
        app.sessions.find_one.assert_not_awaited()


class VaultScrubTests(unittest.IsolatedAsyncioTestCase):
    def harness(self,damaged=False):
        app,row,original,now,command=VaultRestoreTests().harness(damaged=damaged)
        app.ensure_indexes=AsyncMock()
        cursor=app.sessions.find.return_value
        cursor.sort.return_value=cursor
        cursor.limit.return_value=cursor
        cursor.max_time_ms.return_value=cursor
        cursor.to_list=AsyncMock(return_value=[{k:row[k] for k in ("_id","tenant_id","owner_id","version")}])
        app.sessions.update_one=AsyncMock(return_value=Mock(modified_count=1))
        return app,row,now

    async def test_patrol_records_exact_observation_without_changing_authority(self):
        app,row,now=self.harness()
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["redundant"],1)
        self.assertEqual(app.sessions.update_one.await_count,2)
        query,update=app.sessions.update_one.await_args.args
        audit=update["$set"]["treasury_vault_scrub"]
        self.assertEqual(audit["version"],row["version"])
        self.assertEqual(audit["snapshot_digest"],row["snapshot"]["snapshot_digest"])
        self.assertEqual(set(update["$set"]),{"treasury_vault_scrub","treasury_vault_scrub_due"})
        self.assertNotIn("$inc",update)
        self.assertEqual(query["treasury_vault_scrub_due"],now.timestamp()+180)
        self.assertIn("$expr",query)
        app._admit.assert_awaited_once()
        public=app._public_vault_scrub({**row,"treasury_vault_scrub":audit},now.timestamp(),audit["snapshot_digest"])
        self.assertFalse(public["live_verified"])
        self.assertIsNone(app._public_vault_scrub({**row,"version":row["version"]+1,"treasury_vault_scrub":audit},
                                                now.timestamp(),audit["snapshot_digest"]))

    async def test_damaged_primary_detected_but_not_repaired_automatically(self):
        app,row,now=self.harness(damaged=True)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["repairable_primary"],1)
        self.assertEqual(row["snapshot"],{"damaged":True})
        self.assertNotIn("snapshot",app.sessions.update_one.await_args.args[1]["$set"])

    async def test_lost_lease_cannot_publish_audit(self):
        app,row,now=self.harness()
        app.sessions.update_one.side_effect=[Mock(modified_count=1),Mock(modified_count=0)]
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["superseded"],1)
        self.assertEqual(result["redundant"],0)

    async def test_catalogue_keeps_damaged_primary_repair_reachable(self):
        app,row,now=self.harness(damaged=True)
        # Actual Mongo projection has no binding when primary is damaged.
        meta={k:row[k] for k in ("_id","version","treasury_vault","checkpoint_identity","archive_grant")}
        app.sessions.find.return_value.to_list=AsyncMock(return_value=[meta])
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.treasury_vault_catalog(SCOPE)
        item=result["sessions"][0]
        self.assertEqual(item["vault"]["state"],"vaulted")
        self.assertIsNone(item["legacy_runtime"])
        self.assertFalse(item["integrity_held"])
        self.assertIsNone(item["last_scrub"])


class VaultCareTests(unittest.IsolatedAsyncioTestCase):
    def harness(self,damaged=True,enabled=True):
        from skeleton.ai.webcrawler.dragon_vault_care import issue_care
        app,row,now=VaultScrubTests().harness(damaged=damaged)
        app._grant_principal=AsyncMock()
        row["treasury_vault_care"]=issue_care(operation="a"*64,request_digest="b"*64,
            snapshot_digest=row["treasury_vault"]["snapshot_digest"],principal_email="owner@example.test",
            now=now.timestamp()-10,days=7,budget=2,enabled=enabled)
        if not damaged:
            row["checkpoint_replica"]="bad"
        return app,row,now

    async def test_patrol_consumes_grant_in_same_cas_as_repair(self):
        for damaged,side,field in ((True,"primary","snapshot"),(False,"replica","checkpoint_replica")):
            app,row,now=self.harness(damaged=damaged)
            with patch("core.dragon_crawler._now",return_value=now):
                result=await app.scrub_treasury_vault()
            self.assertEqual(result["auto_"+side+"_repaired"],1)
            fence,mutation=app.sessions.update_one.await_args.args
            self.assertEqual(fence["treasury_vault_care"],row["treasury_vault_care"])
            self.assertEqual(mutation["$set"]["treasury_vault_care"]["used"],1)
            history=mutation["$set"]["treasury_vault_care_history"]
            self.assertEqual(history["entries"][-1]["kind"],"auto_"+side)
            self.assertEqual(history["entries"][-1]["used"],1)
            self.assertEqual(history["entries"][-1]["version"],row["version"]+1)
            self.assertEqual(fence["treasury_vault_care_history"],{"$exists":False})
            self.assertEqual(mutation["$set"]["treasury_vault_care"]["last_repair"]["side"],side)
            self.assertIn(field,mutation["$set"])
            self.assertEqual(mutation["$inc"],{"version":1})
            self.assertNotIn("archive_grant",mutation["$set"])
            self.assertNotIn("checkpoint_identity",mutation["$set"])
            self.assertIn({"$gt":["$treasury_vault_care.expires_at",{"$divide":[{"$toLong":"$$NOW"},1000]}]},fence["$expr"]["$and"])

    async def test_revoked_care_remains_observation_only(self):
        app,row,now=self.harness(enabled=False)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["repairable_primary"],1)
        self.assertEqual(result["auto_primary_repaired"],0)
        self.assertNotIn("snapshot",app.sessions.update_one.await_args.args[1]["$set"])

    async def test_disabled_or_downgraded_account_cannot_repair(self):
        app,row,now=self.harness()
        app._grant_principal=AsyncMock(side_effect=CrawlerError("crawler_grant_revoked","revoked",403))
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["auto_primary_repaired"],0)
        self.assertEqual(result["repairable_primary"],1)
        self.assertNotIn("snapshot",app.sessions.update_one.await_args.args[1]["$set"])
        app._grant_principal.assert_awaited_once()

    async def test_live_principal_rechecked_after_admission(self):
        app,row,now=self.harness()
        app._grant_principal=AsyncMock(side_effect=[None,CrawlerError("crawler_grant_revoked","revoked",403)])
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["auto_primary_repaired"],0)
        self.assertEqual(result["repairable_primary"],1)
        self.assertNotIn("snapshot",app.sessions.update_one.await_args.args[1]["$set"])
        self.assertEqual(app._grant_principal.await_count,2)

    async def test_revocation_or_concurrent_version_wins_publication(self):
        app,row,now=self.harness()
        app.sessions.update_one.side_effect=[Mock(modified_count=1),Mock(modified_count=0)]
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["superseded"],1)
        self.assertEqual(result["auto_primary_repaired"],0)

    async def test_corrupt_history_blocks_automatic_repair_but_not_owner_withdrawal(self):
        app,row,now=self.harness()
        row["treasury_vault_care_history"]={"damaged":True}
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.scrub_treasury_vault()
        self.assertEqual(result["auto_primary_repaired"],0)
        self.assertEqual(result["repairable_primary"],1)
        body={"expected_version":row["version"],"idempotency_key":"withdraw-history","enabled":False,
              "days":7,"repairs":2,"retention_acknowledged":False}
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            receipt=await app.configure_vault_care(SCOPE,row["_id"],body,principal={"role":"viewer","email":"owner@example.test"})
        self.assertFalse(receipt["care"]["active"])
        self.assertNotIn("treasury_vault_care_history",app.sessions.update_one.await_args.args[1]["$set"])

    async def test_history_read_is_version_fenced_and_redacted(self):
        from skeleton.ai.webcrawler.dragon_vault_care_history import append_history
        app,row,now=self.harness()
        row["treasury_vault_care_history"]=append_history(None,
            witness=row["treasury_vault"]["snapshot_digest"],version=row["version"],at=now.timestamp()-10,
            kind="grant",operation="a"*64,budget=2,used=0)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.treasury_vault_care_history(SCOPE,row["_id"])
        self.assertEqual(result["state"],"recorded")
        self.assertEqual(result["events"][0]["kind"],"grant")
        self.assertNotIn("operation",result["events"][0])
        self.assertFalse(result["independent_audit"])
        app.sessions.update_one.assert_not_awaited()
        app.sessions.find_one.side_effect=[row,{**row,"version":row["version"]+1}]
        with patch("core.dragon_crawler._now",return_value=now):
            with self.assertRaises(CrawlerError) as err:
                await app.treasury_vault_care_history(SCOPE,row["_id"])
        self.assertEqual(err.exception.code,"crawler_conflict")

    async def test_owner_issue_and_viewer_withdraw_without_source_read(self):
        app,row,now=self.harness()
        body={"expected_version":row["version"],"idempotency_key":"care-test","enabled":True,
              "days":7,"repairs":2,"retention_acknowledged":True}
        with patch("core.dragon_crawler._now",return_value=now),patch(
                "core.dragon_crawler.authenticated_scope",return_value=SCOPE):
            with self.assertRaises(CrawlerError):
                await app.configure_vault_care(SCOPE,row["_id"],body,principal={"role":"viewer","email":"owner@example.test"})
            receipt=await app.configure_vault_care(SCOPE,row["_id"],body,principal={"role":"editor","email":"owner@example.test"})
            self.assertTrue(receipt["care"]["active"])
            with patch.object(app,"_inspect_vault_redundancy") as inspect:
                revoked=await app.configure_vault_care(SCOPE,row["_id"],{**body,"enabled":False,
                    "idempotency_key":"withdraw-care","retention_acknowledged":False},principal={"role":"viewer","email":"owner@example.test"})
                inspect.assert_not_called()
        self.assertFalse(revoked["care"]["active"])
        self.assertFalse(revoked["care"]["network_authorized"])
        app._admit.assert_awaited_once()


class VaultHealthTests(unittest.IsolatedAsyncioTestCase):
    def harness(self):
        from skeleton.ai.webcrawler.dragon_vault_care import issue_care
        app,row,now=VaultScrubTests().harness()
        from core.dragon_crawler import _plain
        marker=row["treasury_vault"]
        digest=marker["snapshot_digest"]
        base={"version":7,"treasury_vault":marker,"checkpoint_identity":{"snapshot_digest":digest}}
        def observation(state,primary,replica,age):
            return {"schema":"skeleton.dragon.vault-scrub.v1","version":7,"snapshot_digest":digest,
                    "checked_at":now.timestamp()-age,"state":state,"primary":primary,"replica":replica}
        grant=issue_care(operation="a"*64,request_digest="b"*64,snapshot_digest=digest,
                         principal_email="owner@example.test",now=now.timestamp()-1,days=7,budget=2)
        rows=[
            {"_id":"a",**base,"treasury_vault_scrub":observation("redundant","exact","exact",1),
             "treasury_vault_care":grant,"treasury_vault_scrub_due":now.timestamp()+3600},
            {"_id":"b",**base,"treasury_vault_scrub":observation("repairable_primary","held","exact",1)},
            {"_id":"c",**base,"treasury_vault_scrub":observation("primary_only","exact","held",7*3600)},
            {"_id":"d",**base,"treasury_vault_scrub":{**observation("redundant","exact","exact",1),"version":6}},
            {"_id":"e",**base,"checkpoint_identity":{}},
            {"_id":"f",**base,"treasury_vault":{**marker,"state":"pending","active_slot_released":False}},
        ]
        app.sessions.find.return_value.to_list=AsyncMock(return_value=_plain(rows))
        return app,rows,now

    async def test_census_conserves_counts_and_never_reads_content(self):
        app,rows,now=self.harness()
        with patch("core.dragon_crawler._now",return_value=now):
            value=await app.treasury_vault_health(SCOPE)
        self.assertEqual(value["records"],6)
        self.assertEqual((value["pending"],value["vaulted"],value["marker_held"]),(1,4,1))
        self.assertEqual((value["redundant"],value["repairable_primary"],value["stale"],value["uninspected"]),(1,1,1,1))
        self.assertEqual((value["care_active"],value["remaining_repairs"],value["care_absent"]),(1,2,3))
        self.assertFalse(value["live_verified"])
        for call in app.sessions.find.call_args_list:
            self.assertEqual(call.args[0]["owner_id"],SCOPE["owner_id"])
            self.assertNotIn("snapshot",call.args[1])
            self.assertNotIn("checkpoint_replica",call.args[1])
        app.sessions.update_one.assert_not_awaited()

    async def test_midread_metadata_mutation_rejects_entire_census(self):
        app,rows,now=self.harness()
        app.sessions.find.return_value.to_list.side_effect=[rows,rows[:-1]]
        with patch("core.dragon_crawler._now",return_value=now):
            with self.assertRaises(CrawlerError) as error:
                await app.treasury_vault_health(SCOPE)
        self.assertEqual(error.exception.code,"crawler_vault_changed")


if __name__=="__main__":
    unittest.main()
