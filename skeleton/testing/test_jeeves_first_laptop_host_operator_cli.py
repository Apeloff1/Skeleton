"""The local host probe CLI is read-only and redacts private model paths."""
from __future__ import annotations
from io import BytesIO, StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops.batch import cli
from skeleton.testing.test_jeeves_first_laptop_host_summary_contract import good
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.summary import HostObservation
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.cpu import CpuObservation

FLAGS = [
    "--host-observe",
    "--model-file", "/private/model.gguf",
    "--state-directory", "/private/state",
    "--threads", "4",
    "--memory-reservation-bytes", "8000000000",
    "--storage-reservation-bytes", "1000000000",
]

def invoke(flags):
    stdout=SimpleNamespace(buffer=BytesIO())
    stderr=StringIO()
    stdin=SimpleNamespace(buffer=BytesIO(b"private prompt not readable"))
    with (
        mock.patch.object(cli.sys,"stdin",stdin),
        mock.patch.object(cli.sys,"stdout",stdout),
        mock.patch.object(cli.sys,"stderr",stderr),
    ):
        code=cli.main(flags)
    return code,stdout.buffer.getvalue(),stderr.getvalue()

class HostProbeCliTests(unittest.TestCase):
    def test_success_reports_only_observations_not_model_or_path(self):
        with mock.patch.object(cli,"observe_host",return_value=good()) as observe:
            code,out,errors=invoke(FLAGS)
        self.assertEqual(code,0)
        self.assertEqual(errors,"")
        doc=json.loads(out)
        self.assertTrue(doc["structural_preconditions_observed"])
        self.assertFalse(doc["native_model_started"])
        self.assertFalse(doc["real_native_generation_witnessed"])
        self.assertFalse(doc["release_certified"])
        self.assertNotIn("/private",out.decode())
        self.assertNotIn("private prompt",out.decode())
        observe.assert_called_once_with(
            model_file=Path("/private/model.gguf"),
            state_directory=Path("/private/state"),
            threads=4,
            reserved_memory_bytes=8000000000,
            reserved_storage_bytes=1000000000,
        )

    def test_failed_cpu_quota_returns_nonzero_with_explicit_hold(self):
        observed=good()
        broken=HostObservation(
            CpuObservation(64,16,8,8),observed.memory,
            observed.storage,observed.gguf,
        )
        with mock.patch.object(cli,"observe_host",return_value=broken):
            code,out,errors=invoke(FLAGS)
        self.assertEqual(code,2)
        self.assertFalse(errors)
        doc=json.loads(out)
        self.assertFalse(doc["structural_preconditions_observed"])
        self.assertTrue(doc["observational_holds"])
        self.assertFalse(doc["physical_device_qualified"])
