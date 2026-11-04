"""Read-only local GGUF device observations respect cgroup ceilings.

Kernel counters and state filesystem are mocked. These tests never measure
real laptop performance or attest physical GPU, RAM/VRAM or release readiness.
"""
from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import device_observer
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation


MEMINFO = """MemTotal:       8000000 kB
MemAvailable:   6000000 kB
SwapFree:       2000000 kB
HugePages_Total: 0
"""


class DeviceMemoryBoundaryTests(unittest.TestCase):
    def observe(self, *, source=MEMINFO, version=2, cap=4_000_000_000,
                used=1_000_000_000, available_disk=10_000_000):
        disk=SimpleNamespace(f_bavail=available_disk, f_frsize=4096)
        with (
            mock.patch("builtins.open",return_value=StringIO(source)),
            mock.patch.object(
                device_observer,"_cgroup_reading",return_value=(version,cap,used),
            ),
            mock.patch.object(device_observer.os,"statvfs",return_value=disk),
        ):
            return device_observer.inspect_device("/private/ai-state")

    def test_cgroup_limit_tightens_effective_memory(self):
        result=self.observe()
        self.assertEqual(result["cgroup_version_observed"],2)
        self.assertEqual(result["cgroup_memory_limit_bytes"],4_000_000_000)
        self.assertEqual(result["effective_memory_available_bytes"],3_000_000_000)
        self.assertFalse(result["qualified_device"])
        self.assertTrue(result["measurement_only"])

    def test_unlimited_v2_preserves_host_reading_without_certifying(self):
        result=self.observe(cap=None,used=10_000_000)
        self.assertEqual(result["effective_memory_available_bytes"],6000000*1024)
        self.assertIsNone(result["cgroup_memory_limit_bytes"])
        self.assertFalse(result["qualified_device"])

    def test_missing_cgroup_returns_explicit_unknown_version(self):
        result=self.observe(version=None,cap=None,used=None)
        self.assertIsNone(result["cgroup_version_observed"])
        self.assertEqual(result["effective_memory_available_bytes"],6000000*1024)

    def test_exact_full_cgroup_is_zero_available_not_positive(self):
        result=self.observe(cap=100,used=100)
        self.assertEqual(result["effective_memory_available_bytes"],0)
        self.assertFalse(result["qualified_device"])

    def test_malformed_cgroup_cannot_increase_capacity(self):
        with mock.patch.object(
            device_observer,"_cgroup_reading",
            side_effect=ContractViolation("incomplete kernel memory"),
        ):
            with mock.patch("builtins.open",return_value=StringIO(MEMINFO)):
                with self.assertRaises(ContractViolation):
                    device_observer.inspect_device("/private/state")

    def test_duplicate_or_invalid_meminfo_is_rejected(self):
        cases=(
            MEMINFO+"MemTotal: 1 kB\n",
            MEMINFO.replace("6000000","bogus"),
            MEMINFO.replace("MemTotal:","MemTotal: -1"),
            MEMINFO.replace("8000000","100"),
            MEMINFO.replace("SwapFree:","Unknown:"),
            MEMINFO+"A"*5000,
        )
        for source in cases:
            with self.subTest(source=source[-30:]):
                with self.assertRaises(ContractViolation):
                    device_observer._parse_meminfo(source)

    def test_wrong_state_paths_rejected_before_file_reads(self):
        for path in ("relative", "/private/../other", "/bad\x00state",None,True):
            with self.subTest(path=repr(path)), mock.patch("builtins.open") as reader:
                with self.assertRaises(ContractViolation):
                    device_observer.inspect_device(path)
                reader.assert_not_called()

    def test_overflowed_disk_capacity_is_not_validated(self):
        with self.assertRaises(ContractViolation):
            self.observe(available_disk=1 << 63)

    def test_negative_disk_available_is_invalid(self):
        with self.assertRaises(ContractViolation):
            self.observe(available_disk=-1)

    def test_kernel_integer_accepts_v2_max_without_reading_more(self):
        with (
            mock.patch.object(device_observer.os,"open",return_value=9),
            mock.patch.object(
                device_observer.os,"read",side_effect=[b"max\n",b""],
            ) as read,
            mock.patch.object(device_observer.os,"close") as close,
        ):
            result=device_observer._kernel_integer(
                "/sys/fs/cgroup/memory.max",allow_max=True,
            )
        self.assertIsNone(result)
        self.assertEqual(read.call_count,2)
        close.assert_called_once_with(9)

    def test_kernel_integer_rejects_symlink_and_extra_bytes(self):
        for raw, extra in ((b"123\n",b"junk"),(b"-1\n",b""),(b"abc\n",b"")):
            with (
                self.subTest(raw=raw),
                mock.patch.object(device_observer.os,"open",return_value=9),
                mock.patch.object(device_observer.os,"read",side_effect=[raw,extra]),
                mock.patch.object(device_observer.os,"close"),
            ):
                with self.assertRaises(ContractViolation):
                    device_observer._kernel_integer(
                        "/sys/fs/cgroup/memory.max",
                    )

    def test_kernel_integer_missing_source_is_not_fabricated(self):
        with mock.patch.object(
            device_observer.os,"open",side_effect=FileNotFoundError,
        ):
            self.assertIs(
                device_observer._kernel_integer(
                    "/sys/fs/cgroup/memory.current",
                ),device_observer._MISSING,
            )

    def test_v2_memory_reads_use_exact_limit_and_current(self):
        calls=[]
        def observer(path, *,allow_max=False):
            calls.append(path)
            if path.endswith("memory.max"):
                return 8_000_000_000
            if path.endswith("memory.current"):
                return 6_000_000_000
            raise AssertionError(path)
        with mock.patch.object(
            device_observer,"_kernel_integer",side_effect=observer,
        ):
            version,limit,used=device_observer._cgroup_reading()
        self.assertEqual((version,limit,used),(2,8_000_000_000,6_000_000_000))
        self.assertEqual(len(calls),2)

    def test_missing_v2_current_denied_without_claimed_capacity(self):
        with mock.patch.object(
            device_observer,"_kernel_integer",
            side_effect=[8_000_000_000,device_observer._MISSING],
        ):
            with self.assertRaises(ContractViolation):
                device_observer._cgroup_reading()

    def test_cgroup_v1_sentinel_is_unlimited_but_observed(self):
        with mock.patch.object(
            device_observer,"_kernel_integer",
            side_effect=[
                device_observer._MISSING,1<<62,100_000_000
            ],
        ):
            result=device_observer._cgroup_reading()
        self.assertEqual(result,(1,None,100_000_000))


if __name__ == "__main__":
    unittest.main()
