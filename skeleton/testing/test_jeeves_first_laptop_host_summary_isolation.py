"""Host inventory cannot call a native provider, shell or private task reader."""
from __future__ import annotations
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops.host_probes import summary
from skeleton.testing.test_jeeves_first_laptop_host_summary_contract import good
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold

class HostSummaryIsolationTests(unittest.TestCase):
    def test_exact_four_read_only_observations_are_composed(self):
        original=good()
        model=Path("/models/source.gguf")
        state=Path("/state")
        with (
            mock.patch.object(summary,"observe_cpu",return_value=original.cpu) as cpu,
            mock.patch.object(summary,"observe_ram",return_value=original.memory) as memory,
            mock.patch.object(summary,"observe_disk",return_value=original.storage) as disk,
            mock.patch.object(summary,"probe_gguf_header",return_value=original.gguf) as gguf,
            mock.patch.object(subprocess,"Popen",side_effect=AssertionError("no shell")),
        ):
            result=summary.observe_host(
                model_file=model,state_directory=state,threads=4,
                reserved_memory_bytes=8000000000,reserved_storage_bytes=1000000000,
            )
        self.assertEqual(result,original)
        cpu.assert_called_once_with(4)
        memory.assert_called_once_with(8000000000)
        disk.assert_called_once_with(state,1000000000)
        gguf.assert_called_once_with(model)

    def test_private_model_and_state_paths_are_not_serialized(self):
        original=good()
        with (
            mock.patch.object(summary,"observe_cpu",return_value=original.cpu),
            mock.patch.object(summary,"observe_ram",return_value=original.memory),
            mock.patch.object(summary,"observe_disk",return_value=original.storage),
            mock.patch.object(summary,"probe_gguf_header",return_value=original.gguf),
        ):
            value=summary.observe_host(
                model_file=Path("/private/passwords/model.gguf"),
                state_directory=Path("/private/secrets/state"),
                threads=4,reserved_memory_bytes=8000000000,
                reserved_storage_bytes=1000000000,
            )
        payload=str(value.to_record())
        self.assertNotIn("/private",payload)
        self.assertNotIn("passwords",payload)
        self.assertNotIn("secrets",payload)
        self.assertFalse(value.to_record()["release_certified"])

    def test_missing_required_paths_rejected_before_observations(self):
        with mock.patch.object(summary,"observe_cpu") as cpu:
            with self.assertRaises(LaptopGateHold):
                summary.observe_host(
                    model_file="relative.gguf",state_directory=Path("/state"),
                    threads=4,reserved_memory_bytes=100,reserved_storage_bytes=100,
                )
        cpu.assert_not_called()
