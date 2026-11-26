"""Exact checkpoint archive reads, owner/version fences, and grant expiration."""
from __future__ import annotations

import copy
from datetime import timedelta
import hashlib
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.dragon_crawler import DragonCrawlerApplication, CrawlerError
from skeleton.ai.webcrawler.dragon_archive_grant import create_grant
from test_dragon_sanctuary_boundary import fixture, SCOPE


class TreasuryPassageTests(unittest.IsolatedAsyncioTestCase):
    def app(self,row,*,stable=True):
        app=object.__new__(DragonCrawlerApplication)
        app._owned=AsyncMock(return_value=row)
        app.sessions=Mock()
        app.sessions.find_one=AsyncMock(return_value={"_id":row["_id"]} if stable else None)
        app.sessions.update_one=AsyncMock()
        return app

    async def test_historic_span_is_exact_but_never_model_context(self):
        row,captured=fixture()
        now=captured+timedelta(days=2)
        source_id=next(iter(row["snapshot"]["sources"]))
        source=row["snapshot"]["sources"][source_id]
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp(),days=7)
        app=self.app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            value=await app.treasury_passage(SCOPE,row["_id"],source_id,offset=3,length=17)
        self.assertEqual(value["text"],source["text"][3:20])
        self.assertEqual(value["span_sha256"],hashlib.sha256(value["text"].encode()).hexdigest())
        self.assertTrue(value["history_only"])
        self.assertFalse(value["model_context_permission"])
        self.assertFalse(value["training_permission"])
        self.assertEqual(value["next_offset"],20)
        app._owned.assert_awaited_once_with(SCOPE,row["_id"])
        self.assertEqual(app.sessions.find_one.await_args.args[0]["version"],row["version"])
        app.sessions.update_one.assert_not_awaited()

    async def test_expired_grant_and_withdrawal_cannot_read(self):
        row,captured=fixture()
        now=captured+timedelta(days=2)
        sid=next(iter(row["snapshot"]["sources"]))
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp(),days=1)
        for stamp,withdrawn in ((now+timedelta(days=2),False),(now,True)):
            altered=copy.deepcopy(row)
            if withdrawn:
                altered["source_use_policies"]={sid:{"enabled":False,"version":1,
                    "max_age_seconds":86400,"changed_at":now.isoformat()}}
            app=self.app(altered)
            with patch("core.dragon_crawler._now",return_value=stamp):
                with self.assertRaises(CrawlerError) as error:
                    await app.treasury_passage(SCOPE,row["_id"],sid)
            self.assertEqual(error.exception.status,403)

    async def test_concurrent_grant_revoke_invalidates_passage(self):
        row,now=fixture()
        sid=next(iter(row["snapshot"]["sources"]))
        app=self.app(row,stable=False)
        with patch("core.dragon_crawler._now",return_value=now):
            with self.assertRaises(CrawlerError) as error:
                await app.treasury_passage(SCOPE,row["_id"],sid)
        self.assertEqual(error.exception.status,409)


class TreasuryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_historical_segment_reused_with_live_policy(self):
        from core.dragon_crawler import DragonCrawlerApplication
        from skeleton.ai.webcrawler.dragon_index_manifest import build_manifest
        from test_dragon_sanctuary_boundary import application
        row,captured=fixture()
        now=captured+timedelta(days=2)
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp(),days=7)
        row["treasury_index"]=build_manifest(row["snapshot"],row["archive_grant"],now=now.timestamp())
        app=application(row)
        with patch("core.dragon_crawler._now",return_value=now):
            value=await app.companion_treasury(SCOPE,mode="historic_only")
        self.assertEqual(value["historic_indexed"],1)
        self.assertEqual(value["current_indexed"],0)
        self.assertEqual(value["materialized_payload_hits"],1)
        self.assertEqual(value["invalid_materialized_segments"],0)
        self.assertEqual(value["index_health"],{"active_grants":1,"qualified_segments":1,
            "missing_segments":0,"stale_segments":0,"invalid_segments":0,
            "eligible_archive_members":1,"materialized_archive_members":1})
        self.assertEqual(value["evolution"]["expedition_growth"],0)
        app.sessions.update_one.assert_not_awaited()

    async def test_missing_and_corrupt_index_health_does_not_grant_authority(self):
        from test_dragon_sanctuary_boundary import application
        row,captured=fixture()
        now=captured+timedelta(days=2)
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp(),days=7)
        for value,field in ((None,"missing_segments"),({"schema":"obsolete"},"stale_segments"),
                            ("broken","invalid_segments")):
            altered=copy.deepcopy(row)
            altered["treasury_index"]=value
            app=application(altered)
            with patch("core.dragon_crawler._now",return_value=now):
                result=await app.companion_treasury(SCOPE,mode="historic_only")
            self.assertEqual(result["index_health"][field],1)
            self.assertEqual(result["index_health"]["eligible_archive_members"],1)
            self.assertEqual(result["index_health"]["materialized_archive_members"],0)
            self.assertEqual(result["historic_indexed"],1)
            self.assertEqual(result["current_indexed"],0)
            self.assertEqual(result["evolution"]["expedition_growth"],0)
            app.sessions.update_one.assert_not_awaited()

    async def test_current_discovery_and_expired_historical_permissions_are_separate(self):
        from test_dragon_sanctuary_boundary import application
        row,now=fixture()
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp(),days=1)
        app=application(row)
        with patch("core.dragon_crawler._now",return_value=now):
            current=await app.companion_treasury(SCOPE,mode="current_only")
        self.assertGreater(current["evolution"]["expedition_growth"],0)
        self.assertEqual(current["index_health"]["active_grants"],1)
        expired=now+timedelta(days=2)
        app=application(row)
        with patch("core.dragon_crawler._now",return_value=expired):
            history=await app.companion_treasury(SCOPE,mode="historic_only")
        self.assertEqual(history["evolution"]["expedition_growth"],0)
        self.assertEqual(history["index_health"]["active_grants"],0)
        self.assertEqual(history["historic_indexed"],0)

    async def test_new_owner_session_invalidates_fenced_catalogue(self):
        from test_dragon_sanctuary_boundary import application
        row,now=fixture()
        app=application(row)
        original=[{"_id":row["_id"],"version":row["version"]}]
        app.sessions.find.return_value.to_list.side_effect=[original,original+[{"_id":"new","version":1}]]
        with patch("core.dragon_crawler._now",return_value=now):
            with self.assertRaises(CrawlerError) as caught:
                await app.companion_treasury(SCOPE,mode="current_only")
        self.assertEqual(caught.exception.code,"crawler_treasury_changed")

    async def test_replaced_watch_claim_cannot_authorize_old_physical_worker(self):
        row,now=fixture()
        app=object.__new__(DragonCrawlerApplication)
        app.sessions=Mock()
        child={**row,"treasury_watch_parent":{"parent_id":"parent"},"worker_watch_claim":"old-claim"}
        app.sessions.find_one=AsyncMock(return_value=child)
        app._watch_authority=AsyncMock(return_value={"claim_token":"new-claim","claim_until":now.timestamp()+100})
        with patch("core.dragon_crawler._now",return_value=now):
            with self.assertRaises(CrawlerError) as caught:
                await app._live(SCOPE,"child","worker",1,network_margin=True)
        self.assertEqual(caught.exception.code,"crawler_watch_lease")
        child["worker_watch_claim"]="new-claim"
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual(await app._live(SCOPE,"child","worker",1,network_margin=True),child)

    async def test_live_watch_representation_checks_actual_witnessed_parent(self):
        from skeleton.ai.webcrawler.dragon_treasury_watch import create_watch,claim_watch,child_binding
        row,captured=fixture()
        source=next(iter(row["snapshot"]["sources"].values()))
        issued=captured.timestamp()
        watch=create_watch(operation="d"*64,parent_id=row["_id"],scope=SCOPE,
            principal_email="owner@example.org",snapshot_digest=row["snapshot"]["snapshot_digest"],
            source=source,policy_version=0,now=issued,days=2,cycles=2,
            minimum_interval=21600,retention_days=1)
        now=captured+timedelta(hours=6,seconds=1)
        watch=claim_watch(watch,now=now.timestamp(),token="live")
        row["treasury_watch"]=watch
        app=object.__new__(DragonCrawlerApplication)
        app.sessions=Mock()
        app.sessions.find_one=AsyncMock(return_value=row)
        app._grant_principal=AsyncMock()
        binding=child_binding(watch)
        with patch("core.dragon_crawler._now",return_value=now):
            self.assertEqual((await app._watch_authority(SCOPE,binding,
                observed_source=copy.deepcopy(source)))["claim_token"],"live")
            changed=copy.deepcopy(source)
            changed["provenance"]["http_freshness"]["languages"]=["no"]
            with self.assertRaises(CrawlerError) as caught:
                await app._watch_authority(SCOPE,binding,observed_source=changed)
            self.assertEqual(caught.exception.code,"crawler_watch_representation")
        self.assertEqual(app._grant_principal.await_count,1)

    def maintenance_app(self,row,*,modified=1,admission_error=None):
        app=object.__new__(DragonCrawlerApplication)
        app.ensure_indexes=AsyncMock()
        app.sessions=Mock()
        cursor=app.sessions.find.return_value
        cursor.sort.return_value=cursor
        cursor.limit.return_value=cursor
        cursor.max_time_ms.return_value=cursor
        item={"_id":row["_id"],**SCOPE,"version":row["version"],"treasury_repair_due":0.}
        cursor.to_list=AsyncMock(return_value=[item])
        app.sessions.find_one=AsyncMock(return_value=row)
        app.sessions.update_one=AsyncMock(return_value=Mock(modified_count=modified))
        app._admit=AsyncMock(return_value={"receipt":"test"},side_effect=admission_error)
        return app

    def maintenance_fixture(self):
        row,captured=fixture()
        now=captured+timedelta(days=2)
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},
                                           now=now.timestamp()-60,days=3)
        row["treasury_repair_due"]=0.
        return row,now

    async def test_maintenance_repairs_missing_index_without_renewal(self):
        from skeleton.ai.webcrawler.dragon_index_manifest import load_manifest
        row,now=self.maintenance_fixture()
        original=copy.deepcopy(row["archive_grant"])
        app=self.maintenance_app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["repaired"],1)
        query,mutation=app.sessions.update_one.await_args.args
        self.assertEqual(query["version"],row["version"])
        self.assertEqual(query["treasury_repair_due"],now.timestamp()+180)
        self.assertEqual(query["archive_grant.expires_at"],original["expires_at"])
        claim_query,claim_update=app.sessions.update_one.await_args_list[0].args
        self.assertEqual(claim_query["treasury_repair_due"],0.)
        self.assertEqual(claim_update,{"$set":{"treasury_repair_due":now.timestamp()+180}})
        db_clock={"$divide":[{"$toLong":"$$NOW"},1000]}
        self.assertEqual(query["$expr"],{"$and":[{"$gt":["$archive_grant.expires_at",db_clock]},
                                                 {"$gt":["$treasury_repair_due",db_clock]}]})
        self.assertEqual(mutation["$inc"],{"version":1})
        self.assertNotIn("archive_grant",mutation["$set"])
        self.assertNotIn("snapshot",mutation["$set"])
        self.assertNotIn("updated_at",mutation["$set"])
        index=mutation["$set"]["treasury_index"]
        self.assertEqual(len(load_manifest(index,original,snapshot_digest=original["snapshot_digest"],
                                             now=now.timestamp())),1)
        self.assertEqual(row["archive_grant"],original)
        app._admit.assert_awaited_once()

    async def test_maintenance_healthy_audit_never_republishes_or_changes_version(self):
        from skeleton.ai.webcrawler.dragon_index_manifest import build_manifest
        row,now=self.maintenance_fixture()
        row["treasury_index"]=build_manifest(row["snapshot"],row["archive_grant"],now=now.timestamp()-30)
        from skeleton.ai.webcrawler.dragon_archive_routing import build_routing
        row["treasury_archive_route"]=build_routing(SCOPE,row["treasury_index"],row["archive_grant"],now=now.timestamp())
        app=self.maintenance_app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["healthy"],1)
        app._admit.assert_not_awaited()
        self.assertEqual(set(app.sessions.update_one.await_args.args[1]),{"$set"})
        self.assertEqual(set(app.sessions.update_one.await_args.args[1]["$set"]),{"treasury_repair_due"})

    async def test_maintenance_withdrawn_source_cannot_be_reindexed(self):
        row,now=self.maintenance_fixture()
        sid=next(iter(row["snapshot"]["sources"]))
        row["source_use_policies"]={sid:{"enabled":False,"version":1,
            "max_age_seconds":86400,"changed_at":now.isoformat()}}
        app=self.maintenance_app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["repaired"],1)
        self.assertEqual(app.sessions.update_one.await_args.args[1]["$set"]["treasury_index"]["source_count"],0)

    async def test_maintenance_cas_loss_is_not_reported_as_repair(self):
        row,now=self.maintenance_fixture()
        app=self.maintenance_app(row,modified=0)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["superseded"],1)
        self.assertEqual(result["repaired"],0)

    async def test_maintenance_lost_lease_prevents_storage_admission(self):
        row,now=self.maintenance_fixture()
        app=self.maintenance_app(row)
        after=now+timedelta(seconds=181)
        # Selection, reservation, grant verification, then elapsed CPU time.
        with patch("core.dragon_crawler._now",side_effect=[now,now,now,after]):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["superseded"],1)
        self.assertEqual(app.sessions.update_one.await_count,1)
        app._admit.assert_not_awaited()

    async def test_maintenance_cannot_publish_after_concurrent_owner_update(self):
        row,now=self.maintenance_fixture()
        app=self.maintenance_app(row)
        app.sessions.update_one.side_effect=[Mock(modified_count=1),Mock(modified_count=0)]
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["superseded"],1)
        self.assertEqual(result["repaired"],0)
        app._admit.assert_awaited_once()
        final=app.sessions.update_one.await_args.args[0]
        self.assertEqual(final["owner_id"],SCOPE["owner_id"])
        self.assertEqual(final["version"],row["version"])

    async def test_maintenance_storage_denial_defers_without_index(self):
        row,now=self.maintenance_fixture()
        app=self.maintenance_app(row,admission_error=CrawlerError("storage_denied","denied",503))
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["deferred"],1)
        self.assertEqual(set(app.sessions.update_one.await_args.args[1]["$set"]),{"treasury_repair_due"})

    async def test_maintenance_corrupt_witness_drops_only_derived_index(self):
        row,now=self.maintenance_fixture()
        row["treasury_index"]={"damaged":True}
        row["checkpoint_identity"]={}
        app=self.maintenance_app(row)
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.repair_treasury_segments()
        self.assertEqual(result["blocked"],1)
        self.assertEqual(app.sessions.update_one.await_args.args[1]["$unset"],{"treasury_index":"","treasury_archive_route":""})
        app._admit.assert_not_awaited()

    async def test_expired_posting_cleanup_preserves_snapshot_and_uses_exact_version(self):
        row,captured=fixture()
        now=captured+timedelta(days=2)
        app=object.__new__(DragonCrawlerApplication)
        app.ensure_indexes=AsyncMock()
        app.sessions=Mock()
        cursor=app.sessions.find.return_value
        cursor.sort.return_value=cursor
        cursor.limit.return_value=cursor
        cursor.max_time_ms.return_value=cursor
        expired={"_id":row["_id"],**SCOPE,"version":7,"treasury_index":{"expires_at":now.timestamp()-1}}
        cursor.to_list=AsyncMock(return_value=[expired])
        app.sessions.update_one=AsyncMock(return_value=Mock(modified_count=1))
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.purge_expired_treasury_segments()
        self.assertEqual(result,{"scanned":1,"purged":1,"source_records_erased":0})
        query,mutation=app.sessions.update_one.await_args.args
        self.assertEqual(query["version"],7)
        self.assertEqual(query["treasury_index.expires_at"],expired["treasury_index"]["expires_at"])
        self.assertEqual(mutation["$unset"],{"treasury_index":"","treasury_archive_route":""})


