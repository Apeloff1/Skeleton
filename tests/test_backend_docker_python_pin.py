"""Exact immutable Python backend container runtime policy."""
from __future__ import annotations
import pathlib
import re
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
DOCKER=ROOT/"backend"/"Dockerfile"
PIN="python:3.14.10-alpine3.24@sha256:04357e8d728ac6a88a12b808f9b377762f937271ecaf5b99feb242c04de1ffc1"

class BackendDockerPythonPin(unittest.TestCase):
    def test_all_backend_stages_use_same_supported_pinned_abi(self):
        src=DOCKER.read_text(encoding="utf-8")
        stages=re.findall(r"^FROM\s+([^\s]+)\s+AS\s+(builder|runtime-source|production)$",src,re.MULTILINE)
        self.assertEqual([name for _,name in stages],["builder","runtime-source","production"])
        self.assertTrue(all(image==PIN for image,_ in stages))
        self.assertEqual(len(PIN.rsplit("sha256:",1)[-1]),64)
        self.assertNotIn("python:3.15-",src)
        self.assertIn('sys.version_info[:2] < (3, 15)',src)
        self.assertIn("/usr/local/lib/python3.14/site-packages",src)

if __name__=="__main__":
    unittest.main()
