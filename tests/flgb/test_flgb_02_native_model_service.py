import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import (
    GenerationConfig,
    NativeLLMRuntime,
    RuntimeContractError,
)
from skeleton.ai.model_runtime.flgb_model_runtime import LocalModelRequest, ModelIdentity
from skeleton.ai.model_runtime.runtime_service import (
    CancellationToken,
    NativeModelService,
    NativeServiceError,
)


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
        model = TinyTransformer(
            vocab=("alpha", "beta", "gamma", "delta"),
            dim=8,
            ctx=8,
            seed=31,
            n_heads=2,
            n_layers=2,
            d_ff=16,
        )
        return NativeLLMRuntime(model)

    def test_service_identity_binds_weights_tokenizer_and_architecture(self):
        runtime = self.runtime()
        service = NativeModelService(runtime)
        self.assertEqual(
            service.identity.weights_digest,
            runtime.model_digest,
        )
        self.assertEqual(
            service.identity.tokenizer_digest,
            runtime.tokenizer.digest,
        )
        self.assertEqual(
            service.identity.config_digest,
            runtime.architecture.digest,
        )
        self.assertEqual(len(service.identity_digest), 64)

    def test_completed_request_returns_generation_and_receipt(self):
        runtime = self.runtime()
        service = NativeModelService(runtime)
        config = GenerationConfig(
            max_new_tokens=3,
            seed=7,
            temperature=0.0,
        )
        request = service.request(
            "op-1",
            "alpha beta",
            config,
            deadline_ms=10_000,
        )
        result = service.execute(request, "alpha beta", config)
        self.assertEqual(result.receipt.terminal_reason, "completed")
        self.assertIsNotNone(result.generation)
        self.assertEqual(
            result.receipt.output_digest,
            result.generation.output_digest,
        )
        self.assertEqual(
            result.receipt.usage_digest,
            result.generation.usage.digest,
        )
        self.assertEqual(
            result.receipt.model_identity_digest,
            service.identity_digest,
        )
        self.assertEqual(result.events[-1].kind, "completed")

    def test_input_and_model_identity_tampering_fail_closed(self):
        service = NativeModelService(self.runtime())
        config = GenerationConfig(max_new_tokens=2, temperature=0.0)
        good = service.request(
            "op-2",
            "alpha",
            config,
            deadline_ms=1_000,
        )
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

    def test_deadline_returns_terminal_receipt_without_generation(self):
        runtime = self.runtime()
        service = NativeModelService(
            runtime,
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

    def test_runtime_contract_failure_becomes_sanitized_model_error(self):
        service = NativeModelService(self.runtime())
        invalid = GenerationConfig(
            max_new_tokens=1,
            top_p=0.0,
        )
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
        self.assertEqual(len(result.receipt.usage_digest), 64)

    def test_external_identity_must_match_runtime_components(self):
        runtime = self.runtime()
        bad = ModelIdentity(
            model_id="native",
            revision="bad",
            architecture="tiny-transformer",
            config_digest=runtime.architecture.digest,
            tokenizer_digest=runtime.tokenizer.digest,
            weights_digest="c" * 64,
        )
        with self.assertRaises(NativeServiceError):
            NativeModelService(runtime, identity=bad)

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


if __name__ == "__main__":
    unittest.main()
