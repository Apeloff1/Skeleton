"""Native M-series launcher negotiation and one-time llama.cpp profile seals."""
from __future__ import annotations

from dataclasses import replace
import threading
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from skeleton.ai.runtime.inference.llama_cpp import (
    LlamaCppConfig, LlamaCppModel, LlamaCppRuntimeError,
)
from skeleton.app.offline_metal_runtime import (
    plan_metal_llama_launch, require_live_metal_headroom,
)
from skeleton.app.offline_resources import LocalResourcePressure
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.app.offline_resource_fabric import GPUResource
from skeleton.app.offline_resources import LocalResourceSnapshot


def configuration(*, gpu_layers=30, batch_size=512):
    return LlamaCppConfig(
        executable="/offline/llama-cli",
        model_path="/offline/local.gguf",
        gpu_layers=gpu_layers, batch_size=batch_size,
        context_size=4096, kv_bytes_per_token=2048,
        runtime_scratch_bytes=256_000_000,
    )


def local_hardware(*, free=6_000_000_000, pressure=0.0):
    return LocalResourceSnapshot(
        total_ram_bytes=16_000_000_000, available_ram_bytes=free,
        total_disk_bytes=1_000_000_000_000,
        free_disk_bytes=500_000_000_000, cpu_count=12,
        cpu_load_ratio=0.2, memory_pressure_ratio=pressure,
    )


def apple_device(*, working=8_000_000_000, allocated=1_000_000_000):
    return GPUResource(
        "Apple Silicon Metal", "apple", 0, 0,
        shared_with_system_ram=True,
        recommended_working_set_bytes=working,
        current_allocated_bytes=allocated,
        measurement="metal_unified_working_set",
    )


def fake_model(config):
    return SimpleNamespace(
        config=config, model_artifact=SimpleNamespace(
            size_bytes=2_000_000_000, path="/offline/local.gguf",
        ),
        serving_metadata=SimpleNamespace(
            block_count=40, kv_bytes_per_token_upper_bound=2048,
        ),
    )


