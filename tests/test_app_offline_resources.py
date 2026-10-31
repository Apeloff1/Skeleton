"""Live hardware budget calculations, independent of a particular host."""
from __future__ import annotations

from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.app.offline_resources import (
    LocalResourcePressure, LocalResourceSnapshot,
    _linux_memory, _linux_swap, admit_resident_document, admit_disk_document,
    probe_local_resources,
)


class LocalResourceBudgetTests(unittest.TestCase):
    def test_canonical_offline_cli_stages_and_reverifies_actual_source_bytes(self):
        from skeleton.app.offline_cli import main
        measured = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        with TemporaryDirectory() as root:
            selected = Path(root) / "story.txt"
            selected.write_text("original narrative continuity")
            flags = [
                "--stage-sources", "--stage-approve", "--stage-root", root,
                "--stage-path", "story.txt", "--stage-streams", "2", "--json",
            ]
            with patch(
                "skeleton.app.offline_resource_fabric.probe_local_resources",
                return_value=measured,
            ), patch(
                "skeleton.app.offline_resource_fabric.probe_gpu_resources",
                return_value=(),
            ):
                out, err = StringIO(), StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main(flags), 0, err.getvalue())
                manifest = json.loads(out.getvalue())
                self.assertEqual(manifest["source_count"], 1)
                self.assertEqual(manifest["source_bytes"], selected.stat().st_size)
                self.assertFalse(manifest["manifest_authenticated"])
                replay = flags + [
                    "--stage-manifest-digest", manifest["manifest_digest"],
                ]
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    self.assertEqual(main(replay), 0)
                selected.write_text("mutated narrative continuity")
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    self.assertEqual(main(replay), 1)
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    self.assertEqual(main(flags[:-1]), 0)

    def test_stage_cli_fails_closed_without_approval_or_valid_deadline(self):
        from skeleton.app.offline_cli import main
        with TemporaryDirectory() as root:
            (Path(root) / "file.txt").write_text("original")
            cases = (
                ["--stage-sources", "--stage-root", root, "--stage-path", "file.txt"],
                ["--stage-sources", "--stage-approve", "--stage-root", root,
                 "--stage-path", "../escape"],
                ["--stage-sources", "--stage-approve", "--stage-root", root,
                 "--stage-path", "file.txt", "--stage-deadline-s", "nan"],
                ["--stage-path", "file.txt"],
            )
            for args in cases:
                with self.subTest(args=args), redirect_stdout(StringIO()), \
                     redirect_stderr(StringIO()):
                    self.assertNotEqual(main(args), 0)

    def test_canonical_offline_cli_measures_resources_without_model(self):
        from skeleton.app.offline_cli import main
        measured = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        stdout, stderr = StringIO(), StringIO()
        with TemporaryDirectory() as root, patch(
            "skeleton.app.offline_resource_fabric.probe_local_resources",
            return_value=measured,
        ), patch(
            "skeleton.app.offline_resource_fabric.probe_gpu_resources",
            return_value=(),
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                "--resource-monitor", "--json", "--resource-root", root,
                "--resource-plan-bytes", "1000000", "--resource-streams", "3",
            ])
        self.assertEqual(code, 0, stderr.getvalue())
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["hardware"]["available_ram_bytes"], 8_000_000_000)
        self.assertEqual(output["readonly_plan"]["source_bytes"], 1_000_000)
        self.assertTrue(output["readonly_plan"]["readonly_stream"])
        self.assertEqual(output["readonly_plan"]["stream_count"], 3)
        self.assertFalse(output["gpu_telemetry_available"])

    def test_resource_cli_rejects_conflicting_modes_and_invalid_roots(self):
        from skeleton.app.offline_cli import main
        for args in (
            ["--resource-monitor", "--model", "untrusted.json"],
            ["--resource-monitor", "--resource-plan-bytes", "-1"],
            ["--resource-monitor", "--resource-streams", "0"],
            ["--resource-plan-bytes", "100"],
        ):
            with self.subTest(args=args), redirect_stdout(StringIO()), \
                 redirect_stderr(StringIO()):
                self.assertEqual(main(args), 2)
        with TemporaryDirectory() as root:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main([
                    "--resource-monitor", "--resource-root",
                    str(Path(root) / "missing"),
                ]), 2)

    def snapshot(self, *, memory: int, disk: int, load: float = 0.0):
        return LocalResourceSnapshot(
            total_ram_bytes=16_000_000_000, available_ram_bytes=memory,
            total_disk_bytes=1_000_000_000_000, free_disk_bytes=disk,
            cpu_count=8, cpu_load_ratio=load,
        )

    def test_live_ram_changes_admission_without_static_file_quota(self):
        payload_size = 100_000_000
        plenty = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        tight = self.snapshot(memory=200_000_000, disk=300_000_000_000)
        admit_resident_document(plenty, payload_size)
        with self.assertRaisesRegex(LocalResourcePressure, "RAM"):
            admit_resident_document(tight, payload_size)
        self.assertLess(tight.resident_document_budget,
                        plenty.resident_document_budget)

    def test_free_disk_changes_writes_but_not_unmodified_reads(self):
        enough = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        low = self.snapshot(memory=8_000_000_000, disk=2_000_000_000)
        admit_resident_document(enough, 100_000_000, write=True)
        admit_resident_document(low, 100_000_000, write=False)
        with self.assertRaisesRegex(LocalResourcePressure, "disk"):
            admit_resident_document(low, 100_000_000, write=True)

    def test_load_adapts_processing_buffers_and_admission_batch(self):
        quiet = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        busy = self.snapshot(memory=8_000_000_000, disk=300_000_000_000,
                             load=0.95)
        self.assertGreater(quiet.read_chunk_bytes, busy.read_chunk_bytes)
        self.assertGreater(quiet.suggested_index_jobs,
                           busy.suggested_index_jobs)

    def test_container_memory_ceiling_overrides_host(self):
        meminfo = "MemTotal:       16000000 kB\nMemAvailable:  12000000 kB\n"
        counters = {
            "/sys/fs/cgroup/memory.max": 2_000_000_000,
            "/sys/fs/cgroup/memory.current": 1_500_000_000,
        }
        from unittest.mock import mock_open
        from skeleton.app import offline_resources
        def counter(path):
            return counters.get(str(path))
        with patch("builtins.open", mock_open(read_data=meminfo)), \
             patch.object(offline_resources, "_read_counter", side_effect=counter):
            self.assertEqual(_linux_memory(), (2_000_000_000, 500_000_000))

    def test_cpu_quota_is_respected(self):
        from skeleton.app import offline_resources
        with TemporaryDirectory() as temp:
            with patch.object(offline_resources, "_linux_memory",
                              return_value=(8_000_000_000, 4_000_000_000)), \
                 patch.object(offline_resources.os, "cpu_count", return_value=12), \
                 patch.object(offline_resources.Path, "read_text",
                              return_value="150000 100000"):
                snap = probe_local_resources(temp)
            self.assertEqual(snap.cpu_count, 2)

    def test_cpu_affinity_and_cgroup_v1_quota_are_both_respected(self):
        from skeleton.app import offline_resources
        counters = {
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": 150000,
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us": 100000,
        }
        with TemporaryDirectory() as temp, patch.object(
            offline_resources, "_linux_memory",
            return_value=(8_000_000_000, 4_000_000_000),
        ), patch.object(
            offline_resources.os, "cpu_count", return_value=16,
        ), patch.object(
            offline_resources.os, "sched_getaffinity",
            return_value={0, 1, 2}, create=True,
        ), patch.object(
            offline_resources.Path, "read_text", return_value="max 100000",
        ), patch.object(
            offline_resources, "_read_counter",
            side_effect=lambda path: counters.get(str(path)),
        ):
            self.assertEqual(probe_local_resources(temp).cpu_count, 2)
            counters.clear()  # Unlimited v1 quota still obeys affinity.
            self.assertEqual(probe_local_resources(temp).cpu_count, 3)

    def test_swap_is_a_pressure_signal_not_extra_free_ram(self):
        plenty = self.snapshot(memory=2_000_000_000, disk=300_000_000_000)
        committed = LocalResourceSnapshot(
            total_ram_bytes=plenty.total_ram_bytes,
            available_ram_bytes=plenty.available_ram_bytes,
            total_disk_bytes=plenty.total_disk_bytes,
            free_disk_bytes=plenty.free_disk_bytes,
            cpu_count=8, cpu_load_ratio=0.1,
            total_swap_bytes=8_000_000_000,
            free_swap_bytes=200_000_000,
            memory_pressure_ratio=0.35,
        )
        self.assertTrue(committed.should_spill_early)
        self.assertLess(committed.resident_document_budget,
                        plenty.resident_document_budget)
        self.assertLess(committed.suggested_index_jobs,
                        plenty.suggested_index_jobs)
        admit_disk_document(committed, 5_000_000)
        with self.assertRaisesRegex(LocalResourcePressure, "RAM"):
            admit_resident_document(committed, 200_000_000)

    def test_cgroup_swap_ceiling_is_respected(self):
        from unittest.mock import mock_open
        from skeleton.app import offline_resources
        meminfo = "SwapTotal: 4000000 kB\nSwapFree: 3000000 kB\n"
        counters = {
            "/sys/fs/cgroup/memory.swap.max": 1_000_000_000,
            "/sys/fs/cgroup/memory.swap.current": 800_000_000,
        }
        with (
            patch("builtins.open", mock_open(read_data=meminfo)),
            patch.object(offline_resources, "_read_counter",
                         side_effect=lambda p: counters.get(str(p))),
        ):
            self.assertEqual(_linux_swap(), (1_000_000_000, 200_000_000))

    def test_cgroup_v1_memsw_subtracts_physical_memory(self):
        from unittest.mock import mock_open
        from skeleton.app import offline_resources
        meminfo = "SwapTotal: 4000000 kB\nSwapFree: 3000000 kB\n"
        counters = {
            "/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes": 2_500_000_000,
            "/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes": 2_200_000_000,
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": 2_000_000_000,
            "/sys/fs/cgroup/memory/memory.usage_in_bytes": 1_800_000_000,
        }
        with patch("builtins.open", mock_open(read_data=meminfo)), patch.object(
            offline_resources, "_read_counter",
            side_effect=lambda path: counters.get(str(path)),
        ):
            self.assertEqual(_linux_swap(), (500_000_000, 100_000_000))
            del counters["/sys/fs/cgroup/memory/memory.usage_in_bytes"]
            self.assertEqual(_linux_swap(), (0, 0))

    def test_cgroup_v1_inconsistent_memsw_never_invents_capacity(self):
        from unittest.mock import mock_open
        from skeleton.app import offline_resources
        counters = {
            "/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes": 1_000,
            "/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes": 500,
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": 2_000,
            "/sys/fs/cgroup/memory/memory.usage_in_bytes": 700,
        }
        with patch("builtins.open", mock_open(
            read_data="SwapTotal: 4000000 kB\nSwapFree: 3000000 kB\n",
        )), patch.object(
            offline_resources, "_read_counter",
            side_effect=lambda path: counters.get(str(path)),
        ):
            self.assertEqual(_linux_swap(), (0, 0))

    def test_probe_reports_host_disk_and_recomputes(self):
        with TemporaryDirectory() as temp:
            with patch("skeleton.app.offline_resources._linux_memory",
                       return_value=(8_000_000_000, 4_000_000_000)):
                result = probe_local_resources(Path(temp))
            self.assertGreater(result.read_chunk_bytes, 0)
            self.assertGreater(result.free_disk_bytes, 0)
            self.assertGreaterEqual(result.cpu_count, 1)


if __name__ == "__main__":
    unittest.main()
