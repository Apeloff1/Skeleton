"""Negative-path tests use local synthetic bytes, never fabricate real clearance."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_emerald_v5_publication as pub


class BinaryCustodyTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.parts=self.root/"parts"
        self.parts.mkdir()
        raw=[b"alpha",b"beta",b"gamma",b"delta"]
        self.rows=[]
        for i,data in enumerate(raw):
            name="scholar.glb.part"+str(i+1).zfill(3)
            (self.parts/name).write_bytes(data)
            self.rows.append({
                "path":"assets/emerald/evolution-v5/scholar-wingfold-r1/"+name,
                "offset":sum(map(len,raw[:i])),"bytes":len(data),
                "sha256":hashlib.sha256(data).hexdigest()})
        self.fixture={"parts":self.rows,"bytes":sum(map(len,raw)),
                      "sha256":hashlib.sha256(b"".join(raw)).hexdigest()}
        p=patch.object(pub,"contract",return_value=self.fixture)
        p.start()
        self.addCleanup(p.stop)

    def test_measured_pins_are_explicit(self):
        self.assertEqual(pub.EXPECTED["bytes"],113305100)
        self.assertEqual(pub.EXPECTED["source_sha256"],"db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9")
        self.assertEqual(pub.EXPECTED["sha256"],"3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877")

    def test_private_assembly(self):
        path=self.root/"scholar.glb"
        result=pub.assemble(self.parts,path)
        self.assertTrue(result["assembled_exact_bytes"])
        self.assertFalse(result["release_qualified"])
        self.assertEqual(path.read_bytes(),b"alphabetagammadelta")

    def test_wrong_part_rejected_before_publication(self):
        (self.parts/"scholar.glb.part002").write_bytes(b"BEta")
        out=self.root/"scholar.glb"
        with self.assertRaisesRegex(ValueError,"mismatched"):
            pub.assemble(self.parts,out)
        self.assertFalse(out.exists())

    def test_correct_parts_but_wrong_whole_digest(self):
        self.fixture["sha256"]="0"*64
        out=self.root/"scholar.glb"
        with self.assertRaisesRegex(ValueError,"assembled asset"):
            pub.assemble(self.parts,out)
        self.assertFalse(out.exists())

    def test_no_overwrite(self):
        out=self.root/"scholar.glb"
        out.write_bytes(b"retain")
        with self.assertRaisesRegex(ValueError,"unused"):
            pub.assemble(self.parts,out)
        self.assertEqual(out.read_bytes(),b"retain")

    def test_symlink_slice_rejected(self):
        name=self.parts/"scholar.glb.part003"
        name.unlink()
        try:
            name.symlink_to(self.parts/"scholar.glb.part004")
        except OSError:
            self.skipTest("no symlink support")
        with self.assertRaisesRegex(ValueError,"mismatched"):
            pub.assemble(self.parts,self.root/"scholar.glb")

    def test_real_manifest_does_not_qualify_release(self):
        with self.subTest("measured metadata"):
            raw=pub.MANIFEST.read_bytes()
            self.assertIn(b'"automatic_adoption": false',raw)
            self.assertIn(b'"release_qualified": false',raw)


if __name__=="__main__":
    unittest.main()
