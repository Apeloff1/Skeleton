"""Nonrelease tests: SOTA facade cannot bypass canonical flight auth/SSE."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.transport.flight.http import (
    FlightHTTPServer, FlightRequestHandler,
)
from skeleton.ai.runtime.operational_ai.transport.flight.http_sota import (
    FlightHTTPServerSOTA, FlightRequestHandlerSOTA,
)
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.contracts import (
    FlightEvent, StreamError,
)
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.query import StreamQuery
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.reader import StreamSnapshot
from skeleton.ai.runtime.operational_ai.transport.flight.event_stream.service_sota import EventStreamSOTA


class FakeIdentity:
    def key(self):
        return "tenant=bounded;principal=reader"


class FakeLedger:
    identity = FakeIdentity()
    db = object()
    def _get(self, *_args):
        raise AssertionError("no fake durable snapshot may be treated as proof")


class FlightSOTAQuarantine(unittest.TestCase):
    def test_http_handler_delegates_every_security_and_framing_path(self):
        self.assertTrue(issubclass(FlightRequestHandlerSOTA, FlightRequestHandler))
        self.assertTrue(issubclass(FlightHTTPServerSOTA, FlightHTTPServer))
        self.assertIs(FlightRequestHandlerSOTA._authorize, FlightRequestHandler._authorize)
        self.assertIs(FlightRequestHandlerSOTA._headers_safe, FlightRequestHandler._headers_safe)
        self.assertIs(FlightRequestHandlerSOTA._write, FlightRequestHandler._write)
        self.assertIs(FlightRequestHandlerSOTA.do_GET, FlightRequestHandler.do_GET)
        self.assertIs(FlightRequestHandlerSOTA.do_POST, FlightRequestHandler.do_POST)

    def setUp(self):
        self.stream = EventStreamSOTA(
            FakeLedger(), "s" * 32, FakeLedger.identity.key()
        )

    def test_wrong_principal_and_invalid_bearer_denied_before_read(self):
        with self.assertRaises(StreamError):
            EventStreamSOTA(FakeLedger(), "s" * 32, "other")
        with self.assertRaises(StreamError):
            EventStreamSOTA(FakeLedger(), "s" * 32, "x" * 257)
        with self.assertRaises(StreamError):
            EventStreamSOTA(FakeLedger(), "tiny", FakeLedger.identity.key())

    def _snapshot(self):
        cursor = "v1.1." + "a" * 64 + "." + "b" * 64
        event = FlightEvent("job-one", 1, "running", "a" * 64, cursor)
        return StreamSnapshot("job-one", "running", (event,), cursor, False, 1, False)

    def test_real_event_projection_is_sse_not_hash(self):
        snapshot = self._snapshot()
        raw = self.stream._encode(snapshot)
        self.assertIsInstance(raw, bytes)
        self.assertIn(b"event: transition", raw)
        self.assertIn(b"event: checkpoint", raw)
        self.assertIn(b'"job_id":"job-one"', raw)
        self.assertIn(b'"event_sha256"', raw)
        self.assertGreater(len(raw), 32)

    def test_read_preserves_canonical_bytes_and_receipt(self):
        snapshot = self._snapshot()
        raw = self.stream._encode(snapshot)
        with patch.object(self.stream._stream, "read", return_value=(raw, snapshot.record())):
            result, receipt = self.stream.read(StreamQuery("job-one", None, 32, 0))
        self.assertEqual(result, raw)
        self.assertEqual(receipt["events"], 1)
        self.assertEqual(receipt["latest_ordinal"], 1)
        self.assertEqual(receipt["epoch"], 0)
        self.assertEqual(len(self.stream.telemetry), 1)

    def test_unattested_epoch_and_malformed_response_are_denied(self):
        query = StreamQuery("job-one", None, 32, 0)
        for epoch in (1, -1, True, "0"):
            with self.subTest(epoch=epoch), self.assertRaises(StreamError):
                self.stream.read(query, epoch=epoch)
        with patch.object(self.stream._stream, "read", return_value=(b"bogus", {})):
            with self.assertRaises(StreamError):
                self.stream.read(query)

    def test_finite_admission_refuses_parallel_reads(self):
        self.stream._slots = __import__("threading").BoundedSemaphore(1)
        self.assertTrue(self.stream._slots.acquire(blocking=False))
        try:
            with self.assertRaises(StreamError):
                self.stream.read(StreamQuery("job-one", None, 32, 0))
        finally:
            self.stream._slots.release()

    def test_reader_failure_cannot_publish_fake_events(self):
        with patch.object(self.stream._stream, "read", side_effect=StreamError("ledger-held")):
            with self.assertRaises(StreamError):
                self.stream.read(StreamQuery("job-one", None, 32, 0))
        self.assertEqual(len(self.stream.telemetry), 0)


if __name__ == "__main__":
    unittest.main()