class AdaptiveMetalLaunchTests(unittest.TestCase):
    def test_normal_unified_ram_reduces_layer_count_without_escalating(self):
        config = configuration()
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=True):
            selected, receipt = plan_metal_llama_launch(
                fake_model(config), hardware=local_hardware(),
                devices=(apple_device(),),
            )
        self.assertTrue(receipt.supported)
        self.assertGreater(selected.gpu_layers, 0)
        self.assertLess(selected.gpu_layers, config.gpu_layers)
        self.assertLessEqual(selected.batch_size, config.batch_size)
        self.assertLessEqual(selected.threads, 12)
        self.assertEqual(selected.model_path, config.model_path)
        self.assertEqual(selected.executable, config.executable)
        self.assertFalse(receipt.gpu_transfer_verified)

    def test_swap_pressure_and_missing_geometry_choose_cpu(self):
        original = configuration()
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=True):
            selected, receipt = plan_metal_llama_launch(
                fake_model(original),
                hardware=local_hardware(pressure=0.92),
                devices=(apple_device(),),
            )
            self.assertEqual(selected.gpu_layers, 0)
            self.assertIn("pressure", receipt.reason)
            missing = fake_model(original)
            missing.serving_metadata.block_count = None
            cpu, receipt = plan_metal_llama_launch(
                missing, hardware=local_hardware(),
                devices=(apple_device(),),
            )
            self.assertEqual(cpu.gpu_layers, 0)
            self.assertIn("geometry", receipt.reason)

    def test_missing_telemetry_no_added_virtual_gpu_ram(self):
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=True):
            config, receipt = plan_metal_llama_launch(
                fake_model(configuration()), hardware=local_hardware(),
                devices=(),
            )
        self.assertEqual(config.gpu_layers, 0)
        self.assertEqual(receipt.metal_headroom_bytes, None)
        self.assertFalse(receipt.actual_backend_allocation)

    def test_gpu_disabled_by_operator_must_remain_disabled(self):
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=True):
            cfg, _ = plan_metal_llama_launch(
                fake_model(configuration(gpu_layers=0)),
                hardware=local_hardware(), devices=(apple_device(),),
            )
        self.assertEqual(cfg.gpu_layers, 0)

    def test_other_hardware_preserves_exact_operator_profile(self):
        original = configuration()
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=False):
            profile, receipt = plan_metal_llama_launch(fake_model(original))
        self.assertIs(profile, original)
        self.assertFalse(receipt.supported)

    def test_runtime_preflight_blocks_new_gpu_inference_when_uma_shrinks(self):
        candidate = fake_model(configuration(gpu_layers=8))
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=True):
            supported = require_live_metal_headroom(
                candidate, hardware=local_hardware(),
                devices=(apple_device(),),
            )
            self.assertTrue(supported.supported)
            with self.assertRaisesRegex(LocalResourcePressure, "headroom"):
                require_live_metal_headroom(
                    candidate,
                    hardware=local_hardware(free=60_000_000, pressure=0.9),
                    devices=(apple_device(working=3_000_000_000,
                                          allocated=2_999_000_000),),
                )
        self.assertEqual(candidate.config.gpu_layers, 8)

    def test_resource_guard_must_be_registered_once_before_inference(self):
        model = object.__new__(LlamaCppModel)
        model._process_lock = threading.Lock()
        model._processes_started = 0
        model._spawning_processes = 0
        model._inference_admitted = False
        model._resource_preflight_bound = False
        model._resource_preflight = None
        calls = []
        model.install_prelaunch_resource_guard(lambda: calls.append("checked"))
        self.assertTrue(model._resource_preflight_bound)
        with self.assertRaisesRegex(LlamaCppRuntimeError, "after admission"):
            model.install_prelaunch_resource_guard(lambda: None)
        self.assertEqual(calls, [])
        model._inference_admitted = True
        with self.assertRaisesRegex(LlamaCppRuntimeError, "after admission"):
            model.install_prelaunch_resource_guard(lambda: None)

    def test_inference_preflight_refusal_precedes_model_or_prompt_access(self):
        """No subprocess, prompt renderer or artifact check runs after a deny."""
        model = object.__new__(LlamaCppModel)
        model._process_lock = threading.Lock()
        model._inference_admitted = False
        model._resource_preflight_checks = 0
        def deny():
            raise LocalResourcePressure("GPU headroom exhausted")
        model._resource_preflight = deny
        with patch.object(
            LlamaCppModel, "_assert_artifacts_stable",
            side_effect=AssertionError("preflight must run first"),
        ), patch.object(
            LlamaCppModel, "_render_prompt",
            side_effect=AssertionError("prompt must not be rendered"),
        ):
            with self.assertRaisesRegex(
                LocalResourcePressure, "headroom exhausted"
            ):
                model.infer(LocalInferenceRequest(prompt="hello"),
                            threading.Event())
        self.assertEqual(model._resource_preflight_checks, 1)
        self.assertTrue(model._inference_admitted)

    def test_native_kv_observation_is_owned_by_exact_execution_receipt(self):
        model = object.__new__(LlamaCppModel)
        model._process_lock = threading.Lock()
        first = "a" * 64
        second = "b" * 64
        model._kv_by_execution_receipt = {
            first: {"reported_host_kv_bytes": 4096,
                    "reported_device_kv_bytes": 0},
            second: {"reported_host_kv_bytes": 0,
                     "reported_device_kv_bytes": 8192},
        }
        observation = model.kv_observation_for_receipt(first)
        self.assertEqual(observation["reported_host_kv_bytes"], 4096)
        self.assertEqual(
            model.kv_observation_for_receipt(second)["reported_device_kv_bytes"],
            8192,
        )
        observation["reported_host_kv_bytes"] = -1
        self.assertEqual(
            model.kv_observation_for_receipt(first)["reported_host_kv_bytes"],
            4096,
        )
        self.assertIsNone(model.kv_observation_for_receipt("c" * 64))
        with self.assertRaises(LlamaCppRuntimeError):
            model.kv_observation_for_receipt("untrusted")

    def test_backend_reconfiguration_is_prelaunch_and_identity_bound(self):
        baseline = configuration()
        # Testing an already created backend's policy gate without requiring
        # model weights, the runtime CLI, or a Metal driver.
        model = object.__new__(LlamaCppModel)
        model.config = baseline
        model._process_lock = threading.Lock()
        model._processes_started = 0
        model._active_processes = set()
        model._draining_processes = set()
        model._spawning_processes = 0
        with patch.object(LlamaCppModel, "_assert_artifacts_stable"):
            model.activate_prelaunch_resource_profile(
                replace(baseline, gpu_layers=4, threads=4, batch_size=64),
            )
        self.assertEqual(model.config.gpu_layers, 4)
        self.assertEqual(model.config.batch_size, 64)
        self.assertTrue(model._resource_profile_bound)
        with self.assertRaisesRegex(LlamaCppRuntimeError, "already bound"):
            model.activate_prelaunch_resource_profile(model.config)
        with self.assertRaises(LlamaCppRuntimeError):
            model.activate_prelaunch_resource_profile(
                replace(model.config, gpu_layers=9),
            )
        with self.assertRaises(LlamaCppRuntimeError):
            model.activate_prelaunch_resource_profile(
                replace(model.config, context_size=8192),
            )
        model._processes_started = 1
        with self.assertRaises(LlamaCppRuntimeError):
            model.activate_prelaunch_resource_profile(model.config)


if __name__ == "__main__":
    unittest.main()
