import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("dragon_atelier_admit", Path(__file__).resolve().parents[1] / "scripts/dragon_atelier_admit.py")
assert SPEC and SPEC.loader
admit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admit)


def fixture():
    # Synthetic structural fixture, never represented as a rendered dragon.
    return {"asset": {"version": "2.0"}, "nodes": [{} for _ in range(108)],
            "skins": [{"joints": list(range(108))}], "buffers": [{"byteLength": 4}],
            "bufferViews": [{"buffer": 0, "byteLength": 4}],
            "meshes": [{}], "scenes": [{}],
            "animations": [{"name": f"clip_{i}", "channels": [{}], "samplers": [{}]} for i in range(380)]}


def glb(doc):
    raw = json.dumps(doc).encode()
    raw += b" " * (-len(raw) % 4)
    return struct.pack("<4sIIII", b"glTF", 2, len(raw) + 32, len(raw), 0x4E4F534A) + raw + struct.pack("<II", 4, 0x004E4942) + b"\x00" * 4


class AdmissionTests(unittest.TestCase):
    def inspect(self, doc, transform=lambda x: x, pin=None):
        raw = transform(glb(doc))
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "emerald_continuum.glb"
            p.write_bytes(raw)
            return admit.inspect_glb(p, pin or hashlib.sha256(raw).hexdigest())

    def test_fixture_receipt_is_not_artistic_evidence(self):
        receipt = self.inspect(fixture())
        self.assertEqual(receipt["joints"], 108)
        self.assertEqual(len(receipt["clips"]), 380)
        self.assertFalse(receipt["physical_rtx_qualification"])
        self.assertFalse(receipt["artistic_qualification"])

    def test_structural_fixture_cannot_impersonate_pinned_original(self):
        receipt = self.inspect(fixture())
        pin = {"modelSha256": "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a", "modelBytes": 463149740}
        with self.assertRaisesRegex(ValueError, "repository-pinned"):
            admit.verify_peak_receipt(receipt, pin)

    def test_wrong_digest(self):
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.inspect(fixture(), pin="0" * 64)

    def test_external_resource(self):
        doc = fixture()
        doc["images"] = [{"uri": "https://example.invalid/texture.png"}]
        with self.assertRaisesRegex(ValueError, "external resource"):
            self.inspect(doc)

    def test_reduced_rig(self):
        doc = fixture()
        doc["skins"][0]["joints"].pop()
        with self.assertRaisesRegex(ValueError, "skeleton threshold"):
            self.inspect(doc)

    def test_duplicate_clips(self):
        doc = fixture()
        doc["animations"][-1]["name"] = "clip_0"
        with self.assertRaisesRegex(ValueError, "animation threshold"):
            self.inspect(doc)

    def test_truncated(self):
        with self.assertRaisesRegex(ValueError, "envelope"):
            self.inspect(fixture(), lambda raw: raw[:-1])

    def test_view_outside_buffer(self):
        doc = fixture()
        doc["bufferViews"][0]["byteLength"] = 8
        with self.assertRaisesRegex(ValueError, "exceeds storage"):
            self.inspect(doc)

    def test_mapping_requires_disjoint_actual_clips(self):
        receipt = self.inspect(fixture())
        names = receipt["clips"]
        mapping = {"ground": names[:320], "takeoff": names[320:340], "flight": names[340:360], "landing": names[360:]}
        self.assertEqual(admit.bind_families(receipt, mapping)["families"], mapping)
        mapping["landing"] = mapping["flight"]
        with self.assertRaisesRegex(ValueError, "overlapping"):
            admit.bind_families(receipt, mapping)


if __name__ == "__main__":
    unittest.main()
