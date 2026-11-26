"""Synthetic correction and custody regression tests. Not physical clearance."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emerald_v5_scholar_wingfold as build
import verify_emerald_v5_scholar as verify


class ScholarWingfoldTests(unittest.TestCase):
    def test_local_z_quaternion_composition(self):
        original=np.array([[0,0,0,1],[0,0,1,0],[1,0,0,0]],dtype="<f4")
        result=build.corrected_quaternions(original)
        s=np.sin(.18/2);c=np.cos(.18/2)
        np.testing.assert_allclose(result[0],[0,0,s,c],rtol=0,atol=4e-8)
        np.testing.assert_allclose(result[1],[0,0,c,-s],rtol=0,atol=4e-8)
        np.testing.assert_allclose(np.linalg.norm(result,axis=1),1,rtol=0,atol=3e-8)
        np.testing.assert_array_equal(original,np.array([[0,0,0,1],[0,0,1,0],[1,0,0,0]],dtype="<f4"))

    def test_rotation_rejects_malformed_input(self):
        for bad in (np.array([]),np.zeros((3,4)),np.ones((1,3)),
                    np.array([[0,0,float("nan"),1]],dtype=np.float32)):
            with self.assertRaises(ValueError):
                build.corrected_quaternions(bad)

    def test_only_bounded_reviewed_angle(self):
        q=np.array([[0,0,0,1]],dtype=np.float32)
        for angle in (float("nan"),0,.01,.36,1):
            with self.assertRaises(ValueError):
                build.corrected_quaternions(q,angle)

    def test_original_source_absent_fails(self):
        with tempfile.TemporaryDirectory() as name:
            out=Path(name)/"model.glb"
            with self.assertRaises(ValueError):
                build.build(Path(name)/"not-an-original.glb",out)
            self.assertFalse(out.exists())

    def test_source_pin_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as name:
            src=Path(name)/"scholar.glb"
            src.write_bytes(b"not the original")
            with self.assertRaisesRegex(ValueError,"identity"):
                build.parse_model(src)

    def test_existing_output_never_replaced(self):
        with tempfile.TemporaryDirectory() as name:
            src=Path(name)/"model.glb"
            out=Path(name)/"candidate.glb"
            out.write_bytes(b"retain")
            with self.assertRaisesRegex(ValueError,"existing trusted destination"):
                build.build(src,out)
            self.assertEqual(out.read_bytes(),b"retain")

    def test_input_pins_and_qualification_holds(self):
        self.assertEqual(build.SOURCE_BYTES,112509064)
        self.assertEqual(build.OUTPUT_BYTES,113305100)
        self.assertEqual(build.TARGET_SKIN_JOINTS,(79,91))
        self.assertEqual(build.CLIP_COUNT,380)
        self.assertEqual(build.SOURCE_SHA,"db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9")
        self.assertEqual(build.OUTPUT_SHA,"3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877")

    def test_verifier_rejects_missing_candidate(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError,"candidate identity"):
                verify.verify(Path(name)/"source.glb",Path(name)/"candidate.glb")


if __name__=="__main__":
    unittest.main()
