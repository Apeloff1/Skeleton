"""The authenticated editor document must retain its public transport envelope."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core import game_frontier_authoring as authoring
from skeleton.forge.game_frontier_studio_authoring import authored_summary
from skeleton.forge.game_frontier_studio_document import create_authoring_project


class FrontierDocumentContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_summary_does_not_replace_the_public_editor_schema(self):
        project_id = "frontier-contract"
        source = create_authoring_project(project_id)
        summary = authored_summary(source)
        self.assertEqual(summary["schema"], "skeleton.forge.frontier_authoring_summary.v1")
        for saved in (False, True):
            with self.subTest(saved=saved):
                owner = {"version": 7, "files": [{"path": authoring.SOURCE_PATH}] if saved else []}
                with patch.object(authoring, "_source", AsyncMock(return_value=(owner, source))):
                    document = await authoring.document({"tenant_id": "tenant", "owner_id": "owner"}, project_id)
                self.assertEqual(document["schema"], "skeleton.game.frontier_studio_document.v1")
                self.assertEqual(document["project_id"], project_id)
                self.assertEqual(document["expected_version"], 7)
                self.assertEqual(document["studio_file"], authoring.SOURCE_PATH)
                self.assertIs(document["already_saved"], saved)
                self.assertEqual(len(document["action_catalog"]), 500)
                for key, value in summary.items():
                    if key != "schema":
                        self.assertEqual(document[key], value, key)

    async def test_summary_growth_cannot_override_project_and_revision_authority(self):
        owner = {"version": 3, "files": []}
        overlapping = {"schema": "summary", "project_id": "other-project", "expected_version": 99,
                       "studio_file": "other.json", "already_saved": True,
                       "source_sha256": "a" * 64, "custom_future_summary": {"retained": True}}
        with patch.object(authoring, "_source", AsyncMock(return_value=(owner, object()))), \
                patch.object(authoring, "authored_summary", return_value=overlapping):
            document = await authoring.document({"tenant_id": "tenant", "owner_id": "owner"}, "owned-project")
        self.assertEqual(document["schema"], "skeleton.game.frontier_studio_document.v1")
        self.assertEqual(document["project_id"], "owned-project")
        self.assertEqual(document["expected_version"], 3)
        self.assertEqual(document["studio_file"], authoring.SOURCE_PATH)
        self.assertFalse(document["already_saved"])
        self.assertEqual(document["source_sha256"], overlapping["source_sha256"])
        self.assertEqual(document["custom_future_summary"], {"retained": True})


if __name__ == "__main__":
    unittest.main()
