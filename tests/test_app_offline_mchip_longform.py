"""Apple Silicon memory-tier selection and durable local longform paging."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.app.offline_resources import (
    LocalResourceSnapshot, _darwin_swap, probe_local_resources,
)
from skeleton.app.offline_resource_fabric import (
    AdaptiveResourceFabric, GPUResource, probe_gpu_resources,
)
from skeleton.app.offline_longform_virtual import (
    LongformMemoryError, LongformVirtualMemory,
)


def hardware(*, ram=2_000_000_000, swap_free=1_000_000_000):
    return LocalResourceSnapshot(
        total_ram_bytes=8_000_000_000,
        available_ram_bytes=ram,
        total_disk_bytes=1_000_000_000_000,
        free_disk_bytes=500_000_000_000,
        cpu_count=8, cpu_load_ratio=0.2,
        total_swap_bytes=2_000_000_000, free_swap_bytes=swap_free,
    )


class AppleSiliconVMTests(unittest.TestCase):
    def test_darwin_swap_usage_is_read_only_and_not_fake_free_ram(self):
        value = (
            (4_000_000_000).to_bytes(8, "little")
            + (1_000_000_000).to_bytes(8, "little")
            + (3_000_000_000).to_bytes(8, "little")
            + b"\x00" * 8
        )
        with patch(
            "skeleton.app.offline_resources._darwin_sysctl",
            return_value=value,
        ):
            self.assertEqual(_darwin_swap(), (4_000_000_000, 1_000_000_000))
        with patch(
            "skeleton.app.offline_resources.sys.platform", "darwin",
        ), patch(
            "skeleton.app.offline_resources._darwin_memory",
            return_value=(8_000_000_000, 2_000_000_000),
        ), patch(
            "skeleton.app.offline_resources._darwin_swap",
            return_value=(4_000_000_000, 1_000_000_000),
        ):
            with TemporaryDirectory() as d:
                snapshot = probe_local_resources(d)
        self.assertEqual(snapshot.available_ram_bytes, 2_000_000_000)
        self.assertEqual(snapshot.free_swap_bytes, 1_000_000_000)

    def test_metal_unified_capacity_does_not_expand_physical_ram(self):
        apple = GPUResource(
            device="Apple Silicon Metal", vendor="apple",
            dedicated_total_bytes=0, dedicated_free_bytes=0,
            shared_with_system_ram=True,
            recommended_working_set_bytes=12_000_000_000,
            current_allocated_bytes=9_000_000_000,
            measurement="metal_unified_working_set",
        )
        with TemporaryDirectory() as d:
            fabric = AdaptiveResourceFabric(d)
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=hardware(),
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(apple,),
            ):
                allowed = fabric.plan(
                    1_000_000, requested_gpu_bytes=400_000_000,
                    allow_gpu=True,
                )
                denied = fabric.plan(
                    1_000_000, requested_gpu_bytes=900_000_000,
                    allow_gpu=True,
                )
                self.assertTrue(allowed.gpu_eligible)
                self.assertFalse(denied.gpu_eligible)
                self.assertLessEqual(allowed.dedicated_gpu_budget_bytes,
                                     int(hardware().available_ram_bytes * 0.35))
                self.assertFalse(allowed.as_dict()["gpu_coherency_proven"])
                self.assertFalse(allowed.as_dict()["backend_gpu_transfer_executed"])
                self.assertEqual(fabric.monitor()["gpus"][0]["dedicated_free_bytes"], 0)

    def test_metal_probe_short_circuits_other_drivers_without_double_count(self):
        apple = GPUResource("Apple Metal", "apple", 0, 0,
                            shared_with_system_ram=True,
                            recommended_working_set_bytes=10_000_000_000,
                            current_allocated_bytes=2_000_000_000)
        with patch(
            "skeleton.app.offline_resource_fabric._probe_apple_metal",
            return_value=(apple,),
        ):
            self.assertEqual(probe_gpu_resources(), (apple,))


class LongformVMTests(unittest.TestCase):
    def test_large_utf8_work_is_compressed_pageable_and_recoverable(self):
        with TemporaryDirectory() as d:
            folder = Path(d)
            root = folder / "source"
            root.mkdir()
            text = ("Longform research memory and continuity — chapter. " * 120000)
            text += "finaluniquecontinuitytoken"
            (root / "novel.txt").write_text(text, encoding="utf-8")
            db = folder / "virtual.sqlite"
            with LongformVirtualMemory(db) as store:
                receipt = store.ingest(root, "novel.txt")
                self.assertEqual(receipt["source_sha256"],
                                 sha256(text.encode()).hexdigest())
                self.assertGreater(receipt["page_count"], 3)
                self.assertLess(receipt["stored_payload_bytes"],
                                receipt["source_bytes"])
                self.assertTrue(store.verify(receipt["source_id"])["verified"])
                found = store.search(receipt["source_id"], "finaluniquecontinuitytoken")
                self.assertEqual(len(found["hits"]), 1)
                self.assertIn("finaluniquecontinuitytoken",
                              found["hits"][0]["text"])
                first = store.read_window(receipt["source_id"], pages=1)
                self.assertEqual(first["returned_pages"], 1)
                self.assertTrue(text.startswith(first["text"]))
                self.assertFalse(first["model_context_applied"])
            with LongformVirtualMemory(db) as reopened:
                self.assertTrue(reopened.verify(receipt["source_id"])["verified"])
                self.assertEqual(
                    reopened.read_window(receipt["source_id"], pages=1)["text"],
                    first["text"],
                )

    def test_corrupt_page_and_projection_fail_closed(self):
        with TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "file.txt").write_text("immutable work " * 20000)
            with LongformVirtualMemory(folder / "private.sqlite") as store:
                result = store.ingest(folder, "file.txt")
                uid = result["source_id"]
                store._db.execute(
                    "UPDATE longform_pages SET encoded=X'01' "
                    "WHERE source_id=? AND ordinal=0", (uid,),
                )
                with self.assertRaises(LongformMemoryError):
                    store.verify(uid)
                with self.assertRaises(LongformMemoryError):
                    store.read_window(uid)

    def test_invalid_utf8_rolls_back_without_source_entry(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "invalid.txt").write_bytes(b"valid start" * 1000 + b"\xff")
            with LongformVirtualMemory(root / "vm.sqlite") as store:
                with self.assertRaisesRegex(LongformMemoryError, "UTF-8"):
                    store.ingest(root, "invalid.txt")
                count = store._db.execute(
                    "SELECT COUNT(*) FROM longform_sources",
                ).fetchone()[0]
                self.assertEqual(count, 0)
                self.assertEqual(store._db.execute(
                    "SELECT COUNT(*) FROM longform_pages",
                ).fetchone()[0], 0)

    def test_symlink_escape_rejected_without_reading_secret(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            base = root / "books"
            base.mkdir()
            (root / "private.txt").write_text("private")
            with LongformVirtualMemory(root / "vm.sqlite") as store:
                with self.assertRaises(LongformMemoryError):
                    store.ingest(base, "../private.txt")
                try:
                    (base / "redirect.txt").symlink_to(root / "private.txt")
                except (OSError, NotImplementedError):
                    return
                with self.assertRaises((LongformMemoryError, OSError)):
                    store.ingest(base, "redirect.txt")

    def test_low_memory_window_does_not_materialize_archive(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "large.txt").write_text("source words " * 3000)
            with LongformVirtualMemory(root / "vm.sqlite") as store:
                receipt = store.ingest(root, "large.txt")
                with patch(
                    "skeleton.app.offline_longform_virtual.probe_local_resources",
                    return_value=hardware(ram=2000),
                ):
                    with self.assertRaises(LongformMemoryError):
                        store.read_window(receipt["source_id"])


if __name__ == "__main__":
    unittest.main()
