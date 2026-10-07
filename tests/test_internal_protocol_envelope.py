from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p2_internal_protocol",
    ROOT / "skeleton" / "contracts" / "protocol.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ProtocolContractError = MODULE.ProtocolContractError
ProtocolEnvelope = MODULE.ProtocolEnvelope
ProtocolReplayGuard = MODULE.ProtocolReplayGuard
RetryClass = MODULE.RetryClass
UnknownOutcomePolicy = MODULE.UnknownOutcomePolicy


class InternalProtocolEnvelopeTests(unittest.TestCase):
    def _envelope(self, **overrides: object) -> ProtocolEnvelope:
        data: dict[str, object] = {
            "protocol": "test.control",
            "message_id": "msg-1",
            "kind": "command",
            "sender": "scheduler",
            "recipient": "worker-1",
            "operation_id": "op-1",
            "correlation_id": "corr-1",
            "causation_id": "cause-0",
            "trace_id": "trace-1",
            "span_id": "span-1",
            "deadline_utc": "2026-10-01T01:00:00Z",
            "idempotency_key": "idem-1",
            "attempt": 1,
            "retry_class": RetryClass.IDEMPOTENT,
            "unknown_outcome_policy": UnknownOutcomePolicy.IDEMPOTENT_REPLAY,
            "payload": {"value": 1},
        }
        data.update(overrides)
        return ProtocolEnvelope(**data)

    def test_digest_is_deterministic(self) -> None:
        left = self._envelope(payload={"b": 2, "a": 1})
        right = self._envelope(payload={"a": 1, "b": 2})
        self.assertEqual(left.digest, right.digest)

    def test_trace_headers_preserve_operation_and_causation(self) -> None:
        headers = self._envelope().trace_headers()
        self.assertEqual(headers["x-trace-id"], "trace-1")
        self.assertEqual(headers["x-correlation-id"], "corr-1")
        self.assertEqual(headers["x-causation-id"], "cause-0")
        self.assertEqual(headers["x-operation-id"], "op-1")

    def test_replay_same_digest_is_idempotent(self) -> None:
        guard = ProtocolReplayGuard()
        envelope = self._envelope()
        self.assertTrue(guard.accept(envelope))
        self.assertFalse(guard.accept(envelope))

    def test_replay_changed_payload_fails_closed(self) -> None:
        guard = ProtocolReplayGuard()
        self.assertTrue(guard.accept(self._envelope()))
        with self.assertRaisesRegex(ProtocolContractError, "changed canonical"):
            guard.accept(self._envelope(payload={"value": 2}))

    def test_deadline_detection_is_timezone_aware(self) -> None:
        envelope = self._envelope()
        self.assertFalse(
            envelope.deadline_exceeded(
                now=datetime(2026, 10, 1, 0, 59, tzinfo=timezone.utc)
            )
        )
        self.assertTrue(
            envelope.deadline_exceeded(
                now=datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
            )
        )

    def test_nonfinite_payload_rejected(self) -> None:
        with self.assertRaisesRegex(ProtocolContractError, "canonical JSON"):
            self._envelope(payload={"value": float("nan")})

    def test_idempotent_replay_policy_requires_retryable_class(self) -> None:
        with self.assertRaisesRegex(ProtocolContractError, "requires a retryable"):
            self._envelope(
                retry_class=RetryClass.NEVER,
                unknown_outcome_policy=UnknownOutcomePolicy.IDEMPOTENT_REPLAY,
            )


if __name__ == "__main__":
    unittest.main()
