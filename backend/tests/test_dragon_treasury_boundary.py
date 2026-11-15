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


if __name__=="__main__":
    unittest.main()
