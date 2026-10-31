"""Hardware resource fabric contracts: fail-closed GPU, immutable mmap, live control."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
from types import SimpleNamespace

from skeleton.app.offline_resources import LocalResourcePressure, LocalResourceSnapshot
from skeleton.app.offline_resource_fabric import (
    AdaptiveResourceFabric, GPUResource, ResourceFabricError,
    _probe_apple_metal, probe_gpu_resources,
)


def hardware(*, ram: int = 2_000_000_000, pressure: float = 0,
             cpu: float = 0, swap: int = 0) -> LocalResourceSnapshot:
    return LocalResourceSnapshot(
        total_ram_bytes=8_000_000_000,
        available_ram_bytes=ram,
        total_disk_bytes=1_000_000_000_000,
        free_disk_bytes=500_000_000_000,
        cpu_count=12, cpu_load_ratio=cpu,
        total_swap_bytes=2_000_000_000,
        free_swap_bytes=2_000_000_000 - swap,
        memory_pressure_ratio=pressure,
    )


class FabricTests(unittest.TestCase):
    def test_metal_repeated_probe_releases_created_device_on_all_paths(self):
        metal = SimpleNamespace(
            MTLCreateSystemDefaultDevice=Mock(return_value=0xFEED),
        )
        objc = SimpleNamespace(
            sel_registerName=Mock(side_effect=lambda selector: selector),
            objc_autoreleasePoolPush=Mock(return_value=0xCAFE),
            objc_autoreleasePoolPop=Mock(),
        )
        observations = {
            b"hasUnifiedMemory": 1,
            b"recommendedMaxWorkingSetSize": 8_000_000_000,
            b"currentAllocatedSize": 300_000_000,
            b"release": 0,
        }
        def message(_device, selector):
            if selector not in observations:
                raise OSError("simulated Metal selector failure")
            return observations[selector]
        objc.objc_msgSend = Mock(side_effect=message)
        with patch(
            "skeleton.app.offline_resource_fabric.sys.platform", "darwin",
        ), patch(
            "skeleton.app.offline_resource_fabric.platform.machine",
            return_value="arm64",
        ), patch(
            "skeleton.app.offline_resource_fabric.ctypes.CDLL",
            side_effect=lambda path: metal if path.endswith("/Metal") else objc,
        ):
            for _ in range(3):
                probe = _probe_apple_metal()
                self.assertEqual(probe[0].vendor, "apple")
                self.assertEqual(probe[0].dedicated_total_bytes, 0)
            observations[b"hasUnifiedMemory"] = 0
            self.assertEqual(_probe_apple_metal(), ())
            observations[b"hasUnifiedMemory"] = 1
            del observations[b"recommendedMaxWorkingSetSize"]
            self.assertEqual(_probe_apple_metal(), ())
        self.assertEqual(
            objc.objc_autoreleasePoolPop.call_count, 5,
        )
        self.assertEqual(
            [call.args[1] for call in objc.objc_msgSend.call_args_list]
            .count(b"release"), 5,
        )

    def test_gpu_shared_host_budget_is_not_additive_or_fabricated(self):
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            integrated = GPUResource(
                device="uma0", vendor="drm",
                dedicated_total_bytes=1_000_000_000,
                dedicated_free_bytes=900_000_000,
                shared_total_bytes=3_000_000_000,
                shared_free_bytes=3_000_000_000,
                shared_with_system_ram=True,
                measurement="synthetic_test",
            )
            with patch("skeleton.app.offline_resource_fabric.probe_local_resources",
                       return_value=hardware()), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(integrated,),
            ):
                plan = fabric.plan(1_000_000, desired_streams=8,
                                   allow_gpu=True, requested_gpu_bytes=800_000_000)
                self.assertFalse(plan.gpu_eligible)  # 70% of dedicated VRAM
                plan = fabric.plan(1_000_000, allow_gpu=True,
                                   requested_gpu_bytes=600_000_000)
                self.assertTrue(plan.gpu_eligible)
                self.assertEqual(plan.gpu_device, "uma0")
                self.assertFalse(plan.as_dict()["backend_gpu_transfer_executed"])
                monitor = fabric.monitor()
                self.assertFalse(monitor["shared_memory_is_additive"])
                self.assertEqual(monitor["gpus"][0]["shared_free_bytes"],
                                 3_000_000_000)

    def test_unknown_gpu_is_never_inferred_from_system_ram(self):
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            with patch("skeleton.app.offline_resource_fabric.probe_local_resources",
                       return_value=hardware()), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                plan = fabric.plan(500_000, allow_gpu=True,
                                   requested_gpu_bytes=100_000)
                self.assertFalse(plan.gpu_eligible)
                self.assertIsNone(plan.gpu_device)
                self.assertFalse(fabric.monitor()["gpu_telemetry_available"])

    def test_ram_swap_pressure_switches_to_disk_and_slow_recovers(self):
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            with patch("skeleton.app.offline_resource_fabric.probe_gpu_resources",
                       return_value=()), patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=100_000_000, pressure=0.85,
                                      swap=1_900_000_000, cpu=0.9),
            ):
                low = fabric.plan(10_000_000, desired_streams=20)
                self.assertEqual(low.residency, "disk_chunks")
                self.assertTrue(low.readonly_staging)
                self.assertEqual(low.stream_count, 1)
                high_pressure = low.memory_pressure
            with patch("skeleton.app.offline_resource_fabric.probe_gpu_resources",
                       return_value=()), patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=7_000_000_000),
            ):
                recovered = fabric.plan(10_000_000, desired_streams=20)
                self.assertGreater(recovered.stream_count, low.stream_count)
                self.assertLess(recovered.memory_pressure, high_pressure)
                self.assertGreater(recovered.memory_pressure, 0)

    def test_concurrent_readonly_mmap_checksums_without_source_mutation(self):
        with TemporaryDirectory() as d:
            base = Path(d)
            source = base / "trusted"
            source.mkdir()
            contents = {
                "first.txt": b"the test source" * 12000,
                "second.dat": "unicode document — pass".encode() * 300,
                "empty.txt": b"",
            }
            for name, data in contents.items():
                (source / name).write_bytes(data)
            fabric = AdaptiveResourceFabric(base)
            with patch("skeleton.app.offline_resource_fabric.probe_local_resources",
                       return_value=hardware(ram=4_000_000_000)), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                records = fabric.stream_readonly(
                    source, contents.keys(), desired_streams=4,
                )
            self.assertEqual([r["source"] for r in records], list(contents))
            for item in records:
                expected = contents[item["source"]]
                self.assertEqual(item["sha256"], sha256(expected).hexdigest())
                self.assertEqual(item["size_bytes"], len(expected))
                self.assertTrue(item["readonly"])
                self.assertFalse(item["gpu_coherence_verified"])
                self.assertEqual((source / item["source"]).read_bytes(), expected)
            self.assertEqual(fabric.monitor()["active_streams"], 0)

    def test_symlink_escape_is_rejected(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            trusted = root / "trusted"
            trusted.mkdir()
            outside = root / "outside.txt"
            outside.write_text("secret")
            with self.assertRaises(ResourceFabricError):
                AdaptiveResourceFabric(root).stream_readonly(trusted, ("../outside.txt",))
            try:
                (trusted / "link.txt").symlink_to(outside)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(ResourceFabricError):
                AdaptiveResourceFabric(root).stream_readonly(trusted, ("link.txt",))

    def test_not_enough_disk_or_ram_rejects_admission(self):
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            low = replace(
                hardware(ram=100_000), free_disk_bytes=100_000,
            )
            with patch("skeleton.app.offline_resource_fabric.probe_local_resources",
                       return_value=low), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                with self.assertRaises(LocalResourcePressure):
                    fabric.plan(10_000_000)

    def test_bad_telemetry_and_untrusted_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            GPUResource(device="x", vendor="test", dedicated_total_bytes=10,
                        dedicated_free_bytes=11)
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            for value in (-1, True, 1.5):
                with self.assertRaises(ValueError):
                    fabric.plan(value)
            with self.assertRaises(ValueError):
                fabric.plan(1, desired_streams=0)


if __name__ == "__main__":
    unittest.main()
