"""Exact offline capture/export comparison; no transport or storage grant."""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.dragon_capture_export_witness import (
    build_witness, inspect_independent_export, validate_witness,
)


class CaptureExportWitnessTests(unittest.TestCase):
    def fixture(self, raw):
        return build_witness(session_id="capture-fixture", session_version=7,
            source_id="a"*64,snapshot_digest="b"*64,intent_digest="c"*64,
            source_policy_version=2,raw_body_sha256=hashlib.sha256(raw).hexdigest())

    def test_exact_bytes_match_without_write_or_license_authority(self):
        raw=b'{"_key":1,"name":"Fixture"}\n'
        witness=self.fixture(raw)
        with TemporaryDirectory() as directory:
            path=Path(directory).resolve()/"export.jsonl"
            path.write_bytes(raw)
            result=inspect_independent_export(path,witness=witness,
                expected_witness_digest=witness["witness_digest"])
        self.assertTrue(result["capture_raw_hash_matched"])
        self.assertEqual(result["expected_rows"],1)
        self.assertEqual(result["input_sha256"],witness["raw_body_sha256"])
        for flag in ("storage_written","network_executed","dataset_import_authorized",
                     "source_rights_verified","live_capture_authority_rechecked",
                     "witness_signature_verified"):
            self.assertIs(result[flag],False)

    def test_tampered_receipt_and_changed_explicit_digest_are_refused(self):
        witness=self.fixture(b"fixture")
        changed={**witness,"session_version":8}
        with self.assertRaises(ValueError):
            validate_witness(changed)
        with patch("core.dragon_dataset_ingest.inspect_dataset") as inspect:
            with self.assertRaises(ValueError):
                inspect_independent_export(Path("/not-read"),witness=witness,
                    expected_witness_digest="0"*64)
            inspect.assert_not_called()

    def test_modified_bytes_refused_before_projection(self):
        witness=self.fixture(b'{"_key":1}\n')
        with TemporaryDirectory() as directory:
            path=Path(directory).resolve()/"changed.jsonl"
            path.write_bytes(b'{"_key":2}\n')
            with patch("core.dragon_dataset_ingest.pages") as pages:
                with self.assertRaisesRegex(ValueError,"SHA-256 differs"):
                    inspect_independent_export(path,witness=witness,
                        expected_witness_digest=witness["witness_digest"])
                pages.assert_not_called()

    def test_no_authority_flags_can_be_asserted(self):
        witness=self.fixture(b"fixture")
        for flag in ("raw_bytes_retained","dataset_import_authorized","network_authorized"):
            for value in (True,0,None):
                with self.subTest(flag=flag,value=value):
                    with self.assertRaises(ValueError):
                        validate_witness({**witness,flag:value})

    def test_rejects_ambiguous_or_unbounded_identity(self):
        for kwargs in ({"session_version":True},{"source_policy_version":-1},
                       {"source_id":"A"*64},{"session_id":"x"*129}):
            base=dict(session_id="fixture",session_version=1,source_id="a"*64,
                      snapshot_digest="b"*64,intent_digest="c"*64,
                      source_policy_version=0,raw_body_sha256="d"*64)
            with self.assertRaises(ValueError):
                build_witness(**{**base,**kwargs})


if __name__=="__main__":
    unittest.main()
