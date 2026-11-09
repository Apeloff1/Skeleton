"""Desktop native request watchdog admission without a subprocess or model.

These are structural policy tests only: no Tk, model, network, SQLite or timers
are started. A timeout that has begun after IPC publication is not retried.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.laptop_runtime import desktop_client as client


class DesktopRequestDeadlineTests(unittest.TestCase):
    def test_current_finite_turn_deadline_is_retained(self):
        self.assertEqual(client._request_deadline_seconds("turn", {}, 90000), 135.0)
        self.assertEqual(client._request_deadline_seconds("turn", {}, 600000), 645.0)

    def test_roundtrip_default_agent_timeout_preserves_bounded_window(self):
        self.assertEqual(client._request_deadline_seconds("agent", {}, 90000), 225.0)
        self.assertEqual(
            client._request_deadline_seconds(
                "durable", {"action": "start"}, 90000,
            ),
            225.0,
        )

    def test_durable_inspection_and_history_keep_a_short_read_timeout(self):
        for op, fields in (
            ("history", {}), ("status", {}), ("close", {}),
            ("durable", {"action": "inspect", "maximum_wall_seconds": 99999}),
            ("durable", {"action": "replay", "maximum_wall_seconds": "unknown"}),
        ):
            with self.subTest(op=op, fields=fields):
                self.assertEqual(client._request_deadline_seconds(op, fields, 90000), 30.0)

    def test_large_finite_agent_timeout_is_capped_at_source_bound(self):
        for value in (615, 720, 3600):
            with self.subTest(value=value):
                self.assertEqual(
                    client._request_deadline_seconds(
                        "agent", {"maximum_wall_seconds": value}, 90000,
                    ),
                    660.0,
                )

    def test_nan_infinity_negative_untyped_and_zero_agent_clocks_are_denied(self):
        values = (
            float("nan"), float("inf"), -float("inf"),
            0, -1, 0.5, 3601, True, "180", None, {}, [],
        )
        for value in values:
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(client.DesktopBridgeHold, "wall deadline"):
                    client._request_deadline_seconds(
                        "agent", {"maximum_wall_seconds": value}, 90000,
                    )

    def test_unbounded_int_cannot_overflow_to_native_timer(self):
        with self.assertRaisesRegex(client.DesktopBridgeHold, "wall deadline"):
            client._request_deadline_seconds(
                "agent", {"maximum_wall_seconds": 10 ** 1000}, 90000,
            )

    def test_durable_start_resume_use_same_strict_admission_as_agents(self):
        for action in ("start", "resume"):
            with self.subTest(action=action):
                with self.assertRaisesRegex(client.DesktopBridgeHold, "wall deadline"):
                    client._request_deadline_seconds(
                        "durable", {"action": action, "maximum_wall_seconds": float("nan")},
                        90000,
                    )

    def test_invalid_inference_deadline_never_becomes_timer(self):
        for value in (True, 0, -1, 99, 600001, "90000", float("inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(client.DesktopBridgeHold, "inference deadline"):
                    client._request_deadline_seconds("turn", {}, value)

    def test_invalid_agent_deadline_fails_before_native_pipe_write(self):
        writes = []
        class FakeInput:
            def write(self, *_args):
                writes.append("unexpected write")
                raise AssertionError("native pipe must not be touched")

        class FakeProcess:
            stdin = FakeInput()
            stdout = object()
            def poll(self):
                return None

        bridge = object.__new__(client.DesktopBridge)
        bridge.config = SimpleNamespace(inference_ms=90000)
        bridge._started = True
        bridge._dead = False
        bridge._process = FakeProcess()
        bridge._flight = threading.Lock()
        bridge._batch_gate = threading.RLock()
        bridge.session_id = None
        bridge.model_sha256 = None
        bridge._pressure_guard = None
        bridge._pressure_reason = None

        with patch.object(client, "command", side_effect=lambda op, **fields: dict(op=op, **fields)):
            with self.assertRaisesRegex(client.DesktopBridgeHold, "wall deadline"):
                bridge.request("agent", maximum_wall_seconds="not-a-number")

        self.assertEqual(writes, [])
        self.assertTrue(bridge.connected)
        self.assertFalse(bridge._dead)
        self.assertFalse(bridge._flight.locked())


if __name__ == "__main__":
    unittest.main()
