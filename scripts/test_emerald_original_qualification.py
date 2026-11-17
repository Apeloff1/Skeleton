"""Synthetic orchestration boundary; not original GLB or physical device evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qualify_emerald_original as gate


class OriginalAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pin = {"modelBytes": 123, "modelSha256": "a" * 64, "sourceSha256": "b" * 64}
        self.full_pin = {"assetSet": "fixture", "native": self.pin}
        self.names = ["clip" + str(i) for i in range(380)]
        identity = {"model_sha256": self.pin["modelSha256"], "model_bytes": 123}
        self.animation = {**identity, "clips": [{"name": n} for n in self.names]}
        self.skin = {**identity, "skin_palette_sizes": [108],
                     "total_vertices_by_primitive": 3, "total_index_or_vertex_count": 3}
        self.materials = {**identity, "images": [{}, {}, {}, {}], "unique_image_hashes": 4}
        self.structure = {"clips": self.names, "joints": 108}
        for owner, attr, value in (
            (gate, "copy_exact", None), (gate, "inspect_glb", self.structure),
            (gate, "verify_peak_receipt", self.structure), (gate.animation, "audit_pinned", self.animation),
            (gate.skin, "audit_pinned", self.skin), (gate.materials, "audit_pinned", self.materials),
            (gate, "verify_delivery", {"asset_set": "fixture"}),
        ):
            mock = patch.object(owner, attr, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_complete_original_audit_without_device_claim(self):
        result = gate.qualify(self.root, self.full_pin)
        self.assertTrue(result["sampled_animation_qualified"])
        self.assertFalse(result["native_staging_qualified"])
        for name in ("engine_compiled", "physical_rtx_verified", "artist_approved", "release_qualified"):
            self.assertFalse(result[name])
        self.assertEqual(len(result["model_audits"]["report_digests"]), 4)

    def test_reject_mismatched_digest(self):
        self.skin["model_sha256"] = "x"
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            gate.qualify(self.root, self.full_pin)

    def test_reject_duplicate_clip(self):
        self.animation["clips"][1]["name"] = self.names[0]
        with self.assertRaisesRegex(ValueError, "clip catalogue"):
            gate.qualify(self.root, self.full_pin)

    def test_reject_joint_mismatch(self):
        self.skin["skin_palette_sizes"] = [107]
        with self.assertRaisesRegex(ValueError, "joint census"):
            gate.qualify(self.root, self.full_pin)

    def test_reject_texture_identity_count(self):
        self.materials["unique_image_hashes"] = 3
        with self.assertRaisesRegex(ValueError, "image census"):
            gate.qualify(self.root, self.full_pin)

    def test_reject_wrong_staged_source_receipt(self):
        with patch.object(gate, "verify_stage", return_value={
            "model_sha256": self.pin["modelSha256"], "source_sha256": "wrong",
            "native_staging_qualified": True,
        }), self.assertRaisesRegex(ValueError, "staging evidence mismatch"):
            gate.qualify(self.root, self.full_pin, staged=self.root)

    def test_independent_stage_admission_without_unreal_claim(self):
        with patch.object(gate, "verify_stage", return_value={
            "model_sha256": self.pin["modelSha256"], "source_sha256": self.pin["sourceSha256"],
            "native_staging_qualified": True,
        }):
            result = gate.qualify(self.root, self.full_pin, staged=self.root)
        self.assertTrue(result["native_staging_qualified"])
        self.assertFalse(result["engine_compiled"])


if __name__ == "__main__":
    unittest.main()
