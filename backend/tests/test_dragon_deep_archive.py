from __future__ import annotations
import unittest
from unittest.mock import AsyncMock,Mock,patch
from skeleton.ai.webcrawler import dragon_archive_scale as a
from test_dragon_vault_boundary import VaultRestoreTests
from test_dragon_sanctuary_boundary import SCOPE

class DeepArchiveTests(unittest.IsolatedAsyncioTestCase):
    def harness(self):
        app,row,original,now,command=VaultRestoreTests().harness(damaged=False)
        row["deep_archive"]=a.marker(SCOPE,row["_id"],"a"*64,"b"*64,row["snapshot"]["snapshot_digest"],now.timestamp())
        app.limits=Mock()
        events=[]
        async def quota(q,u,**kw):
            events.append("reserve" if "$addToSet" in u else "init" if "$setOnInsert" in u else "release")
            return Mock(matched_count=1)
        async def update(q,u):
            events.append("publish" if u.get("$set",{}).get("deep_archive.state")=="archived" else "receipt")
            return Mock(modified_count=1)
        app.limits.update_one=AsyncMock(side_effect=quota)
        app.limits.find_one=AsyncMock(return_value={"_id":"quota"})
        app.sessions.update_one=AsyncMock(side_effect=update)
        return app,row,now,events
    async def test_reserve_publish_release(self):
        app,row,now,events=self.harness()
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app._finish_deep_archive(SCOPE,row["_id"])
        self.assertEqual(result,"archived")
        self.assertEqual(events,["init","reserve","publish","release","receipt"])
    async def test_cas_loss_never_releases_vault(self):
        app,row,now,events=self.harness()
        app.sessions.update_one=AsyncMock(return_value=Mock(modified_count=0))
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app._finish_deep_archive(SCOPE,row["_id"])
        self.assertEqual(result,"superseded")
        self.assertEqual(events,["init","reserve"])

    async def test_deep_index_expiration_only_removes_derivative(self):
        app,row,now,events=self.harness()
        app.ensure_indexes=AsyncMock()
        cursor=app.sessions.find.return_value
        cursor.sort.return_value=cursor
        cursor.limit.return_value=cursor
        cursor.max_time_ms.return_value=cursor
        cursor.to_list=AsyncMock(return_value=[{"_id":row["_id"],**SCOPE,"version":row["version"],
            "deep_index":{"expires_at":now.timestamp()-1}}])
        with patch("core.dragon_crawler._now",return_value=now):
            result=await app.purge_expired_deep_indexes()
        self.assertEqual(result["purged"],1)
        self.assertEqual(result["source_records_erased"],0)
        query,update=app.sessions.update_one.await_args.args
        self.assertEqual(update["$unset"],{"deep_index":""})
        self.assertEqual(query["owner_id"],SCOPE["owner_id"])
        self.assertIn("$expr",query)

    async def test_wiki_historical_projection_is_pointer_only(self):
        app,row,now,events=self.harness()
        timestamp=now.timestamp()
        sid=next(iter(row["snapshot"]["sources"]))
        result={"schema":"skeleton.dragon.deep-search.v1","history_only":True,"source_text_returned":False,
            "model_context_permission":False,"wiki_approval":False,"next_cursor":None,
            "matches":[{"session_id":row["_id"],"source_id":sid,"version":7,
                "snapshot_digest":row["snapshot"]["snapshot_digest"],"preserved_text_hash":"a"*64,
                "captured_at":timestamp-10,"valid_until":timestamp+50,"matched_terms":1,"policy_version":0}]}
        app.deep_archive_search=AsyncMock(return_value=result)
        with patch("core.dragon_crawler._now",return_value=now):
            response=await app.query_hoag_wiki(SCOPE,query="orbital",mode="historic")
        self.assertEqual(response["nucleus"],"wiki")
        self.assertEqual(response["stored_prose"],0)
        self.assertFalse(response["pointers"][0]["model_context_authorized"])
        self.assertNotIn("text",response["pointers"][0])
        app.deep_archive_search.assert_awaited_once_with(SCOPE,query="orbital",cursor=None)

    async def test_live_wiki_mirror_and_canonical_version_are_identical(self):
        from skeleton.distributed.galaxy.librarians import WikiLibrarian
        from skeleton.ai.runtime.distributed.galaxy.librarians import WikiLibrarian as Mirror
        projection={"documents":[],"references":[]}
        first=WikiLibrarian.crawler_catalog(projection,mode="current",now=100)
        self.assertEqual(first,Mirror.crawler_catalog(projection,mode="current",now=100))
        self.assertEqual(first["stored_prose"],0)
