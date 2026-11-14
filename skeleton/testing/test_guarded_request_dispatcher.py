"""Dispatcher injection uses the actual native service interface, never fake model text.

This file's local service stub tests dispatch mechanics only. Real inference
must be separately tested with an operator-approved checkpoint.
"""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from skeleton.ai.runtime.operational_ai.guarded_request.workflow import (
    GuardedDispatcher, NativeRequest,
)
from skeleton.ai.runtime.operational_ai.guarded_request.identities import Scope
from skeleton.ai.runtime.operational_ai.guarded_request.pressure import Pressure
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

MODEL = "a" * 64


class ServiceInterfaceFixture:
    def __init__(self):
        self.actor = SimpleNamespace(tenant="tenant", user="user", model_digest=MODEL)
        self.calls = []

    def turn(self, *, session, request_id, question):
        self.calls.append((session, request_id, question))
        return SimpleNamespace(request_id=request_id, audit_status="fixture-only")


class TestDispatcher(unittest.TestCase):
    def setUp(self):
        self.service = ServiceInterfaceFixture()
        self.dispatcher = GuardedDispatcher(self.service)
        self.scope = Scope("tenant", "user", "conversation", MODEL)
        self.pressure = Pressure(0.2, 0.1, 0.1, 1000)

    def request(self, request_id, text="hello"):
        return NativeRequest(self.scope, request_id, text)

    def test_one_real_service_interface_call(self):
        self.assertEqual(
            self.dispatcher.submit(self.request("request_1"), pressure=self.pressure,
                                   now_mono_ms=1000), "healthy",
        )
        result = self.dispatcher.drain_one()
        self.assertEqual(result.request_id, "request_1")
        self.assertEqual(self.service.calls, [("conversation", "request_1", "hello")])
        self.assertEqual(self.dispatcher.queue.snapshot()["total"], 0)

    def test_no_compute_when_pressure_blocked(self):
        with self.assertRaises(GateDenied):
            self.dispatcher.submit(
                self.request("request_1"), pressure=Pressure(0.95, 0.1, 0.1, 1000),
                now_mono_ms=1000,
            )
        self.assertEqual(self.service.calls, [])

    def test_cancel_without_compute(self):
        self.dispatcher.submit(self.request("request_1"), pressure=self.pressure,
                               now_mono_ms=1000)
        self.assertTrue(self.dispatcher.cancel("request_1"))
        self.assertIsNone(self.dispatcher.drain_one())
        self.assertEqual(self.service.calls, [])

    def test_wrong_scope_fails_closed(self):
        wrong = NativeRequest(Scope("other", "user", "conversation", MODEL),
                              "request_1", "hello")
        with self.assertRaises(GateDenied):
            self.dispatcher.submit(wrong, pressure=self.pressure, now_mono_ms=1000)
        self.assertEqual(self.service.calls, [])

    def test_duplicate_request_cannot_queue_twice(self):
        self.dispatcher.submit(self.request("request_1"), pressure=self.pressure,
                               now_mono_ms=1000)
        with self.assertRaises(GateDenied):
            self.dispatcher.submit(self.request("request_1"), pressure=self.pressure,
                                   now_mono_ms=1000)


if __name__ == "__main__":
    unittest.main()
