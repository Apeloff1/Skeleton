"""GGUF inspection cannot coerce paths or fabricate installed-model rights."""
from __future__ import annotations
import unittest
from pathlib import Path
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.host_probes import gguf_header

class GGUFHeaderContractTests(unittest.TestCase):
    def test_noncanonical_or_relative_file_path_refused(self):
        for item in (None,"/tmp/model.gguf",True,Path("./model.gguf"),
                     Path("/tmp/../models/model.gguf")):
            with self.subTest(path=str(item)),self.assertRaises(LaptopGateHold):
                gguf_header.probe_gguf_header(item)

    def test_invalid_header_records_are_refused(self):
        cases=(
            ("header_plausible",8,3,False),
            ("header_plausible",7,3,True),
            ("header_plausible",8,99,True),
            ("bogus",8,3,True),
            ("unavailable",True,None,True),
            ("unavailable",None,True,True),
            ("unavailable",None,None,"yes"),
        )
        for row in cases:
            with self.subTest(row=row),self.assertRaises(LaptopGateHold):
                gguf_header.GGUFHeaderObservation(*row)

    def test_unknown_platform_never_performs_an_unsecured_file_read(self):
        path=Path("/absolute/model.gguf")
        with (
            mock.patch.object(gguf_header.os,"name","nt"),
            mock.patch.object(gguf_header.os,"open",
                              side_effect=AssertionError("MUST NOT OPEN")),
        ):
            report=gguf_header.probe_gguf_header(path)
        self.assertEqual(report.reason,"unavailable")
        self.assertFalse(report.descriptor_nofollow)
        self.assertFalse(report.header_plausible)

    def test_file_header_alone_never_authorizes_inference(self):
        snapshot=gguf_header.GGUFHeaderObservation(
            "header_plausible",8,3,True
        ).to_record()
        self.assertFalse(snapshot["complete_file_sha256_verified"])
        self.assertFalse(snapshot["tokenizer_source_verified"])
        self.assertFalse(snapshot["model_license_approved"])
        self.assertFalse(snapshot["native_model_started"])
        self.assertFalse(snapshot["release_certified"])
