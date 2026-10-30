"""Bounded native KV diagnostics and Apple UMA planning regression tests."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.inference.kv_placement import observe_native_kv_placement
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig
from skeleton.app.offline_metal_runtime import plan_metal_llama_launch
from skeleton.app.offline_resource_fabric import GPUResource
from skeleton.app.offline_resources import LocalResourceSnapshot


def configuration(*, gpu_layers: int = 30, batch_size: int = 512) -> LlamaCppConfig:
    return LlamaCppConfig(
        executable="/offline/llama-cli", model_path="/offline/model.gguf",
        gpu_layers=gpu_layers, batch_size=batch_size,
        context_size=4096, kv_bytes_per_token=2048,
        runtime_scratch_bytes=256_000_000,
    )


def local_hardware(*, free: int = 6_000_000_000) -> LocalResourceSnapshot:
    return LocalResourceSnapshot(
        total_ram_bytes=16_000_000_000, available_ram_bytes=free,
        total_disk_bytes=1_000_000_000_000,
        free_disk_bytes=500_000_000_000,
        cpu_count=12, cpu_load_ratio=0.2,
    )


def apple_device(*, working: int = 8_000_000_000,
                 allocated: int = 1_000_000_000) -> GPUResource:
    return GPUResource(
        "Apple Silicon Metal", "apple", 0, 0,
        shared_with_system_ram=True,
        recommended_working_set_bytes=working,
        current_allocated_bytes=allocated,
        measurement="metal_unified_working_set",
    )


def fake_model(config: LlamaCppConfig) -> SimpleNamespace:
    return SimpleNamespace(
        config=config,
        model_artifact=SimpleNamespace(
            size_bytes=2_000_000_000, path="/offline/model.gguf",
        ),
        serving_metadata=SimpleNamespace(
            block_count=40, kv_bytes_per_token_upper_bound=2048,
        ),
    )


class NativeKVObservationTests(unittest.TestCase):
    def test_backend_reports_host_and_metal_kv_without_fake_sync(self) -> None:
        stderr = (
            b"llama_kv_cache:      CPU KV buffer size =  32.00 MiB\n"
            b"llama_kv_cache_unified: Metal0 KV buffer size =  16.50 MiB\n"
        )
        receipt = observe_native_kv_placement(stderr)
        self.assertEqual(receipt["reported_host_kv_bytes"], 32 * 1024**2)
        self.assertEqual(receipt["reported_device_kv_bytes"],
                         16 * 1024**2 + 512 * 1024)
        self.assertEqual(receipt["matched_allocation_lines"], 2)
        self.assertTrue(receipt["backend_reported"])
        self.assertFalse(receipt["actual_gpu_coherency_proven"])
        self.assertFalse(receipt["native_sync_fence_proven"])
        self.assertEqual(len(receipt["native_stderr_sha256"]), 64)

    def test_no_diagnostics_is_unknown_not_false_allocation_proof(self) -> None:
        unknown = observe_native_kv_placement(b"ordinary model response")
        self.assertEqual(unknown["reported_device_kv_bytes"], 0)
        self.assertEqual(unknown["reported_host_kv_bytes"], 0)
        self.assertFalse(unknown["backend_reported"])
        self.assertFalse(unknown["actual_gpu_coherency_proven"])

    def test_unrecognized_native_gpu_kv_is_not_zero_gpu_evidence(self) -> None:
        receipt = observe_native_kv_placement(
            b"llama_kv_cache: CPU KV buffer size = 64.00 MiB\n"
            b"llama_kv_cache: SYCL0 KV buffer size = 22.00 MiB\n"
        )
        self.assertTrue(receipt["backend_reported"])
        self.assertGreater(receipt["reported_host_kv_bytes"], 0)
        self.assertEqual(receipt["reported_device_kv_bytes"], 0)
        self.assertEqual(receipt["unrecognized_allocation_lines"], 1)
        overflow = observe_native_kv_placement(
            b"llama_kv_cache: CPU KV buffer size = 9999999999.00 GiB\n"
        )
        self.assertEqual(overflow["matched_allocation_lines"], 0)
        self.assertEqual(overflow["unrecognized_allocation_lines"], 1)

    def test_rejects_unbounded_untrusted_or_false_positive_logs(self) -> None:
        with self.assertRaises(ValueError):
            observe_native_kv_placement(b"x" * (16 * 1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            observe_native_kv_placement("GPU KV buffer size = 999 MiB")
        receipt = observe_native_kv_placement(
            b"user: Metal0 KV buffer size = 400 GiB\n"
            b"llama_kv_cache: Metal0 KV buffer size = 900000000000.00 GiB\n"
        )
        self.assertFalse(receipt["backend_reported"])


class HostKVMetalPlanningTests(unittest.TestCase):
    def test_cpu_kv_remains_reserved_in_physical_unified_ram(self) -> None:
        ordinary = fake_model(configuration(gpu_layers=30))
        host = fake_model(replace(ordinary.config, kv_cache_location="host"))
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=True):
            gpu_profile, gpu_receipt = plan_metal_llama_launch(
                ordinary, hardware=local_hardware(),
                devices=(apple_device(),),
            )
            host_profile, host_receipt = plan_metal_llama_launch(
                host, hardware=local_hardware(),
                devices=(apple_device(),),
            )
        self.assertGreater(host_receipt.host_kv_reserve_bytes, 0)
        self.assertEqual(host_receipt.kv_cache_location, "host")
        self.assertEqual(host_profile.kv_cache_location, "host")
        self.assertEqual(gpu_profile.kv_cache_location, "backend")
        self.assertEqual(gpu_receipt.host_kv_reserve_bytes, 0)

    def test_host_kv_profile_never_creates_additional_physical_memory(self) -> None:
        candidate = fake_model(
            replace(configuration(gpu_layers=30, batch_size=128),
                    kv_cache_location="host", context_size=65536,
                    kv_bytes_per_token=100_000),
        )
        with patch("skeleton.app.offline_metal_runtime._apple_silicon",
                   return_value=True):
            selected, receipt = plan_metal_llama_launch(
                candidate,
                hardware=local_hardware(free=500_000_000),
                devices=(apple_device(working=8_000_000_000,
                                      allocated=1_000_000_000),),
            )
        self.assertEqual(selected.gpu_layers, 0)
        self.assertGreater(receipt.host_kv_reserve_bytes, 0)
        self.assertFalse(receipt.actual_backend_allocation)
        self.assertFalse(receipt.gpu_transfer_verified)


if __name__ == "__main__":
    unittest.main()
