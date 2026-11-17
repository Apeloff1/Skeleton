"""Independent synthetic checks for V6 crossfade math and fail-closed source pin."""
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
import emerald_v6_crossfade_screen as mix


class V6CrossfadeRegression(unittest.TestCase):
    def test_unity_and_180_degree_quaternion_blends(self):
        left=np.array([[0,0,0,1],[0,0,1,0],[1,0,0,0]],dtype="<f4")
        right=np.array([[0,0,1,0],[0,0,0,1],[0,1,0,0]],dtype="<f4")
        for w in (0,.125,.25,.5,.75,.875,1):
            actual=mix.slerp_rows(left,right,w)
            np.testing.assert_allclose(np.linalg.norm(actual,axis=1),1,atol=1e-7)
        np.testing.assert_allclose(mix.slerp_rows(left,right,0),left,atol=1e-7)
        np.testing.assert_allclose(mix.slerp_rows(left,right,1),right,atol=1e-7)

    def test_identical_and_antipodal_rotations_stay_equivalent(self):
        q=np.array([[0.,0.,0.,1.],[0.,0.70710678,0.,0.70710678]],dtype="<f4")
        for w in (0,.01,.5,.99,1):
            np.testing.assert_allclose(mix.slerp_rows(q,q,w),q,atol=1e-7)
            actual=mix.slerp_rows(q,-q,w)
            np.testing.assert_allclose(
                np.abs((actual*q).sum(axis=1)),1,atol=1e-7)

    def test_nonfinite_and_invalid_mixer_arguments_denied(self):
        q=np.array([[0.,0.,0.,1.]],dtype="<f4")
        for w in (-.1,1.1,float("nan"),float("inf")):
            with self.assertRaisesRegex(ValueError,"unsafe quaternion"):
                mix.slerp_rows(q,q,w)
        for bad in (
            np.array([[0.,0.,0.,0.]],dtype="<f4"),
            np.array([[0.,0.,float("nan"),1.]],dtype="<f4")):
            with self.assertRaises(ValueError):
                mix.slerp_rows(q,bad,.5)
        with self.assertRaisesRegex(ValueError,"unsafe quaternion"):
            mix.slerp_rows(q,np.ones((1,3)),.5)

    def test_preserves_runtime_crossfade_policy_and_no_art_approval(self):
        self.assertEqual(mix.CROSSFADE_SECONDS,.22)
        self.assertEqual(mix.MARGIN,.008)
        self.assertEqual(len(mix.TRANSITIONS),6)
        self.assertEqual(mix.DONOR,
            "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a")
        self.assertEqual(mix.MODELS["pathfinder"][0],114693124)
        self.assertEqual(mix.MODELS["archivist"][0],114815776)
        self.assertIn(("orbit-01","landing-1"),mix.TRANSITIONS)

    def test_refuse_unreviewed_geometry_tool_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in mix.TOOLS:
                (root/name).write_text("print('mischief')")
            with self.assertRaisesRegex(ValueError,"reviewed contact"):
                mix.vetted_tools(root)

    def test_aabb_screen_empty_means_unqualified(self):
        # Two face pools share a vertex; the seam is a candidate and is
        # never promoted to independently safe contact by this helper.
        positions=np.array([
            [0.,0.,0.],[1.,0.,0.],[0.,1.,0.],
            [-1.,0.,0.],[0.,-1.,0.]],dtype=np.float64)
        faces=np.array([[0,1,2],[0,3,4]],dtype=np.int32)
        groups={name:np.array([],dtype=np.int32)
                for pair in mix.PAIRS for name in pair}
        groups["wing_primary_far"]=np.array([0],dtype=np.int32)
        groups["torso"]=np.array([1],dtype=np.int32)
        g={"positions":positions,"faces":faces}
        class Auditor:
            @staticmethod
            def broadphase_pairs(a,b,margin,max_candidates):
                return ([(0,0)],1) if len(a) and len(b) else ([],0)
        class Seam:
            @staticmethod
            def distances_at_pose_and_bind(a,b,resta,restb,pairs):
                return np.array([0.]),np.array([0.])
        from unittest.mock import patch
        with patch.object(mix.time,"monotonic",return_value=0.):
            result=mix.contact_check(positions,g,groups,Auditor,Seam,1.)
        self.assertEqual(result["shared_index_bind_seam_candidates"],1)
        self.assertEqual(result["new_independent_contact_pairs"],0)

    def test_nonweld_new_contact_is_not_suppressed(self):
        positions=np.array([
            [0.,0.,0.],[1.,0.,0.],[0.,1.,0.],
            [0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],dtype=np.float64)
        faces=np.array([[0,1,2],[3,4,5]],dtype=np.int32)
        groups={name:np.array([],dtype=np.int32)
                for pair in mix.PAIRS for name in pair}
        groups["wing_primary_far"]=np.array([0],dtype=np.int32)
        groups["torso"]=np.array([1],dtype=np.int32)
        g={"positions":positions,"faces":faces}
        class Auditor:
            @staticmethod
            def broadphase_pairs(a,b,margin,max_candidates):
                return ([(0,0)],1) if len(a) and len(b) else ([],0)
        class Seam:
            @staticmethod
            def distances_at_pose_and_bind(a,b,resta,restb,pairs):
                return np.array([0.]),np.array([.01])
        from unittest.mock import patch
        with patch.object(mix.time,"monotonic",return_value=0.):
            result=mix.contact_check(positions,g,groups,Auditor,Seam,1.)
        self.assertEqual(result["new_independent_contact_pairs"],1)
        self.assertEqual(result["shared_index_bind_seam_candidates"],0)


if __name__=="__main__":
    unittest.main()
