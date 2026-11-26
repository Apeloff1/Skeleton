import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("emerald_preflight", Path(__file__).resolve().parent / "emerald_asset_preflight.py")
assert spec and spec.loader
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)


class PreflightTests(unittest.TestCase):
    def test_missing_mutated_and_exact_bytes_do_not_qualify_hardware(self):
        data = b"fixture"
        digest = hashlib.sha256(data).hexdigest()
        pin = {"assetSet": "synthetic", "web": {"bytes": len(data), "sha256": digest},
               "native": {"modelBytes": len(data), "modelSha256": digest, "sourceBytes": len(data), "sourceSha256": digest}}
        with tempfile.TemporaryDirectory() as root:
            paths = {name: Path(root) / name for name, *_ in pre.ASSETS}
            paths["web"].write_bytes(data)
            paths["model"].write_bytes(b"changed")
            result = pre.assess(paths, pin)
            self.assertEqual(result["assets"]["source"]["state"], "missing")
            self.assertEqual(result["assets"]["model"]["state"], "digest-mismatch")
            self.assertFalse(result["all_exact_bytes_available"])
            for path in paths.values():
                path.write_bytes(data)
            result = pre.assess(paths, pin)
            self.assertTrue(result["all_exact_bytes_available"])
            self.assertFalse(result["physical_rtx_verified"])
            self.assertFalse(result["engine_compiled"])
            self.assertFalse(result["artist_approved"])
            self.assertFalse(result["release_qualified"])


if __name__ == "__main__":
    unittest.main()
