"""Hardware resource fabric contracts: fail-closed GPU, immutable mmap, live control."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from threading import Event, Thread
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
from types import SimpleNamespace

from skeleton.app.offline_resources import LocalResourcePressure, LocalResourceSnapshot
from skeleton.app.offline_resource_fabric import (
    AdaptiveResourceFabric, GPUResource, ResourceFabricError,
    _probe_apple_metal, probe_gpu_resources,
    build_staging_manifest, STAGING_MANIFEST_SCHEMA,
    StagingManifestMismatch,
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
    def setUp(self):
        super().setUp()
        # Deterministic simulated host: real CI cgroup PSI is not test input.
        for name in ['probe_cgroup_events','probe_io_pressure','probe_cpu_throttle']:
            guard = patch("skeleton.app.offline_resource_fabric." + name,
                          return_value=None)
            guard.start()
            self.addCleanup(guard.stop)

    def test_bounded_waiter_gets_stream_slot_after_prior_reader_finishes(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "one.txt").write_bytes(b"first" * 100)
            (root / "two.txt").write_bytes(b"second" * 100)
            fabric = AdaptiveResourceFabric(root)
            single = replace(hardware(ram=4_000_000_000), cpu_count=1)
            entered, release = Event(), Event()
            results: dict[str, object] = {}
            from skeleton.app.offline_resource_fabric import _open_source_at
            def delayed_open(base, relative):
                if relative.name == "one.txt":
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError("first reader did not release")
                return _open_source_at(base, relative)
            def first():
                try:
                    results["first"] = fabric.stream_readonly(root, ("one.txt",))
                except BaseException as exc:
                    results["first"] = exc
            def second():
                try:
                    results["second"] = fabric.stream_readonly(
                        root, ("two.txt",), deadline_s=3, wait_for_slot=True,
                    )
                except BaseException as exc:
                    results["second"] = exc
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=single,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ), patch(
                "skeleton.app.offline_resource_fabric._open_source_at",
                side_effect=delayed_open,
            ):
                a = Thread(target=first, daemon=True)
                b = Thread(target=second, daemon=True)
                a.start()
                self.assertTrue(entered.wait(3))
                b.start()
                try:
                    for _ in range(100):
                        if fabric.monitor()["controller"]["waiting_stream_batches"] == 1:
                            break
                        release.wait(0.01)
                    self.assertEqual(fabric.monitor()["controller"]["waiting_stream_batches"], 1)
                    with self.assertRaises(LocalResourcePressure):
                        fabric.stream_readonly(root, ("two.txt",))
                finally:
                    release.set()
                    a.join(timeout=5)
                    b.join(timeout=5)
                self.assertFalse(a.is_alive())
                self.assertFalse(b.is_alive())
                self.assertIsInstance(results.get("first"), tuple)
                self.assertIsInstance(results.get("second"), tuple)
                self.assertEqual(fabric.monitor()["active_streams"], 0)
                self.assertEqual(fabric.monitor()["controller"]["waiting_stream_batches"], 0)

    def test_live_memory_pressure_recheck_aborts_long_stream_without_partial_receipt(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            payload = b"source-bound replay " * 8000
            (root / "large.txt").write_bytes(payload)
            fabric = AdaptiveResourceFabric(root)
            healthy = hardware(ram=8_000_000)
            pressured = hardware(ram=1000)
            observations = {"count": 0}
            def probe(_root):
                observations["count"] += 1
                return healthy if observations["count"] == 1 else pressured
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                side_effect=probe,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                with self.assertRaises(LocalResourcePressure):
                    fabric.stream_readonly(root, ("large.txt",))
            self.assertGreaterEqual(observations["count"], 2)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=healthy,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                monitor = fabric.monitor()
            self.assertEqual(monitor["active_streams"], 0)
            self.assertGreaterEqual(
                monitor["controller"]["live_pressure_rechecks"], 1,
            )
            self.assertGreaterEqual(
                monitor["controller"]["failed_stream_batches"], 1,
            )

    def test_live_pressure_recheck_preserves_digest_when_headroom_is_stable(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            payload = b"stable long source " * 8000
            (root / "large.txt").write_bytes(payload)
            fabric = AdaptiveResourceFabric(root)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=8_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                records = fabric.stream_readonly(root, ("large.txt",))
                self.assertEqual(records[0]["sha256"], sha256(payload).hexdigest())
                self.assertGreaterEqual(
                    fabric.monitor()["controller"]["live_pressure_rechecks"], 1,
                )

    def test_thermal_hysteresis_prevents_repeated_gpu_admission_flapping(self):
        hot = GPUResource(
            device="gpu0", vendor="nvidia", dedicated_total_bytes=1_000_000_000,
            dedicated_free_bytes=900_000_000, temperature_c=93,
            thermal_limit_c=90, measurement="synthetic_test",
        )
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(hot,),
            ) as devices:
                self.assertEqual(fabric.plan(1000).thermal_holds, 1)
                devices.return_value = (replace(hot, temperature_c=89),)
                self.assertEqual(fabric.plan(1000).thermal_holds, 1)
                self.assertEqual(fabric.monitor()["controller"]["thermal_hold_devices"], 1)
                devices.return_value = (replace(hot, temperature_c=None),)
                self.assertEqual(fabric.plan(1000).thermal_holds, 1)
                devices.return_value = (replace(hot, temperature_c=80),)
                self.assertEqual(fabric.plan(1000).thermal_holds, 0)
                devices.return_value = (replace(hot, temperature_c=93),)
                self.assertEqual(fabric.plan(1000).thermal_holds, 1)
                devices.return_value = ()
                self.assertEqual(fabric.plan(1000).thermal_holds, 0)

    def test_driver_measured_thermal_limit_vetoes_gpu_plan(self):
        hot = GPUResource(
            device="gpu0", vendor="nvidia", dedicated_total_bytes=1_000_000_000,
            dedicated_free_bytes=900_000_000, temperature_c=93,
            thermal_limit_c=90, measurement="synthetic_test",
        )
        self.assertTrue(hot.thermal_throttled)
        self.assertTrue(hot.as_dict()["thermal_throttled"])
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(hot,),
            ) as devices:
                held = fabric.plan(
                    1000, allow_gpu=True, requested_gpu_bytes=100_000_000,
                )
                self.assertFalse(held.gpu_eligible)
                self.assertEqual(held.thermal_holds, 1)
                self.assertIn("thermal hold", held.reason)
                devices.return_value = (replace(hot, temperature_c=60),)
                clear = fabric.plan(
                    1000, allow_gpu=True, requested_gpu_bytes=100_000_000,
                )
                self.assertTrue(clear.gpu_eligible)
                self.assertEqual(clear.thermal_holds, 0)
                self.assertNotEqual(clear.evidence_digest, held.evidence_digest)
                devices.return_value = (replace(hot, thermal_limit_c=None),)
                unknown = fabric.plan(
                    1000, allow_gpu=True, requested_gpu_bytes=100_000_000,
                )
                self.assertEqual(unknown.thermal_holds, 0)
        for invalid in (float("nan"), float("inf"), -100, 250):
            with self.assertRaises(ValueError):
                replace(hot, thermal_limit_c=invalid)

    def test_reverify_rejects_changed_source_and_changed_order(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.txt").write_bytes(b"original A")
            (root / "b.txt").write_bytes(b"original B")
            fabric = AdaptiveResourceFabric(root)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                records = fabric.stream_readonly(root, ("a.txt", "b.txt"))
                digest = build_staging_manifest(records)["manifest_digest"]
                self.assertTrue(fabric.reverify_staging_manifest(
                    root, ("a.txt", "b.txt"), digest,
                )["reverified"])
                with self.assertRaises(StagingManifestMismatch):
                    fabric.reverify_staging_manifest(root, ("b.txt", "a.txt"), digest)
                (root / "a.txt").write_bytes(b"mutated A")
                with self.assertRaises(StagingManifestMismatch):
                    fabric.reverify_staging_manifest(root, ("a.txt", "b.txt"), digest)
                with self.assertRaises(ResourceFabricError):
                    fabric.reverify_staging_manifest(root, ("a.txt",), "INVALID")
                with self.assertRaises(ResourceFabricError):
                    build_staging_manifest((dict(records[0], source="../escape"),))

    def test_staged_manifest_is_stable_across_parallelism_and_order_sensitive(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "first.txt").write_bytes(b"first" * 50)
            (root / "second.txt").write_bytes(b"second" * 40)
            fabric = AdaptiveResourceFabric(root)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                a = fabric.stream_readonly(root, ("first.txt", "second.txt"), desired_streams=1)
                b = fabric.stream_readonly(root, ("first.txt", "second.txt"), desired_streams=4)
                c = fabric.stream_readonly(root, ("second.txt", "first.txt"), desired_streams=2)
            manifest = build_staging_manifest(a)
            self.assertEqual(manifest, build_staging_manifest(b))
            self.assertEqual(manifest["manifest_schema"], STAGING_MANIFEST_SCHEMA)
            self.assertEqual(manifest["source_count"], 2)
            self.assertEqual(manifest["source_bytes"], 490)
            self.assertNotEqual(manifest["manifest_digest"], build_staging_manifest(c)["manifest_digest"])
            self.assertFalse(manifest["manifest_authenticated"])

    def test_staged_manifest_rejects_forgery_and_nonfinite_gpu_sensors(self):
        record = {
            "source": "chapter.txt", "size_bytes": 4,
            "sha256": sha256(b"text").hexdigest(),
            "readonly": True, "staging": "os_file_backed_mmap",
            "gpu_coherence_verified": False,
        }
        self.assertEqual(build_staging_manifest((record,))["source_bytes"], 4)
        for key, value in (
            ("sha256", "a" * 63), ("size_bytes", True),
            ("source", "chapter.txt\nforged"), ("readonly", False),
            ("gpu_coherence_verified", True), ("staging", "gpu_unified_memory"),
        ):
            with self.subTest(key=key), self.assertRaises(ResourceFabricError):
                build_staging_manifest((dict(record, **{key: value}),))
        for invalid in ((record, record), (), (dict(record, unexpected="field"),),
                        (dict(record, source="\ud800"),)):
            with self.assertRaises(ResourceFabricError):
                build_staging_manifest(tuple(invalid))
        for invalid in (float("nan"), float("inf"), -float("inf")):
            for key in ("utilization_ratio", "temperature_c"):
                with self.assertRaises(ValueError):
                    GPUResource(
                        device="gpu", vendor="test", dedicated_total_bytes=10,
                        dedicated_free_bytes=5, **{key: invalid},
                    )

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

    def test_atomic_stream_slot_lease_and_recovery(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "first.txt").write_bytes(b"first" * 100)
            (root / "second.txt").write_bytes(b"second" * 100)
            fabric = AdaptiveResourceFabric(root)
            single = replace(hardware(ram=4_000_000_000), cpu_count=1)
            started, release = Event(), Event()
            results = []
            from skeleton.app.offline_resource_fabric import _open_source_at
            def delayed_open(base, relative):
                started.set()
                if not release.wait(5):
                    raise RuntimeError("test release timed out")
                return _open_source_at(base, relative)
            def first_reader():
                try:
                    results.append(fabric.stream_readonly(root, ("first.txt",)))
                except BaseException as exc:
                    results.append(exc)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=single,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ), patch(
                "skeleton.app.offline_resource_fabric._open_source_at",
                side_effect=delayed_open,
            ):
                worker = Thread(target=first_reader, daemon=True)
                worker.start()
                try:
                    self.assertTrue(started.wait(3))
                    self.assertEqual(fabric.monitor()["active_streams"], 1)
                    self.assertEqual(fabric.plan(100).stream_count, 0)
                    with self.assertRaises(LocalResourcePressure):
                        fabric.stream_readonly(root, ("second.txt",))
                finally:
                    release.set()
                    worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(len(results), 1)
                self.assertIsInstance(results[0], tuple)
                self.assertEqual(fabric.monitor()["active_streams"], 0)
                self.assertEqual(len(fabric.stream_readonly(
                    root, ("second.txt",),
                )), 1)

    def test_untrusted_source_iterables_and_failed_worker_release(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "valid.txt").write_bytes(b"verified")
            fabric = AdaptiveResourceFabric(root)
            for source in (None, [["unhashable"]], (str(n) for n in range(10001))):
                with self.assertRaises(ResourceFabricError):
                    fabric.stream_readonly(root, source)
            single = replace(hardware(ram=4_000_000_000), cpu_count=1)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=single,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ), patch(
                "skeleton.app.offline_resource_fabric._open_source_at",
                side_effect=OSError("simulated I/O failure"),
            ):
                with self.assertRaises(OSError):
                    fabric.stream_readonly(root, ("valid.txt",))
                self.assertEqual(fabric.monitor()["active_streams"], 0)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=single,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                self.assertEqual(len(fabric.stream_readonly(
                    root, ("valid.txt",),
                )), 1)

    def test_readonly_stream_has_no_artificial_spill_capacity_quota(self):
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            disk_full = replace(
                hardware(ram=20_000_000), free_disk_bytes=10_000,
            )
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=disk_full,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                with self.assertRaises(LocalResourcePressure):
                    fabric.plan(2_000_000_000)
                plan = fabric.plan(2_000_000_000, readonly_stream=True)
                self.assertTrue(plan.readonly_stream)
                self.assertTrue(plan.readonly_staging)
                self.assertEqual(plan.residency, "disk_chunks")
                self.assertFalse(plan.as_dict()["backend_gpu_transfer_executed"])
                with self.assertRaises(ValueError):
                    fabric.plan(10, readonly_stream="true")
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=replace(disk_full, available_ram_bytes=0),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                with self.assertRaises(LocalResourcePressure):
                    fabric.plan(2_000_000_000, readonly_stream=True)

    def test_cancelled_stream_returns_no_partial_receipt_and_releases_slot(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "source.txt").write_bytes(b"verified source" * 100)
            fabric = AdaptiveResourceFabric(root)
            cancelled = Event()
            from skeleton.app.offline_resource_fabric import _open_source_at
            def cancel_after_open(base, relative):
                fd = _open_source_at(base, relative)
                cancelled.set()
                return fd
            with patch(
                "skeleton.app.offline_resource_fabric._open_source_at",
                side_effect=cancel_after_open,
            ):
                with self.assertRaisesRegex(ResourceFabricError, "cancelled"):
                    fabric.stream_readonly(
                        root, ("source.txt",), cancel_event=cancelled,
                    )
            self.assertEqual(fabric.monitor()["active_streams"], 0)
            with self.assertRaises(ResourceFabricError):
                fabric.stream_readonly(root, ("source.txt",), deadline_s=0)
            with self.assertRaises(ResourceFabricError):
                fabric.stream_readonly(root, ("source.txt",), deadline_s=float("nan"))
            with self.assertRaises(ResourceFabricError):
                fabric.stream_readonly(root, ("source.txt",), deadline_s=10 ** 1000)
            with self.assertRaises(ResourceFabricError):
                fabric.stream_readonly(root, ("source.txt",), deadline_s=True)
            self.assertEqual(len(fabric.stream_readonly(
                root, ("source.txt",), deadline_s=10.0,
            )), 1)

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



class CgroupPressureTests(unittest.TestCase):
    """Synthetic counters verify canonical hardware admission and recovery."""

    def setUp(self):
        super().setUp()
        # Deterministic simulated host: real CI cgroup PSI is not test input.
        for name in ['probe_io_pressure','probe_cpu_throttle']:
            guard = patch("skeleton.app.offline_resource_fabric." + name,
                          return_value=None)
            guard.start()
            self.addCleanup(guard.stop)


    def test_kernel_counter_probe_and_strict_unknown(self):
        from skeleton.app.offline_cgroup_events import probe_cgroup_events
        with TemporaryDirectory() as d:
            path = Path(d) / "memory.events.local"
            path.write_text("low 0\nhigh 7\nmax 2\noom 1\noom_kill 0\n")
            with patch("skeleton.app.offline_cgroup_events.sys.platform", "linux"):
                sample = probe_cgroup_events(d)
                self.assertEqual((sample.scope, sample.high, sample.maximum), ("local", 7, 2))
                path.write_text("high 3\nhigh 4\nmax 0\noom 0\noom_kill 0\n")
                self.assertIsNone(probe_cgroup_events(d))
                path.unlink()
                self.assertIsNone(probe_cgroup_events(d))
            with patch("skeleton.app.offline_cgroup_events.sys.platform", "win32"):
                self.assertIsNone(probe_cgroup_events(d))

    def test_high_event_caps_streams_and_vetoes_shared_gpu(self):
        from skeleton.app.offline_cgroup_events import CgroupEvents, CgroupPressureTracker
        now = [1_000_000_000]
        before = CgroupEvents("local", 1, 0, 0, 0)
        after = CgroupEvents("local", 2, 0, 0, 0)
        gpu = GPUResource(
            device="UMA", vendor="apple", dedicated_total_bytes=0,
            dedicated_free_bytes=0, shared_with_system_ram=True,
            recommended_working_set_bytes=2_000_000_000, current_allocated_bytes=0,
        )
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            fabric._cgroup = CgroupPressureTracker(clock_ns=lambda: now[0])
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(gpu,),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_cgroup_events",
                side_effect=[before, after, after],
            ):
                normal = fabric.plan(10_000, desired_streams=8, allow_gpu=True,
                                     requested_gpu_bytes=100_000_000)
                self.assertTrue(normal.gpu_eligible)
                throttled = fabric.plan(10_000, desired_streams=8, allow_gpu=True,
                                        requested_gpu_bytes=100_000_000)
                self.assertEqual(throttled.stream_count, 1)
                self.assertFalse(throttled.gpu_eligible)
                self.assertTrue(throttled.cgroup_high_backpressure)
                self.assertEqual(
                    fabric.monitor()["controller"]["cgroup_memory_events"][
                        "high_transitions"], 1,
                )
            now[0] += 6_000_000_000
            self.assertFalse(fabric._cgroup.snapshot()["high_backpressure"])

    def test_oom_denies_staging_then_recovers(self):
        from skeleton.app.offline_cgroup_events import CgroupEvents, CgroupPressureTracker
        now = [1_000_000_000]
        before = CgroupEvents("local", 0, 0, 0, 0)
        oom = CgroupEvents("local", 0, 0, 1, 0)
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            fabric._cgroup = CgroupPressureTracker(clock_ns=lambda: now[0])
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_cgroup_events",
                side_effect=[before, oom, None, oom],
            ):
                fabric.plan(1000, readonly_stream=True)
                with self.assertRaisesRegex(LocalResourcePressure, "cgroup OOM"):
                    fabric.plan(1000, readonly_stream=True)
                self.assertTrue(fabric._cgroup.snapshot()["oom_backpressure"])
                now[0] += 31_000_000_000
                self.assertFalse(fabric.plan(1000, readonly_stream=True).cgroup_oom_backpressure)

    def test_counter_reset_and_unknown_keep_oom_hold(self):
        from skeleton.app.offline_cgroup_events import CgroupEvents, CgroupPressureTracker
        now = [10_000_000_000]
        tracker = CgroupPressureTracker(clock_ns=lambda: now[0])
        tracker.sample(CgroupEvents("local", 5, 0, 1, 1))
        tracker.sample(CgroupEvents("local", 5, 0, 2, 2))
        tracker.sample(CgroupEvents("local", 0, 0, 0, 0))
        tracker.sample(None)
        self.assertFalse(tracker.snapshot()["measured"])
        self.assertTrue(tracker.snapshot()["oom_backpressure"])
        self.assertEqual(tracker.snapshot()["oom_transitions"], 1)
        now[0] += 31_000_000_000
        self.assertFalse(tracker.snapshot()["oom_backpressure"])

    def test_invalid_sample_and_clock_regression_rejected(self):
        from skeleton.app.offline_cgroup_events import CgroupPressureTracker
        now = [5]
        tracker = CgroupPressureTracker(clock_ns=lambda: now[0])
        with self.assertRaises(TypeError):
            tracker.sample({"high": 1})
        tracker.sample(None)
        now[0] = 4
        with self.assertRaises(ValueError):
            tracker.snapshot()



class IOPressureTests(unittest.TestCase):
    """Kernel PSI parser and canonical source planner use simulated readings."""

    def setUp(self):
        super().setUp()
        # Deterministic simulated host: real CI cgroup PSI is not test input.
        for name in ['probe_cgroup_events','probe_cpu_throttle']:
            guard = patch("skeleton.app.offline_resource_fabric." + name,
                          return_value=None)
            guard.start()
            self.addCleanup(guard.stop)


    def test_linux_psi_parser_and_invalid_values(self):
        from skeleton.app.offline_io_pressure import probe_io_pressure
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "io.pressure").write_text(
                "some avg10=19.25 avg60=8.0 avg300=3.0 total=10000\n"
                "full avg10=6.25 avg60=2.0 avg300=1.0 total=2000\n"
            )
            with patch("skeleton.app.offline_io_pressure.sys.platform", "linux"):
                sample = probe_io_pressure(root, root / "missing")
                self.assertEqual(sample.scope, "cgroup")
                self.assertEqual(sample.some_avg10, 19.25)
                (root / "io.pressure").write_text(
                    "some avg10=nan total=0\nfull avg10=0 total=0\n"
                )
                self.assertIsNone(probe_io_pressure(root, root / "missing"))
            with patch("skeleton.app.offline_io_pressure.sys.platform", "darwin"):
                self.assertIsNone(probe_io_pressure(root, root / "missing"))

    def test_io_stall_hysteresis_reduces_actual_staging_plan(self):
        from skeleton.app.offline_io_pressure import IOPressure
        fast = IOPressure("cgroup", 0.5, 0.0, 100, 0)
        stalled = IOPressure("cgroup", 22.0, 6.0, 1000, 400)
        recovering = IOPressure("cgroup", 12.0, 3.0, 1200, 420)
        clear = IOPressure("cgroup", 4.0, 0.5, 1500, 430)
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_cgroup_events",
                return_value=None,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_io_pressure",
                side_effect=[fast, stalled, recovering, clear, clear],
            ):
                normal = fabric.plan(1000, desired_streams=8)
                self.assertGreater(normal.stream_count, 1)
                slowed = fabric.plan(1000, desired_streams=8)
                self.assertEqual(slowed.stream_count, 1)
                self.assertTrue(slowed.io_backpressure)
                self.assertIn("IO stall", slowed.reason)
                self.assertTrue(fabric.plan(1000, desired_streams=8).io_backpressure)
                resumed = fabric.plan(1000, desired_streams=8)
                self.assertFalse(resumed.io_backpressure)
                self.assertGreater(resumed.stream_count, 1)
                receipt = fabric.monitor()["controller"]["io_pressure"]
                self.assertTrue(receipt["measured"])
                self.assertEqual(receipt["transitions"], 2)

    def test_missing_io_sample_retains_congestion(self):
        from skeleton.app.offline_io_pressure import IOPressure, IOPressureController
        controller = IOPressureController()
        controller.observe(IOPressure("host", 25.0, 5.0, 100, 100))
        controller.observe(None)
        self.assertFalse(controller.snapshot()["measured"])
        self.assertTrue(controller.snapshot()["congested"])
        controller.observe(IOPressure("host", 3.0, 0.0, 120, 100))
        self.assertFalse(controller.snapshot()["congested"])
        self.assertEqual(controller.snapshot()["transitions"], 2)
        with self.assertRaises(TypeError):
            controller.observe({"some": 25})



class CPUThrottleTests(unittest.TestCase):
    """Synthetic cgroup CPU.stat deltas control the canonical staging planner."""

    def setUp(self):
        super().setUp()
        # Deterministic simulated host: real CI cgroup PSI is not test input.
        for name in ['probe_cgroup_events','probe_io_pressure']:
            guard = patch("skeleton.app.offline_resource_fabric." + name,
                          return_value=None)
            guard.start()
            self.addCleanup(guard.stop)


    def test_linux_cpu_stat_probe_and_invalid_counters(self):
        from skeleton.app.offline_cpu_throttle import probe_cpu_throttle
        with TemporaryDirectory() as d:
            stat = Path(d) / "cpu.stat"
            stat.write_text("usage_usec 500\nnr_periods 100\nnr_throttled 20\n"
                            "throttled_usec 300\n")
            with patch("skeleton.app.offline_cpu_throttle.sys.platform", "linux"):
                sample = probe_cpu_throttle(d)
                self.assertEqual((sample.periods, sample.throttled_periods), (100, 20))
                stat.write_text("nr_periods 2\nnr_throttled 3\nthrottled_usec 1\n")
                self.assertIsNone(probe_cpu_throttle(d))
            with patch("skeleton.app.offline_cpu_throttle.sys.platform", "darwin"):
                self.assertIsNone(probe_cpu_throttle(d))

    def test_throttling_hysteresis_limits_real_stream_plan(self):
        from skeleton.app.offline_cpu_throttle import CPUThrottleSample
        before = CPUThrottleSample(100, 10, 100)
        busy = CPUThrottleSample(200, 40, 200)
        recovering = CPUThrottleSample(300, 55, 250)
        clear = CPUThrottleSample(400, 56, 260)
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(ram=4_000_000_000),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_cgroup_events",
                return_value=None,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_io_pressure",
                return_value=None,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_cpu_throttle",
                side_effect=[before, busy, recovering, clear, clear],
            ):
                self.assertGreater(fabric.plan(1000, desired_streams=8).stream_count, 1)
                slowed = fabric.plan(1000, desired_streams=8)
                self.assertTrue(slowed.cpu_throttle_backpressure)
                self.assertEqual(slowed.stream_count, 1)
                self.assertIn("CPU throttling", slowed.reason)
                self.assertTrue(fabric.plan(1000, desired_streams=8).cpu_throttle_backpressure)
                self.assertFalse(fabric.plan(1000, desired_streams=8).cpu_throttle_backpressure)
                receipt = fabric.monitor()["controller"]["cpu_throttle"]
                self.assertEqual(receipt["transitions"], 2)
                self.assertTrue(receipt["measured"])

    def test_unknown_and_reset_preserve_throttle_hold(self):
        from skeleton.app.offline_cpu_throttle import (
            CPUThrottleSample, CPUThrottleController,
        )
        controller = CPUThrottleController()
        controller.observe(CPUThrottleSample(100, 10, 100))
        controller.observe(CPUThrottleSample(200, 50, 200))
        controller.observe(None)
        self.assertTrue(controller.snapshot()["backpressure"])
        self.assertFalse(controller.snapshot()["measured"])
        controller.observe(CPUThrottleSample(0, 0, 0))
        self.assertTrue(controller.snapshot()["backpressure"])
        controller.observe(CPUThrottleSample(100, 0, 1))
        self.assertFalse(controller.snapshot()["backpressure"])
        with self.assertRaises(TypeError):
            controller.observe({"periods": 100})


if __name__ == "__main__":
    unittest.main()
