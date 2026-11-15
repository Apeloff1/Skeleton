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
        app.sessions.update_one.assert_not_awaited()

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
        self.assertEqual(mutation["$unset"],{"treasury_index":""})


if __name__=="__main__":
    unittest.main()
