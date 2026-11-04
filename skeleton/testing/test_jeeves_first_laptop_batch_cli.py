"""The all-20 source diagnostic CLI never starts a real model or reads catalog stdin."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.batch.catalog import manifest
from skeleton.jeeves.native_fabric.laptop_ops.batch.fixtures import (
    successful_bundle, negative_bundle, encode_bundle,
)
from skeleton.jeeves.native_fabric.laptop_ops.batch.runner import (
    evaluate_bundle, evaluate_json,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import list_domains

from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
from skeleton.jeeves.native_fabric.laptop_ops.batch.cli import main

class TestBatchOperatorCli(unittest.TestCase):
    def _invoke(self, args, payload):
        reader = SimpleNamespace(buffer=BytesIO(payload))
        output = SimpleNamespace(buffer=BytesIO())
        errors = StringIO()
        with (
            mock.patch("skeleton.jeeves.native_fabric.laptop_ops.batch.cli.sys.stdin", reader),
            mock.patch("skeleton.jeeves.native_fabric.laptop_ops.batch.cli.sys.stdout", output),
            mock.patch("skeleton.jeeves.native_fabric.laptop_ops.batch.cli.sys.stderr", errors),
        ):
            code = main(args)
        return code, output.buffer.getvalue(), errors.getvalue()

    def test_catalog_reports_twenty_contracts_without_private_input(self):
        code,out,errors = self._invoke(["--catalog"], b"private task")
        self.assertEqual(code,0)
        self.assertFalse(errors)
        record = json.loads(out)
        self.assertEqual(len(record["domains"]),20)
        self.assertFalse(record["release_certified"])
        self.assertNotIn("private task", out.decode())

    def test_valid_synthetic_evidence_is_source_only(self):
        code,out,errors = self._invoke(
            ["--json-stdin"], encode_bundle(successful_bundle())
        )
        self.assertEqual(code,0)
        self.assertFalse(errors)
        record = json.loads(out)
        self.assertTrue(record["accepted_source_only"])
        self.assertFalse(record["real_native_inference_witnessed"])
        self.assertFalse(record["release_certified"])

    def test_one_negative_stage_returns_hold_not_a_success(self):
        payload = encode_bundle(
            negative_bundle("bootstrap", "model_archive")
        )
        code,out,errors = self._invoke(["--json-stdin"],payload)
        self.assertEqual(code,2)
        self.assertFalse(errors)
        record = json.loads(out)
        self.assertFalse(record["accepted_source_only"])
        self.assertFalse(record["physical_device_qualified"])

    def test_malformed_input_redacts_secret_and_emits_no_success(self):
        payload = b'{"private_task":"do not disclose"}'
        code,out,errors = self._invoke(["--json-stdin"],payload)
        self.assertEqual(code,2)
        self.assertEqual(out,b"")
        report = json.loads(errors)
        self.assertEqual(report["status"],"held")
        self.assertFalse(report["release_certified"])
        self.assertNotIn("do not disclose",errors)

    def test_catalog_mode_is_strictly_read_only(self):
        fake_reader = mock.Mock()
        output = SimpleNamespace(buffer=BytesIO())
        with (
            mock.patch("skeleton.jeeves.native_fabric.laptop_ops.batch.cli.sys.stdin", fake_reader),
            mock.patch("skeleton.jeeves.native_fabric.laptop_ops.batch.cli.sys.stdout", output),
        ):
            self.assertEqual(main(["--catalog"]),0)
        fake_reader.buffer.read.assert_not_called()
