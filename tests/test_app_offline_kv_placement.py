"""Pinned native llama.cpp KV placement: commands, identity, and no escalation."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from skeleton.ai.runtime.inference.llama_cpp import (
    GgufServingMetadata, LlamaCppConfig, LlamaCppModel,
    LlamaCppRuntimeError,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest


def config(location: str = "backend") -> LlamaCppConfig:
    return LlamaCppConfig(
        executable="/pinned/local-llama-cli",
        model_path="/pinned/model.gguf",
        model_id="owned-test-model",
        context_size=4096,
        gpu_layers=16,
        batch_size=128,
        kv_cache_location=location,
    )


def dummy_model(configuration: LlamaCppConfig) -> LlamaCppModel:
    """Use an unstarted fake; no shell, model, weights or GPU are needed."""
    model = object.__new__(LlamaCppModel)
    model.config = configuration
    model._runtime = SimpleNamespace(
        path="/pinned/local-llama-cli", sha256="a" * 64,
    )
    model._model = SimpleNamespace(
        path="/pinned/model.gguf", sha256="b" * 64,
    )
    model._serving_metadata = GgufServingMetadata(
        architecture="llama", block_count=32,
        head_count=32, head_count_kv=8,
        context_length=4096, embedding_length=4096,
    )
    model._admitted_model_id = "owned-test-model"
    model._process_lock = threading.Lock()
    model._processes_started = 0
    model._active_processes = set()
    model._draining_processes = set()
    model._spawning_processes = 0
    model._inference_admitted = False
    model._resource_profile_bound = False
    model._resource_preflight_bound = False
    model._resource_preflight = None
    model._resource_preflight_checks = 0
    return model


class PinnedKVPlacementTests(unittest.TestCase):
    def test_host_kv_emits_native_flag_and_binds_runtime_digest(self) -> None:
        backend = dummy_model(config())
        host = dummy_model(config("host"))
        request = LocalInferenceRequest(prompt="hello")
        prompt_file = Path("/private/skeleton-prompt.txt")
        baseline = backend._command(prompt_file, request)
        hosted = host._command(prompt_file, request)
        self.assertNotIn("--no-kv-offload", baseline)
        self.assertEqual(hosted.count("--no-kv-offload"), 1)
        self.assertEqual(
            [arg for arg in hosted if arg != "--no-kv-offload"], baseline,
        )
        with patch.object(LlamaCppModel, "_effective_environment", return_value={}):
            self.assertNotEqual(
                backend.execution_profile_digest, host.execution_profile_digest,
            )
        self.assertEqual(backend.config.kv_cache_location, "backend")
        self.assertEqual(host.config.kv_cache_location, "host")

    def test_direct_flag_injection_and_unknown_policy_are_denied(self) -> None:
        for argument in (
            "--no-kv-offload", "--kv-offload",
            "--no-kv-offload=true", "-nkvo", "-kvo",
        ):
            with self.subTest(argument=argument):
                with self.assertRaisesRegex(ValueError, "managed flag"):
                    replace(config(), extra_args=(argument,))
        for invalid in ("device", "swap", "unified", "", 1, None):
            with self.subTest(policy=invalid):
                with self.assertRaises(ValueError):
                    replace(config(), kv_cache_location=invalid)

    def test_profile_can_move_kv_only_from_backend_to_host(self) -> None:
        model = dummy_model(config())
        with patch.object(LlamaCppModel, "_assert_artifacts_stable"):
            model.activate_prelaunch_resource_profile(
                replace(model.config, kv_cache_location="host", gpu_layers=8),
            )
        self.assertEqual(model.config.kv_cache_location, "host")
        self.assertEqual(model.config.gpu_layers, 8)
        with self.assertRaises(LlamaCppRuntimeError):
            model.activate_prelaunch_resource_profile(config())

        model2 = dummy_model(config("host"))
        with patch.object(LlamaCppModel, "_assert_artifacts_stable"):
            with self.assertRaisesRegex(LlamaCppRuntimeError, "activate GPU KV"):
                model2.activate_prelaunch_resource_profile(
                    replace(model2.config, kv_cache_location="backend"),
                )
        self.assertEqual(model2.config.kv_cache_location, "host")

    def test_cpu_only_backend_still_emits_host_kv_directive_if_selected(self) -> None:
        model = dummy_model(replace(config("host"), gpu_layers=0))
        command = model._command(
            Path("/private/prompt.txt"),
            LocalInferenceRequest(prompt="local only"),
        )
        self.assertIn("--no-kv-offload", command)
        self.assertEqual(command[command.index("-ngl") + 1], "0")


if __name__ == "__main__":
    unittest.main()
