"""Exact immutable Python backend container runtime policy."""
from __future__ import annotations
import pathlib
import re
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
DOCKER=ROOT/"backend"/"Dockerfile"
PIN="python:3.14-alpine@sha256:f6a589d43c42b9e7f7dc67a12d37132491f362859a5d750607710cc56da3bc72"

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
