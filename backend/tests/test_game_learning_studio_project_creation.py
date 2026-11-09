"""Original studio engines are selectable and create real governed projects."""
from __future__ import annotations
import unittest
from unittest.mock import AsyncMock, patch

from core.game_learning import GameLearningWorkspace, GameLearningError


class StudioProjectSetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_create_initializes_original_studio_source(self):
        from skeleton.jeeves.game_studio_environment import studio_source_target
        workspace = GameLearningWorkspace.__new__(GameLearningWorkspace)
        workspace.ensure_indexes = AsyncMock()
        workspace.projects = type("Collection",(),{
            "find_one":AsyncMock(return_value=None),
            "insert_one":AsyncMock(),
        })()
        workspace.quotas = type("Quota",(),{
            "update_one":AsyncMock(),
            "find_one_and_update":AsyncMock(return_value={"projects":1}),
        })()
        workspace._admit = AsyncMock(return_value={"storage_bytes":1000000})
        workspace.get_project = AsyncMock(side_effect=lambda scope, id: {"project_id":id})
        scope={"tenant_id":"test-tenant","owner_id":"test-owner"}
        with patch("core.game_learning._now", return_value=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc)):
            result=await workspace.create_project(scope,{
                "idempotency_key":"studio-1","name":"Test economy",
                "console_id":"studio:economy",
            })
        self.assertIn("project_id",result)
        doc=workspace.projects.insert_one.await_args.args[0]
        self.assertEqual(doc["execution_mode"],"reference")
        self.assertEqual(doc["console_id"],"studio:economy")
        source={row["path"]:row["content"] for row in doc["files"]}
        self.assertEqual(studio_source_target(source),"studio:economy")


if __name__=="__main__":
    unittest.main()
