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


class HistoricalChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_archive_context_and_permission_fence(self):
        from core.dragon_crawler import CrawlerError
        from skeleton.ai.webcrawler.dragon_archive_grant import create_grant
        from skeleton.ai.webcrawler.dragon_companion import _lexemes
        app,row,now,events=DeepArchiveTests().harness()
        row["deep_archive"].update(state="archived",released=True)
        row["archive_grant"]=create_grant(snapshot=row["snapshot"],policies={},now=now.timestamp()-1,days=7)
        source=next(iter(row["snapshot"]["sources"].values()))
        word=_lexemes(source["text"])[0]
        hit={"session_id":row["_id"],"version":row["version"],"source_id":source["source_id"],
             "snapshot_digest":row["snapshot"]["snapshot_digest"]}
        app.deep_archive_search=AsyncMock(return_value={"matches":[hit]})
        with patch("core.dragon_crawler._now",return_value=now):
            projection=await app.history_context(SCOPE,word,4,4000)
            self.assertEqual(len(projection["documents"]),1)
            self.assertTrue(projection["documents"][0]["history_only"])
            pin=projection["references"][0]
            self.assertEqual(pin["schema_version"],"skeleton.dragon.historical-chat-reference.v1")
            await app.assert_history_context(SCOPE,[pin])
            row["archive_grant"]=None
            with self.assertRaises(CrawlerError):
                await app.assert_history_context(SCOPE,[pin])
