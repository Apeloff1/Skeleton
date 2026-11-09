"""Native serving regression tests for terminal failure and resource cleanup."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from skeleton.ai.model_runtime.conversation_service import SessionRecord
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeEvent
from skeleton.ai.model_runtime.runtime_service import (
    CancellationToken,
    NativeModelService,
    NativeServiceError,
)
from skeleton.ai.model_runtime.tokenization import TokenizerContractError


class _Stream:
    def __init__(self, *, cancellation=None, error=None):
        self.cancellation = cancellation
        self.error = error
        self.emitted = False
        self.closed = False
        self.result = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.error is not None:
            raise self.error
        if self.emitted:
            raise StopIteration
        self.emitted = True
        if self.cancellation is not None:
            self.cancellation.cancel()
        return RuntimeEvent(sequence=0, kind="token", token_id=1)

    def close(self):
        self.closed = True


class _Runtime:
    def __init__(self, stream=None, error=None):
        self.active_stream = stream
        self.tokenizer = SimpleNamespace(assert_unchanged=self._assert_tokenizer)
        self.tokenizer_error = error

    def _assert_tokenizer(self):
        if self.tokenizer_error is not None:
            raise self.tokenizer_error

    def assert_model_unchanged(self):
        return None

    def stream(self, prompt, config):
        return self.active_stream


def _service(runtime):
    # Construct a protocol test instance without allocating a transformer.
    # The tested method still validates request identity and token boundaries.
    service = object.__new__(NativeModelService)
    service.runtime = runtime
    service.identity = SimpleNamespace(identity_digest="a" * 64)
    service._clock_ns = lambda: 0
    service._validate_identity = lambda identity: None
    return service


class NativeServingHardeningTests(unittest.TestCase):
    def test_slots_session_record_serializes_all_fields(self):
        record = SessionRecord("session", 1.5, 2.5, 3, 4, 5, True)
        self.assertEqual(record.to_dict(), {
            "session_id": "session",
            "created_at": 1.5,
            "updated_at": 2.5,
            "revision": 3,
            "turns": 4,
            "context_tokens": 5,
            "pinned": True,
        })

    def test_tokenizer_integrity_failure_has_typed_error(self):
        runtime = _Runtime(error=TokenizerContractError("mutation"))
        service = _service(runtime)
        config = GenerationConfig(max_new_tokens=1)
        request = service.request("integrity-failure", "hello", config, deadline_ms=1000)
        with self.assertRaisesRegex(
            NativeServiceError, "tokenizer identity changed after admission"
        ):
            service.execute(request, "hello", config)

    def test_cancelled_stream_closes_and_discards_partial_tokens(self):
        token = CancellationToken()
        stream = _Stream(cancellation=token)
        service = _service(_Runtime(stream))
        config = GenerationConfig(max_new_tokens=1)
        request = service.request("cancellation", "hello", config, deadline_ms=1000)
        result = service.execute(request, "hello", config, cancellation=token)
        self.assertEqual(result.receipt.terminal_reason, "cancelled")
        self.assertIsNone(result.generation)
        self.assertEqual(result.events, ())
        self.assertTrue(stream.closed)

    def test_model_error_stream_closes_and_discards_partial_output(self):
        stream = _Stream(error=TokenizerContractError("corrupt tokenization"))
        service = _service(_Runtime(stream))
        config = GenerationConfig(max_new_tokens=1)
        request = service.request("model-error", "hello", config, deadline_ms=1000)
        result = service.execute(request, "hello", config)
        self.assertEqual(result.receipt.terminal_reason, "model_error")
        self.assertIsNone(result.generation)
        self.assertEqual(result.events, ())
        self.assertTrue(stream.closed)


if __name__ == "__main__":
    unittest.main()
