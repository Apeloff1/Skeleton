"""Read only the declared eight-byte GGUF header; no source/license grant."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.host_probes.gguf_header import (
    probe_gguf_header,
)

class GGUFHeaderProbeTests(unittest.TestCase):
    @unittest.skipUnless(os.name=="posix" and hasattr(os,"O_NOFOLLOW"),
                         "POSIX O_NOFOLLOW test")
    def test_valid_header_is_only_a_weak_structural_hint(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "model.gguf"
            file.write_bytes(b"GGUF" + (3).to_bytes(4,"little"))
            result = probe_gguf_header(file)
        self.assertTrue(result.header_plausible)
        self.assertEqual(result.gguf_version,3)
        self.assertEqual(result.size_bytes,8)
        report=result.to_record()
        self.assertFalse(report["complete_file_sha256_verified"])
        self.assertFalse(report["tokenizer_source_verified"])
        self.assertFalse(report["model_license_approved"])
        self.assertFalse(report["native_model_started"])
        self.assertFalse(report["physical_device_qualified"])
        self.assertFalse(report["release_certified"])

    @unittest.skipUnless(os.name=="posix" and hasattr(os,"O_NOFOLLOW"),
                         "POSIX O_NOFOLLOW test")
    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"actual.gguf"
            target.write_bytes(b"GGUF" + (3).to_bytes(4,"little"))
            alias=Path(temp)/"alias.gguf"
            alias.symlink_to(target)
            observed=probe_gguf_header(alias)
        self.assertFalse(observed.header_plausible)
        self.assertEqual(observed.reason,"unavailable")

    @unittest.skipUnless(os.name=="posix" and hasattr(os,"O_NOFOLLOW"),
                         "POSIX no-follow test")
    def test_bounded_invalid_headers_and_short_files(self):
        vectors=(
            (b"GGUF", "short_file"),
            (b"NOTF"+(3).to_bytes(4,"little"),"wrong_magic"),
            (b"GGUF"+(99).to_bytes(4,"little"),"unsupported_version"),
            (b"GGUF"+(2).to_bytes(4,"little"),"header_plausible"),
        )
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"model.gguf"
            for data,reason in vectors:
                with self.subTest(reason=reason):
                    file.write_bytes(data)
                    self.assertEqual(probe_gguf_header(file).reason,reason)

    def test_nonexistent_model_is_held(self):
        with tempfile.TemporaryDirectory() as temp:
            result=probe_gguf_header(Path(temp)/"missing.gguf")
        self.assertFalse(result.header_plausible)
        self.assertEqual(result.reason,"unavailable")
