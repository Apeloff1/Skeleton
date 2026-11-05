"""Strict local Jeeves agent admission on the existing GGUF desktop worker.

Every model, source fence and result in this suite is a contract-only fake.
These tests never load actual weights, grant tools or qualify a device.
"""
from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from unittest import mock
import threading
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_agent_mode import (
    DesktopAgentHold, run_agent,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_protocol import (
    DesktopProtocolHold, command, require_command,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopBridge, DesktopBridgeHold,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_host import (
    DesktopHost, DesktopHostLimits, DesktopHostHold,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL


class FakeFence:
    def __init__(self):
        self.calls = []
    def assert_live(self, worker):
        self.calls.append(worker)


class FakeNativeRuntime:
    created = []

    def __init__(self, worker, **kwargs):
        self.identity = ActiveModel.from_supervisor(worker)
        self.provider = SimpleNamespace(name="jeeves_native")
        self.worker = worker
        self.options = kwargs
        self.inputs = None
        self.success = True
        self.tool_calls = 0
        self.model_calls = 2
        self.steps = 2
        self.changed_owner = False
        self.created.append(self)

    def run(self, inputs):
        self.inputs = inputs
        if self.changed_owner:
            self.worker.spine.backend.model_digest = "f"*64
        return SimpleNamespace(
            run_id=inputs.run_id,
            goal_id=inputs.goal.goal_id,
            success=self.success,
            reason=SimpleNamespace(value="complete" if self.success else "held"),
            answer="Original offline source reply 🌲",
            trace_fingerprint="b"*64,
            usage=SimpleNamespace(
                model_calls=self.model_calls,
                steps=self.steps,
                tool_calls=self.tool_calls,
                prompt_tokens=42,
                completion_tokens=18,
            ),
        )


def run_fixture(prompt="Please plan a native-only task", **kwargs):
    worker = FakeWorker()
    fence = FakeFence()
    with (
        mock.patch(
            "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
            FakeFence,
        ),
        mock.patch(
            "skeleton.jeeves.agent.native_runtime.NativeJeevesRuntime",
            FakeNativeRuntime,
        ),
    ):
        report = run_agent(
            worker, fence, tenant="local", subject="owner",
            prompt=prompt, run_id="jrun_test1", **kwargs,
        )
    return worker, fence, report, FakeNativeRuntime.created[-1]


class DesktopStrictNativeAgentTests(unittest.TestCase):
    def setUp(self):
        FakeNativeRuntime.created.clear()

    def test_agent_uses_one_existing_worker_without_any_tool_grants(self):
        worker, fence, report, runtime = run_fixture(
            maximum_steps=4, maximum_model_calls=4,
            maximum_wall_seconds=120,
        )
        self.assertIs(runtime.worker, worker)
        self.assertTrue(runtime.inputs.budget.max_steps <= 4)
        self.assertEqual(runtime.inputs.budget.max_model_calls, 4)
        self.assertEqual(runtime.inputs.budget.max_wall_seconds, 120)
        self.assertEqual(runtime.inputs.grants, ())
        self.assertEqual(runtime.inputs.confirmed_actions, ())
        self.assertEqual(runtime.inputs.preferred_provider, "jeeves_native")
        self.assertEqual(runtime.inputs.run_id, "jrun_test1")
        self.assertEqual(report["status"], "verified")
        self.assertTrue(report["success"])
        self.assertFalse(report["release_certified"])
        self.assertFalse(report["filesystem_write_authorized"])
        self.assertEqual(report["usage"]["tool_calls"], 0)
        self.assertGreaterEqual(len(fence.calls), 2)
        self.assertIs(fence.calls[0], worker)

    def test_unicode_answer_sha256_is_exact(self):
        worker, fence, report, runtime = run_fixture()
        self.assertEqual(
            report["output_sha256"],
            sha256(report["answer"].encode("utf-8", "strict")).hexdigest(),
        )
        self.assertEqual(report["model_sha256"], MODEL)
        self.assertEqual(report["run_id"], "jrun_test1")
        self.assertFalse(report["device_qualified"])
        self.assertFalse(report["automatic_retry"])

    def test_no_auto_retry_of_failed_agent_runs(self):
        worker = FakeWorker()
        fence = FakeFence()
        class FailedAgent(FakeNativeRuntime):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.success = False
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
                FakeFence,
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_runtime.NativeJeevesRuntime",
                FailedAgent,
            ),
        ):
            result = run_agent(
                worker, fence, tenant="local", subject="owner",
                prompt="native private plan", run_id="jrun_fail",
            )
        self.assertEqual(result["status"], "held")
        self.assertIs(result["success"], False)
        self.assertNotIn("answer", result)
        self.assertEqual(len(FakeNativeRuntime.created), 1)

    def test_unexpected_model_tool_call_or_excessive_usage_is_terminal(self):
        for altered in ("tool_calls", "model_calls", "steps"):
            worker = FakeWorker()
            fence = FakeFence()
            class Unexpected(FakeNativeRuntime):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    setattr(
                        self, altered,
                        1 if altered == "tool_calls" else 900,
                    )
            with (
                mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
                    FakeFence,
                ),
                mock.patch(
                    "skeleton.jeeves.agent.native_runtime.NativeJeevesRuntime",
                    Unexpected,
                ),
            ):
                with self.subTest(altered=altered), self.assertRaises(
                    DesktopAgentHold,
                ):
                    run_agent(
                        worker, fence, tenant="local", subject="owner",
                        prompt="private task", run_id="jrun_denial",
                    )

    def test_wrong_owner_and_invalid_budgets_are_rejected_before_model(self):
        worker = FakeWorker()
        fence = FakeFence()
        for overrides in (
            {"tenant": "another"},
            {"subject": "another"},
            {"run_id": "untrusted run id"},
            {"maximum_steps": 0},
            {"maximum_model_calls": True},
            {"maximum_wall_seconds": 601},
            {"prompt": "\x00"},
        ):
            args = dict(
                worker=worker, source_fence=fence, tenant="local", subject="owner",
                prompt="valid task", run_id="jrun_test1",
            )
            args.update(overrides)
            with (
                self.subTest(overrides=overrides),
                mock.patch(
                    "skeleton.jeeves.agent.native_source_fence.NativeSourceFence",
                    FakeFence,
                ),
                mock.patch(
                    "skeleton.jeeves.agent.native_runtime.NativeJeevesRuntime",
                    FakeNativeRuntime,
                ),
            ):
                with self.assertRaises((DesktopAgentHold, ValueError)):
                    run_agent(**args)
        self.assertEqual(FakeNativeRuntime.created, [])

    def test_private_protocol_admits_only_finite_agent_request_shape(self):
        req = command(
            "agent", run_id="jrun_1", prompt="  code 🌲\r\n",
            maximum_steps=8, maximum_model_calls=3,
            maximum_wall_seconds=180,
        )
        self.assertEqual(require_command(req), req)
        self.assertEqual(req["prompt"], "  code 🌲\r\n")
        for bad in (
            {"maximum_steps": 0},
            {"maximum_model_calls": True},
            {"maximum_wall_seconds": 601},
            {"tools": ["execute_shell"]},
        ):
            with self.subTest(bad=bad), self.assertRaises(
                (DesktopProtocolHold, ValueError),
            ):
                command("agent", run_id="jrun_1", prompt="ok", **bad)

    def test_host_routes_to_same_worker_and_keeps_chat_session(self):
        worker = FakeWorker()
        host = DesktopHost.__new__(DesktopHost)
        host.worker = worker
        host.identity = ActiveModel.from_supervisor(worker)
        host.tenant = "local"
        host.subject = "owner"
        host.source = SimpleNamespace(assert_live=lambda _: None)
        host.chat = SimpleNamespace(session_id="s_existing")
        host._stopped = False
        host._lock = threading.RLock()
        host.limits = DesktopHostLimits()
        host._commands = 0
        report = {
            "schema": "jeeves.desktop.strict-agent.v1",
            "status": "verified", "success": True,
            "run_id": "jrun_1", "answer": "Native plan completed",
        }
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_agent_mode.run_agent",
            return_value=report,
        ) as actual:
            result, end = host.handle(command(
                "agent", run_id="jrun_1", prompt="Original private task",
            ))
        self.assertFalse(end)
        self.assertEqual(result["status"], "verified-agent-response")
        self.assertEqual(result["session_id"], "s_existing")
        self.assertEqual(result["run_id"], "jrun_1")
        actual.assert_called_once()
        self.assertIs(actual.call_args.args[0], worker)
        self.assertIs(actual.call_args.args[1], host.source)
        self.assertEqual(actual.call_args.kwargs["tenant"], "local")

    def test_client_rejects_forged_agent_success_or_tool_grants(self):
        answer = "Actual offline reply"
        good = {
            "schema": "jeeves.desktop.strict-agent.v1",
            "status": "verified",
            "success": True, "run_id": "jrun_1",
            "answer": answer,
            "output_sha256": sha256(answer.encode()).hexdigest(),
            "model_sha256": MODEL,
            "device_qualified": False,
            "release_certified": False,
            "filesystem_write_authorized": False,
            "automatic_retry": False,
            "usage": {"tool_calls": 0},
        }
        client = DesktopBridge.__new__(DesktopBridge)
        client.model_sha256 = MODEL
        fields = {"run_id": "jrun_1"}
        result = {
            "status": "verified-agent-response",
            "run_id": "jrun_1",
            "session_id": "s_existing",
            "agent": good,
        }
        client._operation_receipt("agent", fields, result, "s_existing")
        for changed in (
            {"run_id": "jrun_other"},
            {"success": False},
            {"filesystem_write_authorized": True},
            {"output_sha256": "f"*64},
            {"usage": {"tool_calls": 1}},
            {"release_certified": True},
        ):
            with self.subTest(changed=changed):
                import copy
                corrupt = copy.deepcopy(result)
                corrupt["agent"].update(changed)
                with self.assertRaises(DesktopBridgeHold):
                    client._operation_receipt(
                        "agent", fields, corrupt, "s_existing",
                    )


if __name__ == "__main__":
    unittest.main()
