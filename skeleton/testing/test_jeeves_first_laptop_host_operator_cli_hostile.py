"""No malformed operator flags may disclose private path or launch inference."""
from __future__ import annotations
from io import BytesIO, StringIO
from types import SimpleNamespace
import json
import unittest
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops.batch import cli

class HostCliHostileTests(unittest.TestCase):
    def _call(self,args):
        stdout=SimpleNamespace(buffer=BytesIO())
        stderr=StringIO()
        stdin=mock.Mock()
        with (
            mock.patch.object(cli.sys,"stdout",stdout),
            mock.patch.object(cli.sys,"stderr",stderr),
            mock.patch.object(cli.sys,"stdin",stdin),
            mock.patch.object(cli,"observe_host") as probe,
        ):
            result=cli.main(args)
        return result,stdout.buffer.getvalue(),stderr.getvalue(),probe,stdin

    def test_missing_path_or_budget_flag_holds_without_model_access(self):
        inputs=[
            ["--host-observe"],
            ["--host-observe","--model-file","/private/model.gguf"],
            ["--host-observe","--threads","4"],
        ]
        for args in inputs:
            with self.subTest(args=args):
                status,out,err,probe,reader=self._call(args)
                self.assertEqual(status,2)
                self.assertFalse(out)
                self.assertEqual(json.loads(err)["status"],"held")
                self.assertNotIn("/private",err)
                reader.buffer.read.assert_not_called()
                probe.assert_not_called()

    def test_mode_cannot_borrow_host_paths_or_hidden_settings(self):
        cases=(
            ["--catalog","--model-file","/private/model.gguf"],
            ["--json-stdin","--threads","8"],
            ["--catalog","--host-observe"],
            ["--catalog","--unknown-private-parameter","/private/secret"],
        )
        for args in cases:
            with self.subTest(args=args):
                status,out,err,probe,reader=self._call(args)
                self.assertEqual(status,2)
                self.assertFalse(out)
                self.assertIn('"status": "held"',err)
                self.assertNotIn("/private",err)
                probe.assert_not_called()
                reader.buffer.read.assert_not_called()

    def test_malformed_numeric_args_are_redacted_by_parser(self):
        args=[
            "--host-observe",
            "--model-file","/private/hide-me.gguf",
            "--state-directory","/private/state",
            "--threads","untrusted_input",
            "--memory-reservation-bytes","10",
            "--storage-reservation-bytes","10",
        ]
        code,out,err,probe,_=self._call(args)
        self.assertEqual(code,2)
        self.assertFalse(out)
        self.assertNotIn("untrusted_input",err)
        self.assertNotIn("/private",err)
        self.assertFalse(json.loads(err)["release_certified"])
        probe.assert_not_called()
