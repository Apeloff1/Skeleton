"""A local background job stays inside its read/write bound."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_background_job import LocalJobRejected, LocalReferenceJob
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.app.offline_reference_read import ReferenceReadDenied
from skeleton.intelligence.background_agent import (
    AgentStep, BackgroundAgent, READ_TOOLS, WRITE_TOOLS,
)


class LocalReferenceJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = OfflineChatStore(Path(self.temp.name) / "jobs.sqlite3")
        self.addCleanup(self.store.close)
        self.library = OfflineKnowledgeLibrary(self.store, "e" * 64, "f" * 64)
        self.library.add_text(
            "Notes", "The depth buffer stores a depth value for each pixel.",
        )
        self.job = LocalReferenceJob(self.library)
        self.writes = []
        self.searches = []
        original_write = self.library.add_text
        original_search = self.library.search

        def counted_write(title, content):
            self.writes.append(title)
            return original_write(title, content)

        def counted_search(query, *, limit=6):
            self.searches.append(query)
            return original_search(query, limit=limit)

        self.library.search = counted_search
        self.library.add_text = counted_write

    def test_write_payload_without_permission_does_not_run(self):
        with self.assertRaises(ReferenceReadDenied):
            self.job.run("depth buffer", str(uuid4()), granted=False, allow_writes=False)
        with self.assertRaises(LocalJobRejected):
            self.job.run("depth buffer", str(uuid4()), granted=True, allow_writes="yes")
        blocked = self.job.run(
            "depth buffer", str(uuid4()), granted=True, allow_writes=False,
            title="Extra", text="The stencil buffer stores a stencil value.",
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["steps"], 0)
        self.assertEqual(blocked["calls"], [])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.searches, [])

    def test_read_job_is_one_bounded_step(self):
        done = self.job.run("depth buffer", str(uuid4()), granted=True, allow_writes=False)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["calls"], ["local.reference.read"])
        self.assertEqual(done["steps"], 1)
        self.assertEqual(done["max_steps"], 2)
        self.assertEqual(done["max_children"], 0)
        self.assertEqual(done["read"]["hits"][0]["title"], "Notes")
        self.assertIsNone(done["write"])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.searches, ["depth buffer"])

    def test_write_waits_for_the_bound_approval_then_replays(self):
        parent = str(uuid4())
        text = "The stencil buffer stores a stencil value."
        waiting = self.job.run(
            "depth buffer", parent, granted=True, allow_writes=True,
            title="Stencil notes", text=text,
        )
        self.assertEqual(waiting["status"], "waiting_for_approval")
        self.assertEqual(waiting["write"]["error_code"], "approval_required")
        self.assertEqual(self.writes, [])
        done = self.job.run(
            "depth buffer", parent, granted=True, allow_writes=True,
            title="Stencil notes", text=text,
            approval_ref=waiting["write"]["expected_approval_ref"],
        )
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["calls"], ["local.reference.read", "local.reference.write"])
        self.assertTrue(done["write"]["created"])
        self.assertEqual(self.writes, ["Stencil notes"])
        self.assertTrue(self.library.search("stencil buffer"))
        replay = self.job.run(
            "depth buffer", parent, granted=True, allow_writes=True,
            title="Stencil notes", text=text,
            approval_ref=waiting["write"]["expected_approval_ref"],
        )
        self.assertTrue(replay["read"]["replayed"])
        self.assertTrue(replay["write"]["replayed"])
        self.assertEqual(self.writes, ["Stencil notes"])

    def test_allow_profile_keeps_existing_tools_and_blocks_unapproved_writes(self):
        self.assertIn("network.search", READ_TOOLS)
        self.assertIn("local.reference.read", READ_TOOLS)
        self.assertIn("artifact.package", WRITE_TOOLS)
        self.assertIn("local.reference.write", WRITE_TOOLS)
        called = []

        def executor(step: AgentStep) -> str:
            called.append(step.tool)
            return "ok"

        blocked = BackgroundAgent().run(
            "write", lambda goal, calls: AgentStep("local.reference.write"), executor,
        )
        self.assertEqual(blocked.status, "blocked")
        nested = AgentStep(
            "local.reference.read",
            children=(AgentStep("local.reference.read"),),
        )
        wide = BackgroundAgent(max_children=0).run(
            "read", lambda goal, calls: nested, executor,
        )
        self.assertEqual(wide.status, "blocked")
        self.assertEqual(called, [])

    def test_runtime_mirror_matches_the_canonical_agent(self):
        root = Path(__file__).resolve().parents[1]
        canonical = (root / "skeleton/intelligence/background_agent.py").read_bytes()
        mirror = (root / "skeleton/ai/runtime/intelligence/background_agent.py").read_bytes()
        self.assertEqual(canonical, mirror)


if __name__ == "__main__":
    unittest.main()
