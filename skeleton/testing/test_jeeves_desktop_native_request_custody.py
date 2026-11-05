"""Desktop native request custody, bounded deadlines and canonical IPC receipts.

No real GGUF model is loaded. A synthetic pipe is used only to verify the
production desktop bridge's response and timeout contracts, not device rights.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
import threading
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopBridge, DesktopBridgeHold, DesktopConfig,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_protocol import (
    encoded, response,
)


MODEL = "a" * 64
OTHER_MODEL = "b" * 64
SESSION = "s_owner1"
REQUEST = "r_owner1"


class SyntheticNativePipe:
    """A fake fixed-response pipe, never a real installed source witness."""

    def __init__(self, public_result):
        self.stdin = BytesIO()
        self.stdout = BytesIO(encoded(public_result, limit=262144))
        self.terminated = False
        self.wait_calls = 0

    def poll(self):
        return 2 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.wait_calls += 1
        return 2

    def kill(self):
        self.terminated = True


class FakeTimer:
    instances = []

    def __init__(self, delay, fn):
        self.delay = delay
        self.fn = fn
        self.daemon = False
        self.started = False
        self.cancelled = False
        self.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


def fixture(reply, *, inference_ms=90000, session=SESSION):
    result = DesktopBridge.__new__(DesktopBridge)
    result.config = SimpleNamespace(inference_ms=inference_ms)
    result._process = SyntheticNativePipe(reply)
    result._started = True
    result._dead = False
    result._flight = threading.Lock()
    # Synthetic bridge constructed with __new__ must reproduce the canonical
    # single-owner batch gate created by DesktopBridge.__init__. Production
    # requests must NEVER bypass a missing gate.
    result._batch_gate = threading.RLock()
    result.model_sha256 = MODEL
    result.session_id = session
    result.resume_session = None
    return result


def accepted_turn(answer="synthetic fixture answer"):
    receipt = {
        "schema": "jeeves.native_chat_turn.v1",
        "session_id": SESSION,
        "request_id": REQUEST,
        "answer": answer,
        "output_sha256": sha256(answer.encode("utf-8")).hexdigest(),
        "model_sha256": MODEL,
        "tokenizer_sha256": OTHER_MODEL,
        "authoritative_commit": True,
        "release_certified": False,
    }
    return response(
        "committed-native-chat-turn",
        session_id=SESSION,
        request_id=REQUEST,
        model_sha256=MODEL,
        turn=receipt,
    )


class NativeDesktopRequestCustodyTests(unittest.TestCase):
    def setUp(self):
        FakeTimer.instances.clear()

    def test_exact_committed_turn_can_be_published_once(self):
        bridge = fixture(accepted_turn())
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FakeTimer,
        ):
            record = bridge.request(
                "turn", prompt="private local task", request_id=REQUEST,
                context=True,
            )
        self.assertEqual(record["request_id"], REQUEST)
        self.assertFalse(bridge._dead)
        self.assertEqual(len(FakeTimer.instances), 1)
        self.assertEqual(FakeTimer.instances[0].delay, 135.0)
        self.assertTrue(FakeTimer.instances[0].started)
        self.assertTrue(FakeTimer.instances[0].cancelled)

    def test_non_inference_history_uses_shorter_bounded_deadline(self):
        bridge = fixture(response(
            "durable-history", session_id=SESSION, model_sha256=MODEL,
            message_count=0, messages=[],
        ))
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FakeTimer,
        ):
            result = bridge.request("history")
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(FakeTimer.instances[0].delay, 30.0)
        self.assertTrue(FakeTimer.instances[0].cancelled)

    def test_mismatched_request_identity_and_answer_digest_revoked(self):
        valid = accepted_turn()
        for tampering in (
            lambda r: r.__setitem__("request_id", "r_foreign"),
            lambda r: r["turn"].__setitem__("request_id", "r_foreign"),
            lambda r: r["turn"].__setitem__("output_sha256", "f" * 64),
            lambda r: r["turn"].__setitem__("model_sha256", OTHER_MODEL),
            lambda r: r["turn"].__setitem__("authoritative_commit", False),
            lambda r: r["turn"].__setitem__("release_certified", True),
            lambda r: r.__setitem__("session_id", "s_foreign"),
        ):
            with self.subTest(variant=str(tampering)):
                import copy
                bad = copy.deepcopy(valid)
                tampering(bad)
                bridge = fixture(bad)
                with mock.patch(
                    "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
                    FakeTimer,
                ):
                    with self.assertRaises(DesktopBridgeHold):
                        bridge.request(
                            "turn", prompt="private local task",
                            request_id=REQUEST,
                        )
                self.assertTrue(bridge._dead)
                self.assertTrue(bridge._process.terminated)

    def test_spurious_operation_status_cannot_cross_ipc_boundary(self):
        bridge = fixture(response(
            "durable-history",
            session_id=SESSION, model_sha256=MODEL,
            messages=[], message_count=0,
        ))
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FakeTimer,
        ):
            with self.assertRaises(DesktopBridgeHold):
                bridge.request("status")
        self.assertTrue(bridge._dead)

    def test_close_must_report_same_previous_session_and_no_active_session(self):
        good = response(
            "durable-session-closed", session_id=None,
            closed_session_id=SESSION, model_sha256=MODEL, closed=True,
        )
        bridge = fixture(good)
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FakeTimer,
        ):
            output = bridge.request("close")
        self.assertIsNone(output["session_id"])
        self.assertIsNone(bridge.session_id)
        self.assertFalse(bridge._dead)

    def test_resume_cannot_adopt_foreign_native_session(self):
        bad = response(
            "existing-durable-session-reopened",
            session_id="s_foreign", model_sha256=MODEL,
        )
        bridge = fixture(bad)
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FakeTimer,
        ):
            with self.assertRaises(DesktopBridgeHold):
                bridge.request("resume", session_id="s_requested")
        self.assertTrue(bridge._dead)

    def test_telemetry_never_claims_actual_e2e_qualification(self):
        result = response(
            "observed-runtime-capacity",
            model_sha256=MODEL, session_id=SESSION,
            observed={"native_e2e_certified": False},
        )
        bridge = fixture(result)
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FakeTimer,
        ):
            report = bridge.request("telemetry")
        self.assertFalse(report["observed"]["native_e2e_certified"])
        bridge = fixture(response(
            "observed-runtime-capacity",
            model_sha256=MODEL, session_id=SESSION,
            observed={"native_e2e_certified": True},
        ))
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FakeTimer,
        ):
            with self.assertRaises(DesktopBridgeHold):
                bridge.request("telemetry")
        self.assertTrue(bridge._dead)

    def test_timeout_revocation_cannot_return_success_after_child_killed(self):
        bridge = fixture(response(
            "ready", session_id=SESSION, model_sha256=MODEL,
        ))
        class FiredTimer(FakeTimer):
            def start(self):
                super().start()
                self.fn()
        with mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client.threading.Timer",
            FiredTimer,
        ):
            with self.assertRaises(DesktopBridgeHold):
                bridge.request("status")
        self.assertTrue(bridge._dead)
        self.assertTrue(bridge._process.terminated)


if __name__ == "__main__":
    unittest.main()
