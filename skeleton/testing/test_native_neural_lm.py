from __future__ import annotations

import subprocess
import sys
import threading
import textwrap
import unittest

from skeleton.ai.runtime.inference.local import LocalInferenceEngine, LocalInferenceRequest
from skeleton.ai.runtime.inference.neural import (
    NeuralLMConfig,
    NeuralLMError,
    NumpyRecurrentLM,
)


class NativeNeuralLMTests(unittest.TestCase):
    def test_base_inference_package_does_not_require_numpy(self) -> None:
        probe = textwrap.dedent(
            """
            import builtins
            import sys

            real_import = builtins.__import__

            def guarded_import(name, *args, **kwargs):
                if name == "numpy" or name.startswith("numpy."):
                    raise ModuleNotFoundError("numpy intentionally unavailable")
                return real_import(name, *args, **kwargs)

            builtins.__import__ = guarded_import
            import skeleton.ai.runtime.inference as inference
            assert "skeleton.ai.runtime.inference.neural" not in sys.modules
            assert hasattr(inference, "LocalInferenceEngine")
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=".",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def corpus(self):
        return (
            "local intelligence learns locally.",
            "local intelligence keeps model identity.",
        )

    def test_training_changes_weights_and_reduces_corpus_loss(self) -> None:
        model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=12, seed=7))
        before = model.model_digest
        receipt = model.train(
            self.corpus(),
            epochs=12,
            learning_rate=0.03,
            gradient_clip=1.0,
        )
        self.assertNotEqual(before, model.model_digest)
        self.assertEqual(receipt.final_model_digest, model.model_digest)
        self.assertLess(receipt.final_loss, receipt.initial_loss)

    def test_training_is_replay_deterministic_for_same_seed_and_corpus(self) -> None:
        config = NeuralLMConfig(hidden_size=8, seed=11)
        first = NumpyRecurrentLM(model_id="replay", config=config)
        second = NumpyRecurrentLM(model_id="replay", config=config)
        receipt_a = first.train(self.corpus(), epochs=4, learning_rate=0.02)
        receipt_b = second.train(self.corpus(), epochs=4, learning_rate=0.02)
        self.assertEqual(first.model_digest, second.model_digest)
        self.assertEqual(receipt_a.digest, receipt_b.digest)

    def test_serialized_model_round_trips_with_exact_identity(self) -> None:
        model = NumpyRecurrentLM(
            model_id="roundtrip",
            config=NeuralLMConfig(hidden_size=8, seed=3),
        )
        model.train(self.corpus(), epochs=2, learning_rate=0.02)
        payload = model.to_dict()
        restored = NumpyRecurrentLM.from_dict(payload)
        self.assertEqual(restored.model_digest, model.model_digest)
        self.assertEqual(restored.to_dict(), payload)

    def test_tampered_serialized_identity_is_rejected(self) -> None:
        model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=5))
        payload = model.to_dict()
        payload["model_digest"] = "0" * 64
        with self.assertRaisesRegex(NeuralLMError, "digest mismatch"):
            NumpyRecurrentLM.from_dict(payload)


    def test_serialized_representation_identity_tampering_is_rejected(self) -> None:
        model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=5))
        payload = model.to_dict()
        payload["config"]["representation"] = "different-representation"
        with self.assertRaisesRegex(NeuralLMError, "representation/config identity mismatch"):
            NumpyRecurrentLM.from_dict(payload)

    def test_serialized_parameter_set_must_be_exact(self) -> None:
        model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=5))
        payload = model.to_dict()
        payload["parameters"]["unexpected"] = [0.0]
        with self.assertRaisesRegex(NeuralLMError, "parameter set mismatch"):
            NumpyRecurrentLM.from_dict(payload)

    def test_serialized_config_does_not_coerce_types(self) -> None:
        model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=5))
        payload = model.to_dict()
        payload["config"]["hidden_size"] = "8"
        with self.assertRaisesRegex(NeuralLMError, "hidden_size must be an integer"):
            NumpyRecurrentLM.from_dict(payload)

    def test_engine_accepts_native_neural_backend_contract(self) -> None:
        import asyncio

        model = NumpyRecurrentLM(
            model_id="engine-neural",
            config=NeuralLMConfig(hidden_size=8, seed=17),
        )
        model.train(("abababab", "abab"), epochs=2, learning_rate=0.03)
        engine = LocalInferenceEngine(model, cache_size=2)
        request = LocalInferenceRequest(prompt="ab", max_output_tokens=6, seed=31)
        async def exercise():
            first = await engine.generate(request)
            second = await engine.generate(request)
            return first, second

        first, second = asyncio.run(exercise())
        self.assertEqual(first.model_id, "engine-neural")
        self.assertEqual(first.model_digest, model.model_digest)
        self.assertTrue(second.cached)
        self.assertEqual(first.response_id, second.response_id)

    def test_local_inference_is_credential_free_and_seed_replayable(self) -> None:
        model = NumpyRecurrentLM(
            model_id="native-neural",
            config=NeuralLMConfig(hidden_size=8, seed=13),
        )
        model.train(("abcabcabc", "abcabc"), epochs=3, learning_rate=0.03)
        request = LocalInferenceRequest(
            prompt="abc",
            max_output_tokens=12,
            seed=23,
        )
        first = model.infer(request, threading.Event())
        second = model.infer(request, threading.Event())
        self.assertEqual(first.text, second.text)
        self.assertEqual(first.response_id, second.response_id)
        self.assertEqual(first.model_digest, model.model_digest)
        self.assertEqual(first.model_id, "native-neural")

    def test_cancelled_inference_fails_cooperatively(self) -> None:
        model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=1))
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(Exception, "cancelled"):
            model.infer(
                LocalInferenceRequest(prompt="cancel", max_output_tokens=8),
                cancel,
            )

    def test_nonfinite_or_wrong_shape_parameters_are_rejected(self) -> None:
        base = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=2))
        payload = base.to_dict()
        params = payload["parameters"]
        params["hidden_bias"] = [0.0]
        with self.assertRaisesRegex(NeuralLMError, "shape mismatch"):
            NumpyRecurrentLM.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
