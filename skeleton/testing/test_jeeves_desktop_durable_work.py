"""Jeeves GUI durable work-order contracts against the canonical SQLite API.

Fixtures do not load models or prove physical restart. They test that the
desktop never confuses a new effect with an inspect/replay-only action and
never creates a second checkpoint owner.
"""
from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from unittest import mock
import threading
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_durable_work import (
    DesktopDurableHold, run_durable,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_protocol import (
    DesktopProtocolHold, command, require_command,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_host import (
    DesktopHost, DesktopHostLimits,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopBridge, DesktopBridgeHold,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER

PROMPT = "Implement original offline game menu 🌲"
RUN_ID = "wrun_123"


class FakeFence:
    def __init__(self):
        self.calls = []
    def assert_live(self, worker):
        self.calls.append(worker)


class FakeDurableAgent:
    calls = []
    def __init__(self, worker):
        self.worker = worker
        self.identity = ActiveModel.from_supervisor(worker)

    def _result(self, inputs, success=True):
        return SimpleNamespace(
            run_id=inputs.run_id, goal_id=inputs.goal.goal_id,
            success=success,
            reason=SimpleNamespace(value="complete" if success else "held"),
            answer="Completed original offline menu",
            trace_fingerprint="a"*64,
            usage=SimpleNamespace(
                model_calls=2, tool_calls=0, steps=2,
                prompt_tokens=50, completion_tokens=30,
            ),
        )

    def run(self, inputs):
        self.calls.append(("start", inputs))
        return self._result(inputs)

    def resume_operator_approved(self, inputs):
        self.calls.append(("resume", inputs))
        return self._result(inputs)

    def inspect(self, inputs):
        self.calls.append(("inspect", inputs))
        return {
            "schema": "jeeves.native_durable_run.v1",
            "run_id": inputs.run_id,
            "goal_id": inputs.goal.goal_id,
            "model_sha256": MODEL,
            "tokenizer_sha256": TOKENIZER,
            "device_qualified": False, "release_certified": False,
            "operator_resume_structurally_admissible": True,
            "terminal_result_saved": False,
        }

    def replay_terminal(self, inputs):
        self.calls.append(("replay", inputs))
        return {
            "schema": "jeeves.native_terminal_result.v1",
            "run_id": inputs.run_id, "goal_id": inputs.goal.goal_id,
            "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
            "success": True, "release_certified": False,
            "device_qualified": False, "replayed": True,
            "answer": "Completed original offline menu",
            "reason": "complete", "trace_fingerprint": "a"*64,
            "usage": {"tool_calls": 0, "model_calls": 2},
        }


def execute(action, *, task=PROMPT, **kwargs):
    worker = FakeWorker()
    fence = FakeFence()
    with (
        mock.patch(
            "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
            FakeFence,
        ),
        mock.patch(
            "skeleton.jeeves.agent.native_durable_runtime.NativeDurableJeevesAgent",
            FakeDurableAgent,
        ),
    ):
        report = run_durable(
            worker, fence, action=action, tenant="local",
            subject="owner", task=task, run_id=RUN_ID, **kwargs,
        )
    return worker, fence, report, FakeDurableAgent.calls[-1]


class DurableDesktopSourceCustodyTests(unittest.TestCase):
    def setUp(self):
        FakeDurableAgent.calls.clear()

    def test_start_uses_one_existing_worker_without_grants(self):
        worker, fence, result, event = execute(
            "start", maximum_steps=4, maximum_model_calls=4,
            maximum_wall_seconds=120,
        )
        self.assertEqual(event[0], "start")
        self.assertEqual(event[1].run_id, RUN_ID)
        self.assertEqual(event[1].grants, ())
        self.assertEqual(event[1].confirmed_actions, ())
        self.assertEqual(event[1].preferred_provider, "jeeves_native")
        self.assertEqual(event[1].budget.max_steps, 4)
        self.assertEqual(event[1].budget.max_model_calls, 4)
        self.assertEqual(result["status"], "terminal-committed")
        self.assertTrue(result["native_generation_executed"])
        self.assertFalse(result["release_certified"])
        self.assertFalse(result["automatic_resume"])
        self.assertEqual(result["model_sha256"], MODEL)
        self.assertGreaterEqual(len(fence.calls), 2)

    def test_explicit_resume_only_uses_canonical_recovery_entry(self):
        worker, fence, result, event = execute("resume")
        self.assertEqual(event[0], "resume")
        self.assertEqual(result["action"], "resume")
        self.assertEqual(result["status"], "terminal-committed")

    def test_read_only_inspect_and_terminal_replay_never_generate(self):
        _, _, looked, event = execute("inspect")
        self.assertEqual(event[0], "inspect")
        self.assertEqual(looked["status"], "inspected")
        self.assertFalse(looked["native_generation_executed"])
        self.assertEqual(looked["snapshot"]["run_id"], RUN_ID)
        _, _, replayed, event = execute("replay")
        self.assertEqual(event[0], "replay")
        self.assertEqual(replayed["status"], "terminal-replayed")
        self.assertFalse(replayed["native_generation_executed"])
        self.assertTrue(replayed["replayed_without_native_generation"])
        self.assertEqual(
            replayed["output_sha256"],
            sha256(replayed["answer"].encode("utf-8")).hexdigest(),
        )

    def test_changed_task_and_unsigned_control_values_are_not_admitted(self):
        worker = FakeWorker()
        fence = FakeFence()
        for options in (
            {"task": "\x00"},
            {"action": "automatic-resume"},
            {"run_id": "bad run id"},
            {"maximum_steps": 0},
            {"maximum_model_calls": True},
            {"maximum_wall_seconds": 1000},
            {"tenant": "foreign"},
        ):
            with (
                self.subTest(options=options),
                mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
                    FakeFence,
                ),
                mock.patch(
                    "skeleton.jeeves.agent.native_durable_runtime.NativeDurableJeevesAgent",
                    FakeDurableAgent,
                ),
            ):
                args = dict(
                    worker=worker, source_fence=fence, action="start",
                    tenant="local", subject="owner",
                    task=PROMPT, run_id=RUN_ID,
                )
                args.update(options)
                with self.assertRaises(ValueError):
                    run_durable(**args)
        self.assertEqual(FakeDurableAgent.calls, [])

    def test_protocol_refuses_implicit_recovery_or_tool_options(self):
        approved = command(
            "durable", action="replay", run_id=RUN_ID, prompt=PROMPT,
            maximum_steps=8, maximum_model_calls=8,
            maximum_wall_seconds=180,
        )
        self.assertEqual(require_command(approved), approved)
        for modified in (
            {"action": "auto-recover"},
            {"action": None},
            {"tool": "execute"},
            {"maximum_model_calls": False},
        ):
            with self.subTest(modified=modified), self.assertRaises(
                (DesktopProtocolHold, ValueError),
            ):
                command(
                    "durable", run_id=RUN_ID, prompt=PROMPT,
                    **{"action": "start", **modified},
                )

    def test_host_routes_durable_actions_under_same_native_source(self):
        worker = FakeWorker()
        host = DesktopHost.__new__(DesktopHost)
        host.worker = worker
        host.identity = ActiveModel.from_supervisor(worker)
        host.tenant = "local"
        host.subject = "owner"
        host.source = SimpleNamespace(assert_live=lambda _: None)
        host.chat = SimpleNamespace(session_id="s_chat")
        host._stopped = False
        host._lock = threading.RLock()
        host.limits = DesktopHostLimits()
        host._commands = 0
        recorded = {
            "schema": "jeeves.desktop.durable-work.v1",
            "status": "inspected", "action": "inspect",
            "run_id": RUN_ID, "model_sha256": MODEL,
        }
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_durable_work.run_durable",
            return_value=recorded,
        ) as actual:
            frame, exit_now = host.handle(command(
                "durable", action="inspect", run_id=RUN_ID, prompt=PROMPT,
            ))
        self.assertFalse(exit_now)
        self.assertEqual(frame["status"], "durable-work-inspected")
        self.assertEqual(frame["session_id"], "s_chat")
        self.assertEqual(frame["run_id"], RUN_ID)
        self.assertIs(actual.call_args.args[0], worker)
        self.assertIs(actual.call_args.args[1], host.source)

    def test_client_refuses_wrong_run_or_false_native_replay(self):
        answer = "Original offline answer"
        raw = {
            "schema": "jeeves.desktop.durable-work.v1",
            "status": "terminal-replayed",
            "action": "replay",
            "run_id": RUN_ID,
            "model_sha256": MODEL,
            "success": True, "answer": answer,
            "output_sha256": sha256(answer.encode()).hexdigest(),
            "usage": {"tool_calls": 0},
            "native_generation_executed": False,
            "replayed_without_native_generation": True,
            "device_qualified": False,
            "release_certified": False,
            "automatic_resume": False,
        }
        client = DesktopBridge.__new__(DesktopBridge)
        client.model_sha256 = MODEL
        result = {
            "status": "durable-work-replayed",
            "session_id": "s_chat", "run_id": RUN_ID, "durable": raw,
        }
        client._operation_receipt(
            "durable", {"action": "replay", "run_id": RUN_ID}, result, "s_chat",
        )
        for changed in (
            {"run_id": "wrun_foreign"},
            {"replayed_without_native_generation": False},
            {"native_generation_executed": True},
            {"release_certified": True},
            {"output_sha256": "f"*64},
            {"usage": {"tool_calls": 1}},
        ):
            import copy
            with self.subTest(changed=changed):
                invalid = copy.deepcopy(result)
                invalid["durable"].update(changed)
                with self.assertRaises(DesktopBridgeHold):
                    client._operation_receipt(
                        "durable", {"action": "replay", "run_id": RUN_ID},
                        invalid, "s_chat",
                    )


if __name__ == "__main__":
    unittest.main()
