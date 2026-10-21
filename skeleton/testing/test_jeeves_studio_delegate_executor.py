"""Real host ToolExecutor execution and no-replay semantics for Jeeves Studio."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from skeleton.forge.creator.command_surface import (
    build_creator_command, dispatch_creator_command,
)
from skeleton.jeeves.ai.creator_runbook_store import CreatorRunbookStore
from skeleton.jeeves.ai.studio_delegate_executor import (
    execute_approved_studio_batch, StudioDelegationError,
)
from skeleton.jeeves.ai.studio_interaction_contract import (
    JeevesStudioController, StudioEvidenceJournal, StudioProposal,
    StudioInteractionError,
)
from skeleton.jeeves.agent.tools import (
    ArgumentRule, ToolExecutionContext, ToolExecutor, ToolGrant,
    ToolRegistry, ToolSpec,
)
from skeleton.jeeves.agent.types import RiskTier, stable_fingerprint


class NativeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = StudioEvidenceJournal(
            self.root / "evidence.sqlite", project_id="game-one",
            session_id="session-one",
        )
        self.addCleanup(self.journal.close)
        self.controller = JeevesStudioController(self.journal)
        self.plan = self.controller.propose(
            [
                StudioProposal("world", "create", {
                    "intent": {"world": "original archipelago"},
                }),
                StudioProposal("scene_forge", "create", {
                    "intent": {"scene": "original sky island"},
                }, after=("step-000",)),
            ],
            model_checkpoint_sha256="a" * 64,
        )
        self.controller.approve(self.plan, reviewer_id="human-producer")
        self.events = []
        self.registry = ToolRegistry()
        self.registry.register(
            ToolSpec(
                name="creator_execute_authorized",
                description="Host-owned permitted creator operations",
                risk=RiskTier.HIGH_IMPACT,
                idempotent=False,
                arguments=(
                    ArgumentRule("operation", "string"),
                    ArgumentRule("project_id", "string"),
                    ArgumentRule("payload", "object"),
                ),
            ),
            self.handler,
        )
        self.executor = ToolExecutor(self.registry)

    def handler(self, args, ctx):
        command = build_creator_command(
            args["operation"], project_id=args["project_id"],
            payload=args["payload"],
        )
        self.events.append(command.digest)
        return dispatch_creator_command(
            command, handlers={
                "create": lambda _: {
                    "revision": len(self.events),
                    "project_id": command.project_id,
                },
            },
        ).to_dict()

    def grants(self):
        output = {}
        for idx, step in enumerate(self.plan["steps"]):
            command = step["command"]
            args = {field: command[field] for field in
                    ("operation", "project_id", "payload")}
            output[step["step_id"]] = (
                ToolExecutionContext(
                    run_id="producer-run-" + str(idx),
                    user_id="human-producer", trace_id="trace-" + str(idx),
                ),
                ToolGrant(
                    tool_name="creator_execute_authorized",
                    allowed_risks=(RiskTier.HIGH_IMPACT,),
                    expires_at=time.time() + 60,
                    max_calls=1,
                    argument_fingerprint=stable_fingerprint(args),
                ),
            )
        return output

    def store(self):
        return CreatorRunbookStore(
            self.root / "runbook.sqlite",
            plan_sha256=self.plan["plan_sha256"],
        )

    def test_two_real_dependent_mutations_have_host_receipts(self):
        with self.store() as store:
            result = execute_approved_studio_batch(
                self.controller, self.plan, executor=self.executor,
                store=store, host_grants=self.grants(), max_steps=2,
            )
            self.assertEqual(result["completed_effects"], 2)
            self.assertEqual(result["uncertain_effects"], 0)
            self.assertTrue(result["all_runbook_steps_succeeded"])
            self.assertEqual(len(self.events), 2)
            self.assertEqual(result["remaining_ready_steps"], [])
            self.assertEqual(len([e for e in self.journal.read()
                                  if e["kind"] == "execution_succeeded"]), 2)
            self.assertEqual(store.load()["head_digest"],
                             result["runbook_state_sha256"])

    def test_no_grants_means_no_execution_and_no_fake_receipts(self):
        with self.store() as store:
            result = execute_approved_studio_batch(
                self.controller, self.plan, executor=self.executor,
                store=store, host_grants={},
            )
            self.assertEqual(result["stop_reason"], "host_grant_required")
            self.assertFalse(result["all_runbook_steps_succeeded"])
            self.assertEqual(self.events, [])
            self.assertFalse(any(e["kind"].startswith("execution_")
                                 for e in self.journal.read()))

    def test_only_fully_granted_steps_are_executed(self):
        with self.store() as store:
            one = {"step-000": self.grants()["step-000"]}
            result = execute_approved_studio_batch(
                self.controller, self.plan, executor=self.executor,
                store=store, host_grants=one, max_steps=2,
            )
            self.assertEqual(result["completed_effects"], 1)
            self.assertEqual(result["stop_reason"], "host_grant_required")
            self.assertEqual(len(self.events), 1)

    def test_unregistered_external_handler_becomes_in_doubt(self):
        with self.store() as store:
            no_handlers = ToolExecutor(ToolRegistry())
            result = execute_approved_studio_batch(
                self.controller, self.plan, executor=no_handlers,
                store=store, host_grants=self.grants(), max_steps=2,
            )
            self.assertEqual(result["uncertain_effects"], 1)
            self.assertEqual(result["stop_reason"], "external_effect_uncertain")
            self.assertEqual(self.events, [])
            self.assertEqual(len([e for e in self.journal.read()
                                  if e["kind"] == "execution_uncertain"]), 1)
            again = execute_approved_studio_batch(
                self.controller, self.plan, executor=self.executor,
                store=store, host_grants=self.grants(), max_steps=2,
            )
            self.assertEqual(again["completed_effects"], 0)
            self.assertEqual(self.events, [])

    def test_invalid_grant_does_not_mint_permissions(self):
        grants = self.grants()
        context, grant = grants["step-000"]
        grants["step-000"] = (context, ToolGrant(
            tool_name=grant.tool_name,
            allowed_risks=(RiskTier.HIGH_IMPACT,),
            expires_at=time.time() + 60, max_calls=1,
            argument_fingerprint="0" * 64,
        ))
        with self.store() as store:
            with self.assertRaises(StudioDelegationError):
                execute_approved_studio_batch(
                    self.controller, self.plan, executor=self.executor,
                    store=store, host_grants=grants,
                )
            self.assertEqual(self.events, [])

    def test_foreign_step_grant_rejected_before_dispatch(self):
        grants = self.grants()
        grants["another-plan-step"] = grants["step-000"]
        with self.store() as store:
            with self.assertRaises(StudioDelegationError):
                execute_approved_studio_batch(
                    self.controller, self.plan, executor=self.executor,
                    store=store, host_grants=grants,
                )
            self.assertIsNone(store.load())

    def test_unapproved_plan_cannot_execute(self):
        other = self.controller.propose(
            [StudioProposal("world", "create",
                            {"intent": {"world": "unapproved"}})],
            model_checkpoint_sha256="b" * 64,
        )
        with CreatorRunbookStore(
            self.root / "other.sqlite", plan_sha256=other["plan_sha256"],
        ) as store:
            with self.assertRaises(StudioInteractionError):
                execute_approved_studio_batch(
                    self.controller, other, executor=self.executor,
                    store=store, host_grants={},
                )


if __name__ == "__main__":
    unittest.main()
