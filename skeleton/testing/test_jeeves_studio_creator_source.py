"""End-to-end host-authorized native Jeeves project-source mutation contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.agent.tools import (
    ToolExecutionContext, ToolExecutor, ToolGrant, ToolRegistry,
)
from skeleton.jeeves.agent.types import RiskTier, stable_fingerprint
from skeleton.jeeves.ai.studio_creator_source import (
    CreatorProjectSourceStore, CreatorSourceError, register_creator_source_tool,
)
from skeleton.jeeves.ai.studio_interaction_contract import (
    JeevesStudioController, StudioEvidenceJournal, StudioProposal,
)
from skeleton.jeeves.ai.creator_runbook_store import CreatorRunbookStore
from skeleton.jeeves.ai.studio_delegate_executor import execute_approved_studio_batch
from skeleton.jeeves.ai.studio_host_bootstrap import NativeStudioHost
from skeleton.jeeves.ai.studio_interaction_contract import StudioInteractionError


class CreatorSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.export_root = self.root / "exports"
        self.export_root.mkdir()
        self.path = self.root / "creator.sqlite"
        self.owner = CreatorProjectSourceStore(
            self.path, project_id="original-game", export_root=self.export_root,
        )
        self.addCleanup(self.owner.close)
        self.document = {
            "title": "Sky Islands",
            "world": "An original archipelago beyond the cloud shelf",
            "alternates": ["updraft", "skyship", "rope_bridge"],
        }

    def command(self, operation: str, **payload):
        return build_creator_command(
            operation, project_id="original-game", payload=payload,
        )

    def create(self, record="world-one", deps=None, facet="world", document=None):
        return self.owner.create(self.command("create", intent={
            "record_id": record, "facet": facet,
            "document": self.document if document is None else document,
            "depends_on": deps if deps is not None else [],
        }))

    def test_real_create_persists_hash_and_survives_restart(self):
        result = self.create()
        self.assertEqual(result["revision"], 1)
        self.assertTrue(result["source_written_to_sqlite"])
        self.assertEqual(self.owner.snapshot()["source_count"], 1)
        with CreatorProjectSourceStore(
            self.path, project_id="original-game", export_root=self.export_root,
        ) as another:
            self.assertEqual(another.snapshot()["head_sha256"], result["history_sha256"])
            self.assertEqual(another._records["world-one"]["document"], self.document)

    def test_actual_edit_mutates_only_at_correct_revision(self):
        original = self.create()
        result = self.owner.edit(self.command(
            "edit", target_id="world-one", expected_revision=1,
            patch={"set": {"weather": "live turbulence"},
                   "remove": ["alternates"]},
        ))
        self.assertEqual(result["revision"], 2)
        self.assertNotEqual(result["source_sha256"], original["source_sha256"])
        self.assertEqual(self.owner._records["world-one"]["document"]["weather"],
                         "live turbulence")
        self.assertNotIn("alternates", self.owner._records["world-one"]["document"])
        with self.assertRaises(CreatorSourceError):
            self.owner.edit(self.command(
                "edit", target_id="world-one", expected_revision=1,
                patch={"set": {"weather": "fake"}, "remove": []},
            ))
        self.assertEqual(self.owner.snapshot()["event_count"], 2)

    def test_missing_dependency_refused_before_mutation(self):
        with self.assertRaises(CreatorSourceError):
            self.create(record="quest-one", deps=["missing-world"], facet="quests")
        self.assertEqual(self.owner.snapshot()["source_count"], 0)

    def test_real_cross_forge_dependent_source_graph(self):
        self.create()
        self.create(record="hero", deps=["world-one"], facet="cast",
                    document={"title": "Original protagonist", "design": "sky sailor"})
        self.create(record="quest-one", deps=["hero"], facet="quests",
                    document={"quest": "Reach the citadel", "reward": "new skyship"})
        verified = self.owner.test(self.command(
            "test", scopes=["quest-one"], profile="full",
        ))
        self.assertTrue(verified["passed"])
        self.assertEqual(verified["dependency_assurance"]["sources_checked"], 3)
        self.assertFalse(verified["engine_playthrough_performed"])

    def test_static_preview_returns_actual_stored_source_not_rendered_frames(self):
        self.create()
        preview = self.owner.preview(self.command(
            "preview", scopes=["world-one"], mode="static",
        ))
        self.assertEqual(preview["documents"][0]["document"], self.document)
        self.assertFalse(preview["rendered_frames"])
        with self.assertRaises(CreatorSourceError):
            self.owner.preview(self.command(
                "preview", scopes=["world-one"], mode="runtime",
            ))

    def test_export_publishes_pinned_original_source_bundle_once(self):
        self.create()
        command = self.command(
            "export", format="game-source-json", artifact_name="my-world",
        )
        first = self.owner.export(command)
        target = self.export_root / first["artifact_name"]
        self.assertTrue(target.is_file())
        import hashlib
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                         first["artifact_sha256"])
        exported = json.loads(target.read_text())
        self.assertEqual(exported["source_documents"][0]["document"], self.document)
        self.assertFalse(exported["native_binary_compiled"])
        second = self.owner.export(command)
        self.assertTrue(second["already_exported"])
        self.assertEqual(len(list(self.export_root.iterdir())), 1)

    def test_non_source_export_denied(self):
        self.create()
        with self.assertRaises(CreatorSourceError):
            self.owner.export(self.command(
                "export", format="executable", artifact_name="runnable",
            ))
        self.assertFalse(any(self.export_root.iterdir()))

    def test_invalid_and_duplicate_edit_fail_closed(self):
        self.create()
        with self.assertRaises(CreatorSourceError):
            self.create()
        with self.assertRaises(CreatorSourceError):
            self.owner.edit(self.command(
                "edit", target_id="world-one", expected_revision=1,
                patch={"set": {"world": "replaced"}, "remove": ["world"]},
            ))
        with self.assertRaises(CreatorSourceError):
            self.owner.edit(self.command(
                "edit", target_id="world-one", expected_revision=1,
                patch={"set": {}, "remove": []},
            ))
        self.assertEqual(self.owner.snapshot()["event_count"], 1)

    def test_native_source_search_uses_actual_record_and_revision(self):
        original = self.create()
        result = self.owner.search("Sky Islands skyship and updraft")
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["source_head_sha256"],
                         original["history_sha256"])
        self.assertEqual(result["results"][0]["record_id"], "world-one")
        self.assertEqual(result["results"][0]["revision"], 1)
        self.assertEqual(result["results"][0]["source_sha256"],
                         original["source_sha256"])
        self.assertFalse(result["native_engine_compilation_performed"])

    def test_unmatched_native_source_search_abstains(self):
        self.create()
        found = self.owner.search("incomprehensiblequarklevitation")
        self.assertEqual(found["results"], [])
        self.assertEqual(found["source_count"], 1)

    def test_actual_edit_updates_retrieved_context_revision(self):
        self.create()
        self.owner.edit(self.command(
            "edit", target_id="world-one", expected_revision=1,
            patch={"set": {"river_system": "Volcanic sky streams"},
                   "remove": []},
        ))
        hits = self.owner.search("Volcanic streams")
        self.assertEqual(hits["results"][0]["revision"], 2)
        self.assertEqual(hits["source_head_sha256"],
                         self.owner.snapshot()["head_sha256"])

    def test_sqlite_record_tampering_is_detected(self):
        self.create()
        with sqlite3.connect(self.path) as external:
            external.execute(
                "UPDATE creator_source_record SET document_json=? WHERE record_id=?",
                ('{"world":"forged"}', "world-one"),
            )
        with self.assertRaises(CreatorSourceError):
            self.owner.snapshot()

    def test_wrong_project_cannot_reopen_source_owner(self):
        self.create()
        with self.assertRaises(CreatorSourceError):
            CreatorProjectSourceStore(
                self.path, project_id="another-game", export_root=self.export_root,
            )

    def test_registered_tool_requires_separate_host_exact_authorization(self):
        self.create()
        registry = ToolRegistry()
        calls = []
        register_creator_source_tool(
            registry, store=self.owner,
            authorize=lambda cmd, context: calls.append(cmd.digest) or False,
        )
        from skeleton.jeeves.agent.types import ToolCall
        tool = ToolExecutor(registry)
        payload = {
            "operation": "test", "project_id": "original-game",
            "payload": {"scopes": ["world-one"], "profile": "smoke"},
        }
        grant = ToolGrant(
            tool_name="creator_execute_authorized",
            allowed_risks=(RiskTier.HIGH_IMPACT,),
            expires_at=time.time() + 60, max_calls=1,
            argument_fingerprint=stable_fingerprint(payload),
        )
        result = tool.execute(
            ToolCall(call_id="refuse-001", name="creator_execute_authorized",
                     arguments=payload, reason="review testing"),
            ToolExecutionContext(run_id="user-r1", user_id="human-producer",
                                 trace_id="trace-r1"),
            grants=(grant,),
        )
        self.assertFalse(result.ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.owner.snapshot()["event_count"], 1)

    def test_true_creator_runbook_executes_host_authorized_source_mutation(self):
        registry = ToolRegistry()
        register_creator_source_tool(
            registry, store=self.owner,
            authorize=lambda cmd, ctx: (
                cmd.project_id == "original-game"
                and ctx.user_id == "human-producer"
                and cmd.operation == "create"
            ),
        )
        executor = ToolExecutor(registry)
        with StudioEvidenceJournal(
            self.root / "evidence.sqlite", project_id="original-game",
            session_id="human-session",
        ) as journal:
            controller = JeevesStudioController(journal)
            intent = {"record_id": "world-one", "facet": "world",
                      "document": self.document, "depends_on": []}
            plan = controller.propose(
                [StudioProposal("world", "create", {"intent": intent})],
                model_checkpoint_sha256="a" * 64,
            )
            controller.approve(plan, reviewer_id="human-producer")
            command = plan["steps"][0]["command"]
            fingerprint = stable_fingerprint({
                "operation": command["operation"],
                "project_id": command["project_id"],
                "payload": command["payload"],
            })
            context = ToolExecutionContext(
                run_id="host-source-one", user_id="human-producer",
                trace_id="trace-source-one",
            )
            grant = ToolGrant(
                tool_name="creator_execute_authorized",
                allowed_risks=(RiskTier.HIGH_IMPACT,),
                expires_at=time.time() + 60, max_calls=1,
                argument_fingerprint=fingerprint,
            )
            with CreatorRunbookStore(
                self.root / "runbook.sqlite",
                plan_sha256=plan["plan_sha256"],
            ) as runbook:
                receipt = execute_approved_studio_batch(
                    controller, plan, executor=executor, store=runbook,
                    host_grants={"step-000": (context, grant)},
                )
                self.assertEqual(receipt["completed_effects"], 1)
                self.assertTrue(receipt["all_runbook_steps_succeeded"])
                self.assertEqual(self.owner.snapshot()["source_count"], 1)
                self.assertEqual(len([
                    item for item in journal.read()
                    if item["kind"] == "execution_succeeded"
                ]), 1)
                again = execute_approved_studio_batch(
                    controller, plan, executor=executor, store=runbook,
                    host_grants={"step-000": (context, grant)},
                )
                self.assertEqual(again["completed_effects"], 0)
                self.assertEqual(self.owner.snapshot()["event_count"], 1)


class NativePlanSourceFreshnessTests(unittest.TestCase):
    """Exercise dispatch admission without substituting a fake local checkpoint."""

    setUp = CreatorSourceTests.setUp
    create = CreatorSourceTests.create
    command = CreatorSourceTests.command

    def bound(self, *, approved: bool = True):
        journal = StudioEvidenceJournal(
            self.root / "plan-evidence.sqlite",
            project_id="original-game", session_id="human-session",
        )
        self.addCleanup(journal.close)
        controller = JeevesStudioController(journal)
        intent = {
            "record_id": "world-one", "facet": "world",
            "document": self.document, "depends_on": [],
        }
        plan = controller.propose(
            [StudioProposal("world", "create", {"intent": intent})],
            model_checkpoint_sha256="a" * 64,
        )
        if approved:
            controller.approve(plan, reviewer_id="human-producer")
        host = NativeStudioHost.__new__(NativeStudioHost)
        host.journal = journal
        host.source_store = self.owner
        host.book_memory = None
        host.canon_memory = None
        return host, journal, plan

    def pin(self, journal, plan, *, source=None):
        return journal.append("plan_context_bound", {
            "plan_sha256": plan["plan_sha256"],
            "model_checkpoint_sha256": "a" * 64,
            "book_admission_sha256": None,
            "book_source_root_sha256": None,
            "book_rights_head_sha256": None,
            "canon_head_sha256": None,
            "creator_source_head_sha256": source,
            "context_sha256": "b" * 64,
            "host_tool_authority_granted": False,
        }, _authority=journal._plan_token)

    def test_bound_native_plan_allows_first_unmodified_source(self):
        host, journal, plan = self.bound()
        self.pin(journal, plan, source=self.owner.snapshot()["head_sha256"])
        host._require_fresh_native_plan(plan, None)
        self.assertEqual(self.owner.snapshot()["source_count"], 0)

    def test_external_edit_after_native_planning_blocks_host_dispatch(self):
        host, journal, plan = self.bound()
        self.pin(journal, plan)
        self.create(record="unrelated-world")
        with self.assertRaises(StudioInteractionError):
            host._require_fresh_native_plan(plan, None)

    def test_own_completed_creator_step_can_resume_without_duplicate_mutation(self):
        host, journal, plan = self.bound()
        self.pin(journal, plan)
        self.owner.create(build_creator_command(
            "create", project_id="original-game",
            payload=plan["steps"][0]["command"]["payload"],
        ))
        committed = {"steps": [{"step_id": "step-000", "status": "succeeded"}]}
        host._require_fresh_native_plan(plan, committed)
        self.assertEqual(self.owner.snapshot()["source_count"], 1)

    def test_external_action_after_valid_own_step_blocks_resume(self):
        host, journal, plan = self.bound()
        self.pin(journal, plan)
        self.owner.create(build_creator_command(
            "create", project_id="original-game",
            payload=plan["steps"][0]["command"]["payload"],
        ))
        self.create(record="other-producer-sky-island")
        committed = {"steps": [{"step_id": "step-000", "status": "succeeded"}]}
        with self.assertRaises(StudioInteractionError):
            host._require_fresh_native_plan(plan, committed)

    def test_unbound_proposal_cannot_be_executed_by_standalone_host(self):
        host, _journal, plan = self.bound()
        with self.assertRaises(StudioInteractionError):
            host._require_fresh_native_plan(plan, None)

    def test_model_cannot_forge_native_plan_binding(self):
        host, journal, plan = self.bound()
        with self.assertRaises(StudioInteractionError):
            journal.append("plan_context_bound", {
                "plan_sha256": plan["plan_sha256"],
                "creator_source_head_sha256": None,
            })
        with self.assertRaises(StudioInteractionError):
            host._require_fresh_native_plan(plan, None)


if __name__ == "__main__":
    unittest.main()
