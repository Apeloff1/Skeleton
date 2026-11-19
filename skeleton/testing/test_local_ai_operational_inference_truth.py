"""Regression tests for the legacy local-AI inference truth boundary."""
import unittest

from skeleton.local_ai.operational_engine import (
    LocalInferenceNotActivated,
    OperationalEngine,
    get_engine,
)


class OperationalInferenceTruthTests(unittest.TestCase):
    def test_never_claims_native_inference(self):
        engine = get_engine()
        self.assertFalse(engine.status()["inference_ready"])
        self.assertFalse(engine.status()["operational"])
        self.assertEqual(engine.status()["readiness_code"], "LOCAL_GGUF_NOT_ACTIVATED")

    def test_legacy_generation_never_returns_synthetic_text(self):
        with self.assertRaises(LocalInferenceNotActivated):
            OperationalEngine().generate("Create a scene", "a" * 32, 16)

    def test_bad_cas_rejected_before_dispatch(self):
        with self.assertRaises(PermissionError):
            OperationalEngine().generate("hello", "short")

    def test_invalid_prompts_and_token_bounds_rejected(self):
        for prompt in ("", "  ", None, 12):
            with self.subTest(prompt=prompt), self.assertRaises(ValueError):
                OperationalEngine().generate(prompt, "a" * 32)
        for limit in (0, -1, 8193, True, 1.5, None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                OperationalEngine().generate("hello", "a" * 32, limit)

    def test_reinstantiation_remains_unactivated(self):
        with self.assertRaises(LocalInferenceNotActivated):
            get_engine().generate("hello", "a" * 32)
        with self.assertRaises(LocalInferenceNotActivated):
            get_engine().generate("hello", "a" * 32)


if __name__ == "__main__":
    unittest.main()
