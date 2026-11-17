"""Source-only Scholar corrective quaternion and custody regression suite.

Do not mistake these tests for full GLB, software-render, device, Unreal,
continuous mesh CCD, artistic acceptance, or release qualification.
"""
from __future__ import annotations
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

import patch_emerald_scholar_wingfold as patcher

class ScholarQuaternionTests(unittest.TestCase):
    def test_identity_post_rotate_local_z(self):
        x=np.array([[0.,0.,0.,1.]],dtype='<f4')
        value=patcher.quat_correct(x,.18)[0]
        np.testing.assert_allclose(value,[0,0,math.sin(.09),math.cos(.09)],rtol=2e-7,atol=2e-7)

    def test_equivalent_negative_quaternion(self):
        a=np.array([[0,0,0,1],[0,0,0,-1]],dtype='<f4')
        b=patcher.quat_correct(a,.18)
        np.testing.assert_allclose(b[0],-b[1],atol=1e-6)

    def test_inverse_angle_roundtrip(self):
        x=np.asarray([[.22,.17,.12,.945],[.2,.4,.0,.8944272]],dtype='<f4')
        x/=np.linalg.norm(x,axis=1)[:,None]
        v=patcher.quat_correct(x,.18)
        r=patcher.quat_correct(v,-.18)
        np.testing.assert_allclose(x,r,atol=1e-6)

    def test_non_unit_rejected(self):
        with self.assertRaisesRegex(ValueError,'nonunit'):
            patcher.quat_correct(np.array([[0,0,0,3]],dtype='<f4'),.18)

    def test_nan_rejected(self):
        with self.assertRaisesRegex(ValueError,'shape'):
            patcher.quat_correct(np.array([[0,0,float('nan'),1]],dtype='<f4'),.18)

    def test_wrong_shape_rejected(self):
        with self.assertRaisesRegex(ValueError,'shape'):
            patcher.quat_correct(np.zeros((3,3),dtype='<f4'),.18)

    def test_original_quaternions_not_mutated(self):
        x=np.array([[0,0,0,1]],dtype='<f4')
        before=x.copy()
        patcher.quat_correct(x,.18)
        np.testing.assert_array_equal(x,before)

    def test_output_is_normalized_float32(self):
        x=np.array([[0.0,.70710677,0.0,.70710677]],dtype='<f4')
        out=patcher.quat_correct(x,.18)
        self.assertEqual(out.dtype,np.dtype('<f4'))
        self.assertTrue(out.flags.c_contiguous)
        np.testing.assert_allclose(np.linalg.norm(out,axis=1),1,atol=2e-7)

    def test_protected_donor_and_stage_identity(self):
        self.assertEqual(patcher.DONOR_SHA,
            'c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a')
        self.assertEqual(patcher.SCHOLAR_V4_SHA,
            'db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9')
        self.assertEqual(patcher.TARGET_RIG_IDS,(79,91))
        self.assertEqual(patcher.SCHOLAR_V4_BYTES,112509064)

    def test_reject_wrong_input_before_patching(self):
        with tempfile.TemporaryDirectory() as temp:
            input_path=Path(temp)/'scholar.glb'
            input_path.write_bytes(b'not trusted')
            with self.assertRaisesRegex(ValueError,'wrong original Scholar'):
                patcher.read_source(input_path)

    def test_reject_untrusted_angle(self):
        for angle in (0,.5,float('nan'),float('inf'),-.18):
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(ValueError,'corrective angle'):
                    patcher.build(Path(temp)/'source.glb',Path(temp)/'new.glb',angle)

    def test_reject_existing_output_even_before_source_open(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'output.glb').write_bytes(b'protected')
            with self.assertRaisesRegex(ValueError,'trusted parent'):
                patcher.build(directory/'missing.glb',directory/'output.glb',.18)
            self.assertEqual((directory/'output.glb').read_bytes(),b'protected')

if __name__=='__main__':
    unittest.main(verbosity=2)
