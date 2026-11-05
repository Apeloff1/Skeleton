"""Concurrent Apple unified-memory leases are bounded and always released."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig
from skeleton.app.offline_metal_leases import (
    UnifiedMemoryLeaseBook, reserve_apple_llama_runtime,
)
from skeleton.app.offline_resource_fabric import GPUResource
from skeleton.app.offline_resources import LocalResourcePressure, LocalResourceSnapshot


def candidate() -> SimpleNamespace:
    return SimpleNamespace(
        config=LlamaCppConfig(
            executable="/local/llama-cli", model_path="/local/model.gguf",
            context_size=4096, gpu_layers=5, kv_bytes_per_token=2048,
            runtime_scratch_bytes=256_000_000,
        ),
        model_artifact=SimpleNamespace(
            path="/local/model.gguf", size_bytes=2_000_000_000,
        ),
        serving_metadata=SimpleNamespace(
            block_count=40, kv_bytes_per_token_upper_bound=2048,
        ),
    )


class AppleUnifiedLeaseTests(unittest.TestCase):
    def test_ledger_refuses_duplicate_coincident_gpu_reservations(self):
        book = UnifiedMemoryLeaseBook()
        releases = [book.reserve(20, 100) for _ in range(5)]
        self.assertEqual(book.usage(), (5, 100))
        with self.assertRaisesRegex(LocalResourcePressure, "concurrent"):
            book.reserve(1, 100)
        releases[0]()
        releases[0]()
        self.assertEqual(book.usage(), (4, 80))
        again = book.reserve(19, 100)
        self.assertEqual(book.usage(), (5, 99))
        again()
        for release in releases:
            release()
        self.assertEqual(book.usage(), (0, 0))

    def test_invalid_reservation_cannot_create_negative_or_zero_leases(self):
        book = UnifiedMemoryLeaseBook()
        for needed, cap in ((0, 10), (-1, 10), (1, 0), (True, 10),
                            (10, False), (2, 1)):
            with self.subTest(needed=needed, cap=cap):
                with self.assertRaises(LocalResourcePressure):
                    book.reserve(needed, cap)
        self.assertEqual(book.usage(), (0, 0))

    def test_metal_processes_share_one_uma_capacity(self):
        book = UnifiedMemoryLeaseBook()
        resource = LocalResourceSnapshot(
            total_ram_bytes=16_000_000_000,
            available_ram_bytes=6_000_000_000,
            total_disk_bytes=1_000_000_000_000,
            free_disk_bytes=500_000_000_000,
            cpu_count=12, cpu_load_ratio=0.2,
        )
        device = GPUResource(
            "Apple Silicon Metal", "apple", 0, 0,
            shared_with_system_ram=True,
            recommended_working_set_bytes=8_000_000_000,
            current_allocated_bytes=1_000_000_000,
            measurement="metal_unified_working_set",
        )
        with patch(
            "skeleton.app.offline_metal_runtime._apple_silicon",
            return_value=True,
        ), patch(
            "skeleton.app.offline_metal_leases.probe_local_resources",
            return_value=resource,
        ), patch(
            "skeleton.app.offline_metal_leases.probe_gpu_resources",
            return_value=(device,),
        ), patch(
            "skeleton.app.offline_metal_leases.GLOBAL_METAL_LEASE_BOOK",
            book,
        ):
            releases = [
                reserve_apple_llama_runtime(candidate()) for _ in range(4)
            ]
            self.assertEqual(book.usage()[0], 4)
            with self.assertRaisesRegex(LocalResourcePressure, "concurrent"):
                reserve_apple_llama_runtime(candidate())
            releases[0]()
            last = reserve_apple_llama_runtime(candidate())
            for release in releases:
                release()
            last()
        self.assertEqual(book.usage(), (0, 0))

    def test_no_unverified_silicon_or_gpu_profile_is_admitted(self):
        book = UnifiedMemoryLeaseBook()
        with patch(
            "skeleton.app.offline_metal_runtime._apple_silicon",
            return_value=False,
        ), patch(
            "skeleton.app.offline_metal_leases.GLOBAL_METAL_LEASE_BOOK",
            book,
        ):
            release = reserve_apple_llama_runtime(candidate())
            release()
        self.assertEqual(book.usage(), (0, 0))
        cpu = candidate()
        cpu.config = replace(cpu.config, gpu_layers=0)
        with patch(
            "skeleton.app.offline_metal_runtime._apple_silicon",
            return_value=True,
        ):
            release = reserve_apple_llama_runtime(cpu)
            release()
        self.assertEqual(book.usage(), (0, 0))


if __name__ == "__main__":
    unittest.main()
