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
