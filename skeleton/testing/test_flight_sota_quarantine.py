"""Security and authenticated-wire regression for quarantined flight facades.

Tests are in-process source-only: they do not claim a live network service,
real device, model inference, or public exposure qualification.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from skeleton.ai.runtime.operational_ai.transport.flight.http import (
    FlightHTTPServer, FlightRequestHandler,
)
from skeleton.ai.runtime.operational_ai.transport.flight.http_sota import (
    FlightHTTPServerSOTA, FlightRequestHandlerSOTA,
)
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.contracts import (
    StreamError, StreamPolicy,
)
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.query import (
    parse_path,
)
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream import service_sota


class FakeCanonicalStream:
    raw = b"event: source\ndata: {\"ok\":true}\n\n"
    record = {
        "schema": "skeleton.ai.flight-snapshot.v1",
        "job_id": "task_01", "state": "running", "events": 1,
        "latest_ordinal": 1, "terminal": False, "backlog": 0,
    }

    def __init__(self, ledger, bearer, *, policy=None):
        self.policy = policy or StreamPolicy()
        self.reader = object()
        self.ledger = ledger
        self.bearer = bearer

    def read(self, query):
        return type(self).raw, dict(type(self).record)


def fake_ledger(principal: str = "alice"):
    return SimpleNamespace(identity=SimpleNamespace(key=lambda: principal))


class FlightSOTAQuarantineTests(unittest.TestCase):
    def test_http_adapter_preserves_canonical_request_ownership(self):
        self.assertTrue(issubclass(FlightRequestHandlerSOTA, FlightRequestHandler))
        self.assertTrue(issubclass(FlightHTTPServerSOTA, FlightHTTPServer))
        self.assertIs(FlightRequestHandlerSOTA.do_GET, FlightRequestHandler.do_GET)
        self.assertIs(FlightRequestHandlerSOTA.do_POST, FlightRequestHandler.do_POST)
        self.assertIs(FlightRequestHandlerSOTA._get_events, FlightRequestHandler._get_events)
        self.assertIs(FlightRequestHandlerSOTA._authorize, FlightRequestHandler._authorize)

    def test_unauthorized_http_get_and_post_are_not_dispatched(self):
        handler = object.__new__(FlightRequestHandlerSOTA)
        handler.path = "/v2/jobs/task_01/events"
        for verb in ("do_GET", "do_POST"):
            with self.subTest(verb=verb), patch.object(
                FlightRequestHandlerSOTA, "_authorize", return_value=False
            ) as authorize, patch.object(
                FlightRequestHandlerSOTA, "_get_events",
            ) as events:
                getattr(handler, verb)()
                authorize.assert_called_once_with()
                events.assert_not_called()

    def test_event_principal_identity_is_authoritative(self):
        with patch.object(service_sota, "EventStream", FakeCanonicalStream):
            for principal in ("bob", "", True, None):
                with self.subTest(principal=principal):
                    with self.assertRaises(StreamError):
                        service_sota.EventStreamSOTA(
                            fake_ledger("alice"), "opaque-bearer", principal,
                        )
            good = service_sota.EventStreamSOTA(fake_ledger(), "opaque-bearer", "alice")
            self.assertIs(good.policy, good._stream.policy)
            self.assertIs(good.reader, good._stream.reader)

    def test_exact_canonical_sse_bytes_are_returned_not_digests(self):
        with patch.object(service_sota, "EventStream", FakeCanonicalStream):
            gate = service_sota.EventStreamSOTA(fake_ledger(), "opaque", "alice")
            query = parse_path("/v2/jobs/task_01/events?limit=3")
            raw, receipt = gate.read(query)
            self.assertEqual(raw, FakeCanonicalStream.raw)
            self.assertIn(b"event:", raw)
            self.assertEqual(receipt["schema"], "event-stream-receipt.v3-sota")
            self.assertEqual(receipt["job_id"], "task_01")
            self.assertEqual(receipt["events"], 1)
            self.assertFalse(receipt["terminal"])
            self.assertEqual(receipt["epoch"], 0)
            self.assertEqual(len(gate.telemetry), 1)
            self.assertNotIn("bearer", str(receipt))
            self.assertNotIn("opaque", str(receipt))

    def test_invalid_query_epoch_schema_and_unbounded_payload_fail_closed(self):
        with patch.object(service_sota, "EventStream", FakeCanonicalStream):
            gate = service_sota.EventStreamSOTA(fake_ledger(), "opaque", "alice")
            query = parse_path("/v2/jobs/task_01/events")
            for invalid in (None, {}, "task_01", 12):
                with self.subTest(query=invalid), self.assertRaises(StreamError):
                    gate.read(invalid)
            for epoch in (1, -1, True, "0"):
                with self.subTest(epoch=epoch), self.assertRaises(StreamError):
                    gate.read(query, epoch=epoch)
            good_raw, good_record = FakeCanonicalStream.raw, FakeCanonicalStream.record
            try:
                FakeCanonicalStream.record = {**good_record, "schema": "unverified"}
                with self.assertRaises(StreamError):
                    gate.read(query)
                FakeCanonicalStream.record = good_record
                FakeCanonicalStream.raw = b"x" * (gate.policy.max_payload_bytes + 1)
                with self.assertRaises(StreamError):
                    gate.read(query)
                self.assertEqual(len(gate.telemetry), 0)
            finally:
                FakeCanonicalStream.record = good_record
                FakeCanonicalStream.raw = good_raw

    def test_bounded_admission_denies_exhaustion_without_leaking_bytes(self):
        with patch.object(service_sota, "EventStream", FakeCanonicalStream):
            gate = service_sota.EventStreamSOTA(fake_ledger(), "opaque", "alice")
            query = parse_path("/v2/jobs/task_01/events")
            for _ in range(12):
                self.assertTrue(gate._slots.acquire(blocking=False))
            try:
                with self.assertRaisesRegex(StreamError, "admission exhausted"):
                    gate.read(query)
                self.assertEqual(len(gate.telemetry), 0)
            finally:
                for _ in range(12):
                    gate._slots.release()


if __name__ == "__main__":
    unittest.main()
