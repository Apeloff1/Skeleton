import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import (
    CancellationToken,
    GenerationConfig,
    NativeLLMRuntime,
    NativeModelService,
    RuntimeContractError,
)
from skeleton.ai.model_runtime.flgb_model_runtime import LocalModelRequest, ModelIdentity
from skeleton.ai.model_runtime.runtime_service import NativeServiceError


class _Clock:
    def __init__(self, values):
        self.values = iter(values)
        self.last = 0

    def __call__(self):
        try:
            self.last = next(self.values)
        except StopIteration:
            pass
        return self.last


class TestNativeModelService(unittest.TestCase):
    def runtime(self):
        return NativeLLMRuntime(
            TinyTransformer(
                vocab=("alpha", "beta", "gamma", "delta"),
                dim=8,
                ctx=8,
                seed=31,
                n_heads=2,
                n_layers=2,
                d_ff=16,
            )
        )

    def test_request_identity_rejects_non_utf8_surrogates(self):
        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=1)
        with self.assertRaisesRegex(NativeServiceError, "canonically encodable"):
            service.request("bad-unicode", "\\ud800", config, deadline_ms=1000)
        with self.assertRaisesRegex(NativeServiceError, "canonically encodable"):
            service.input_digest("\\udfff", config)

    def test_deadline_budget_includes_request_validation(self):
        from unittest.mock import patch
        service = NativeModelService(self.runtime(), clock_ns=_Clock((0, 2_000_000)))
        config = GenerationConfig(max_new_tokens=1)
        request = service.request("validation-budget", "alpha", config, deadline_ms=1)
        with patch.object(service.runtime, "stream", side_effect=AssertionError("generated")):
            result = service.execute(request, "alpha", config)
        self.assertEqual(result.receipt.terminal_reason, "deadline")
        self.assertIsNone(result.generation)

    def test_invalid_request_type_fails_before_deadline_access(self):
        service = NativeModelService(self.runtime())
        with self.assertRaisesRegex(NativeServiceError, "LocalModelRequest required"):
            service.execute(object(), "alpha", GenerationConfig(max_new_tokens=1))

    def test_terminal_receipt_never_reenters_native_tokenizer(self):
        from unittest.mock import patch
        service = NativeModelService(self.runtime())
        cfg = GenerationConfig(max_new_tokens=1)
        request = service.request("terminal-no-encode", "alpha", cfg, deadline_ms=1000)
        token = CancellationToken()
        token.cancel()
        with patch.object(service.runtime, "encode",
                          side_effect=AssertionError("terminal tokenizer reentered")):
            terminal = service.execute(request, "alpha", cfg, cancellation=token)
        self.assertEqual(terminal.receipt.terminal_reason, "cancelled")
        self.assertEqual(len(terminal.receipt.usage_digest), 64)

    def test_failure_usage_identity_binds_prompt_utf8_and_reason(self):
        from unittest.mock import patch
        service = NativeModelService(self.runtime())
        with patch.object(service.runtime, "encode",
                          side_effect=AssertionError("usage tokenizer reentered")):
            base = service._usage_digest(prompt="alpha", generated_events=0, terminal_reason="cancelled")
            again = service._usage_digest(prompt="alpha", generated_events=0, terminal_reason="cancelled")
            other_prompt = service._usage_digest(prompt="alphá", generated_events=0, terminal_reason="cancelled")
            other_reason = service._usage_digest(prompt="alpha", generated_events=0, terminal_reason="deadline")
            more_events = service._usage_digest(prompt="alpha", generated_events=1, terminal_reason="cancelled")
        self.assertEqual(base, again)
        self.assertEqual(len({base, other_prompt, other_reason, more_events}), 4)

    def test_failure_usage_rejects_malformed_unicode(self):
        service = NativeModelService(self.runtime())
        with self.assertRaisesRegex(NativeServiceError, "valid UTF-8"):
            service._usage_digest(prompt="\\ud800", generated_events=0, terminal_reason="model_error")

    def test_failure_usage_digest_survives_tokenizer_rejection(self):
        from unittest.mock import patch

        service = NativeModelService(self.runtime())
        with patch.object(
            service.runtime, "encode",
            side_effect=RuntimeContractError("encoding rejected"),
        ):
            first = service._usage_digest(
                prompt="alpha", generated_events=0, terminal_reason="model_error"
            )
            second = service._usage_digest(
                prompt="alpha", generated_events=0, terminal_reason="model_error"
            )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_failure_receipt_survives_raw_tokenizer_contract_error(self):
        from unittest.mock import patch
        from skeleton.ai.model_runtime.tokenization import TokenizerContractError

        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=1)
        request = service.request("op-tokenizer-error", "alpha", config, deadline_ms=1000)
        with patch.object(
            service.runtime, "encode",
            side_effect=TokenizerContractError("encoding rejected"),
        ):
            self.assertEqual(
                len(service._usage_digest(
                    prompt="alpha", generated_events=0, terminal_reason="model_error"
                )),
                64,
            )
            result = service.execute(request, "alpha", config)
        self.assertEqual(result.receipt.terminal_reason, "model_error")
        self.assertIsNone(result.generation)
        self.assertIsNone(result.receipt.output_digest)
        self.assertEqual(len(result.receipt.usage_digest), 64)

    def test_cancelled_request_does_not_run_generation(self):
        from unittest.mock import patch

        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=2)
        request = service.request("op-cancel-no-generate", "alpha", config, deadline_ms=1000)
        cancellation = CancellationToken()
        cancellation.cancel()
        with patch.object(service.runtime, "stream", side_effect=AssertionError("generated")):
            first = service.execute(request, "alpha", config, cancellation=cancellation)
            second = service.execute(request, "alpha", config, cancellation=cancellation)
        self.assertEqual(first.receipt.terminal_reason, "cancelled")
        self.assertIsNone(first.receipt.output_digest)
        self.assertIsNone(first.generation)
        self.assertEqual(first.receipt.usage_digest, second.receipt.usage_digest)

    def test_expired_deadline_does_not_run_generation(self):
        from unittest.mock import patch

        service = NativeModelService(self.runtime(), clock_ns=_Clock((0, 2_000_000)))
        config = GenerationConfig(max_new_tokens=2)
        request = service.request("op-deadline-no-generate", "alpha", config, deadline_ms=1)
        with patch.object(service.runtime, "stream", side_effect=AssertionError("generated")):
            result = service.execute(request, "alpha", config)
        self.assertEqual(result.receipt.terminal_reason, "deadline")
        self.assertIsNone(result.generation)
        self.assertIsNone(result.receipt.output_digest)
        self.assertEqual(result.events, ())

    def test_service_uses_runtime_canonical_identity(self):
        runtime = self.runtime()
        service = NativeModelService(runtime)
        self.assertEqual(service.identity, runtime.model_identity)
        self.assertEqual(service.identity.weights_digest, runtime.model_digest)
        self.assertEqual(service.identity.tokenizer_digest, runtime.tokenizer.digest)
        self.assertEqual(service.identity.config_digest, runtime.architecture.digest)
        self.assertEqual(service.identity.revision, runtime.model_digest)
        self.assertEqual(len(service.identity_digest), 64)

    def test_completed_request_returns_generation_and_receipt(self):
        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=3, seed=7, temperature=0.0)
        request = service.request(
            "op-1",
            "alpha beta",
            config,
            deadline_ms=10_000,
        )
        result = service.execute(request, "alpha beta", config)
        self.assertEqual(result.receipt.terminal_reason, "completed")
        self.assertIsNotNone(result.generation)
        self.assertEqual(result.receipt.output_digest, result.generation.output_digest)
        self.assertEqual(result.receipt.usage_digest, result.generation.usage.digest)
        self.assertEqual(result.receipt.model_identity_digest, service.identity_digest)
        self.assertEqual(result.events[-1].kind, "completed")

    def test_input_and_model_identity_tampering_fail_closed(self):
        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=2, temperature=0.0)
        good = service.request("op-2", "alpha", config, deadline_ms=1_000)

        bad_input = LocalModelRequest(
            operation_id=good.operation_id,
            model_identity_digest=good.model_identity_digest,
            input_digest="a" * 64,
            max_output_tokens=good.max_output_tokens,
            deadline_ms=good.deadline_ms,
        )
        with self.assertRaises(NativeServiceError):
            service.execute(bad_input, "alpha", config)

        bad_model = LocalModelRequest(
            operation_id=good.operation_id,
            model_identity_digest="b" * 64,
            input_digest=good.input_digest,
            max_output_tokens=good.max_output_tokens,
            deadline_ms=good.deadline_ms,
        )
        with self.assertRaises(NativeServiceError):
            service.execute(bad_model, "alpha", config)

    def test_request_output_cap_is_non_compensable(self):
        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=3, temperature=0.0)
        request = LocalModelRequest(
            operation_id="op-cap",
            model_identity_digest=service.identity_digest,
            input_digest=service.input_digest("alpha", config),
            max_output_tokens=2,
            deadline_ms=1_000,
        )
        with self.assertRaises(NativeServiceError):
            service.execute(request, "alpha", config)

    def test_precancel_returns_cancelled_receipt_without_output(self):
        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=2, temperature=0.0)
        request = service.request(
            "op-cancel",
            "alpha",
            config,
            deadline_ms=1_000,
        )
        cancellation = CancellationToken()
        cancellation.cancel()
        result = service.execute(
            request,
            "alpha",
            config,
            cancellation=cancellation,
        )
        self.assertEqual(result.receipt.terminal_reason, "cancelled")
        self.assertIsNone(result.receipt.output_digest)
        self.assertIsNone(result.generation)
        self.assertEqual(result.events, ())

    def test_deadline_before_execution_returns_terminal_receipt(self):
        service = NativeModelService(
            self.runtime(),
            clock_ns=_Clock((0, 2_000_000)),
        )
        config = GenerationConfig(max_new_tokens=2, temperature=0.0)
        request = service.request(
            "op-deadline",
            "alpha",
            config,
            deadline_ms=1,
        )
        result = service.execute(request, "alpha", config)
        self.assertEqual(result.receipt.terminal_reason, "deadline")
        self.assertIsNone(result.receipt.output_digest)
        self.assertIsNone(result.generation)
        self.assertEqual(result.events, ())

    def test_midstream_deadline_scrubs_generated_token_events(self):
        service = NativeModelService(
            self.runtime(),
            clock_ns=_Clock((0, 0, 0, 0, 2_000_000)),
        )
        config = GenerationConfig(max_new_tokens=4, temperature=0.0)
        request = service.request(
            "op-mid-deadline",
            "alpha",
            config,
            deadline_ms=1,
        )
        result = service.execute(request, "alpha", config)
        self.assertEqual(result.receipt.terminal_reason, "deadline")
        self.assertIsNone(result.generation)
        self.assertIsNone(result.receipt.output_digest)
        self.assertFalse(
            any(event.kind in {"token", "stopped", "completed"} for event in result.events)
        )
        self.assertEqual([event.kind for event in result.events], ["admitted", "prompt"])

    def test_runtime_contract_failure_becomes_sanitized_model_error(self):
        service = NativeModelService(self.runtime())
        invalid = GenerationConfig(max_new_tokens=1, top_p=0.0)
        request = service.request(
            "op-invalid",
            "alpha",
            invalid,
            deadline_ms=1_000,
        )
        result = service.execute(request, "alpha", invalid)
        self.assertEqual(result.receipt.terminal_reason, "model_error")
        self.assertIsNone(result.receipt.output_digest)
        self.assertIsNone(result.generation)
        self.assertFalse(any(event.kind == "token" for event in result.events))
        self.assertEqual(len(result.receipt.usage_digest), 64)

    def test_external_identity_must_equal_runtime_canonical_identity(self):
        runtime = self.runtime()
        canonical = runtime.model_identity
        alias = ModelIdentity(
            model_id="alias",
            revision=canonical.revision,
            architecture=canonical.architecture,
            config_digest=canonical.config_digest,
            tokenizer_digest=canonical.tokenizer_digest,
            weights_digest=canonical.weights_digest,
        )
        with self.assertRaises(NativeServiceError):
            NativeModelService(runtime, identity=alias)

    def test_weight_mutation_invalidates_service_identity(self):
        runtime = self.runtime()
        service = NativeModelService(runtime)
        config = GenerationConfig(max_new_tokens=1, temperature=0.0)
        request = service.request(
            "op-stale",
            "alpha",
            config,
            deadline_ms=1_000,
        )
        runtime.model.bout[0] += 0.5
        with self.assertRaises(RuntimeContractError):
            service.execute(request, "alpha", config)
        runtime.refresh_model_identity()
        with self.assertRaises(NativeServiceError):
            service.execute(request, "alpha", config)

    def test_midstream_tokenizer_rejection_emits_no_generated_output(self):
        from unittest.mock import patch
        from skeleton.ai.model_runtime.tokenization import TokenizerContractError
        from skeleton.ai.model_runtime.runtime_contracts import RuntimeEvent

        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=2)
        request = service.request("midstream-tokenizer", "alpha", config, deadline_ms=1000)

        def rejected_stream(*args, **kwargs):
            yield RuntimeEvent(sequence=0, kind="token", token_id=1)
            raise TokenizerContractError("stream tokenizer rejected")

        with patch.object(service.runtime, "stream", side_effect=rejected_stream):
            result = service.execute(request, "alpha", config)
        self.assertEqual(result.receipt.terminal_reason, "model_error")
        self.assertIsNone(result.generation)
        self.assertIsNone(result.receipt.output_digest)
        self.assertEqual(result.events, ())
        self.assertEqual(len(result.receipt.usage_digest), 64)

    def test_clock_contract_fails_closed(self):
        service = NativeModelService(self.runtime(), clock_ns=lambda: -1)
        config = GenerationConfig(max_new_tokens=1, temperature=0.0)
        request = service.request("op-clock", "alpha", config, deadline_ms=1000)
        with self.assertRaises(NativeServiceError):
            service.execute(request, "alpha", config)


if __name__ == "__main__":
    unittest.main()