class RecoveryLaneTests(unittest.IsolatedAsyncioTestCase):
    async def test_ancillary_storage_failure_does_not_starve_repair(self):
        from core.dragon_crawler import recover_crawler_runs
        from pymongo.errors import PyMongoError
        app=Mock()
        app.recover=AsyncMock(return_value={"scanned":0})
        app.recover_treasury_watches=AsyncMock(side_effect=PyMongoError("fixture"))
        app.purge_expired_treasury_segments=AsyncMock(return_value={"purged":1})
        app.repair_treasury_segments=AsyncMock(return_value={"repaired":1})
        app.recover_treasury_retirements=AsyncMock(return_value={"vaulted":1})
        app.reconcile_treasury_quotas=AsyncMock(return_value={"reclaimed":1})
        app.scrub_treasury_vault=AsyncMock(return_value={"redundant":1})
        app.recover_deep_archive=AsyncMock(return_value={"archived":1})
        app.build_deep_indexes=AsyncMock(return_value={"indexed":1})
        app.purge_expired_deep_indexes=AsyncMock(return_value={"purged":1})
        app.recover_deep_erasure=AsyncMock(return_value={"cleaned":1})
        # Observe every additional maintenance lane without external I/O.
        from contextlib import ExitStack
        maintenance = {
            "build_deep_dense_indexes": "deep_archive_dense",
            "build_full_vector_batch": "deep_archive_full_vectors",
            "build_current_vector_batch": "current_full_vectors",
            "purge_current_vector_batches": "current_vector_purge",
            "purge_stale_full_vector_batches": "deep_archive_full_vector_purge",
            "cleanup_bulk_copies": "hoarder_copy_cleanup",
            "recover_bulk_copies": "hoarder_copy_recovery",
            "reconcile_cold_primaries": "hoarder_cold_primary",
        }
        for method in maintenance:
            setattr(app, method, AsyncMock(return_value={"fixture_completed": True}))
        with ExitStack() as stack:
            stack.enter_context(patch("core.dragon_crawler.crawler_application", app))
            for method in ("pulse_release_imports", "pulse_world_discovery", "pulse_media_archive", "pulse_game_datasets", "pulse_lead_graph",):
                stack.enter_context(patch("core.dragon_corpus_runtime." + method,
                    new_callable=AsyncMock, return_value={"fixture_completed": True}))
            stack.enter_context(patch("core.dragon_game_routing.backfill_routes",
                new_callable=AsyncMock, return_value={"fixture_completed": True}))
            result=await recover_crawler_runs()
        for method, lane in maintenance.items():
            getattr(app, method).assert_awaited_once()
            self.assertEqual(result[lane], {"fixture_completed": True})
        self.assertTrue(result["treasury_watches"]["failed"])
        self.assertEqual(result["treasury_expired_segments"],{"purged":1})
        self.assertEqual(result["treasury_segment_repair"],{"repaired":1})
        self.assertEqual(result["treasury_retirements"],{"vaulted":1})
        self.assertEqual(result["treasury_quota_repair"],{"reclaimed":1})
        self.assertEqual(result["treasury_vault_scrub"],{"redundant":1})
        self.assertEqual(result["deep_archive_retirements"],{"archived":1})
        self.assertEqual(result["deep_archive_index"],{"indexed":1})
        self.assertEqual(result["deep_archive_expiry"],{"purged":1})
        self.assertEqual(result["deep_archive_erasure"],{"cleaned":1})

    async def test_ancillary_cancellation_propagates(self):
        import asyncio
        from core.dragon_crawler import recover_crawler_runs
        app=Mock()
        app.recover=AsyncMock(return_value={"scanned":0})
        app.recover_treasury_watches=AsyncMock(side_effect=asyncio.CancelledError())
        app.purge_expired_treasury_segments=AsyncMock()
        app.repair_treasury_segments=AsyncMock()
        with patch("core.dragon_crawler.crawler_application",app):
            with self.assertRaises(asyncio.CancelledError):
                await recover_crawler_runs()
        app.repair_treasury_segments.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
