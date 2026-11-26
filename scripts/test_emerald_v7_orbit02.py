"""Synthetic negative-path V7 tests. They do not substitute for exact GLB replay."""
from __future__ import annotations
import math,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import emerald_v7_orbit02 as v7
import verify_emerald_v7_orbit02 as byteproof

class V7Orbit02Tests(unittest.TestCase):
 def test_exact_160_quaternion_source_correction(self):
  q=np.zeros((160,4),dtype='<f4')
  q[:,3]=1.
  src=q.copy()
  fixed=v7.post_y(q)
  self.assertEqual(fixed.shape,(160,4))
  np.testing.assert_allclose(fixed[:,1],math.sin(.09),atol=2e-8)
  np.testing.assert_allclose(fixed[:,3],math.cos(.09),atol=4e-8)
  np.testing.assert_allclose(np.linalg.norm(fixed,axis=1),1,atol=1e-7)
  np.testing.assert_array_equal(q,src)

 def test_nontrivial_quaternion_order(self):
  q=np.tile([0.,0.,1.,0.],(160,1)).astype('<f4')
  corrected=v7.post_y(q)
  np.testing.assert_allclose(corrected[:,0],-math.sin(.09),atol=1e-7)
  np.testing.assert_allclose(corrected[:,2],math.cos(.09),atol=1e-7)

 def test_reject_missing_or_nonunit_quaternion_tracks(self):
  bad=[
   np.zeros((160,4),dtype=np.float32),
   np.ones((159,4),dtype=np.float32),
   np.ones((160,3),dtype=np.float32),
   np.array([1,0,0,0],dtype=np.float32),
  ]
  for item in bad:
   with self.assertRaises(ValueError):v7.post_y(item)
  q=np.zeros((160,4),dtype=np.float32);q[:,3]=1
  q[2,0]=float('nan')
  with self.assertRaises(ValueError):v7.post_y(q)

 def test_pins_are_immutable_and_nonhoarder(self):
  self.assertEqual(set(v7.SOURCES),{"pathfinder","archivist"})
  self.assertEqual(v7.OUTPUTS["pathfinder"],(114696520,"27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade"))
  self.assertEqual(v7.OUTPUTS["archivist"],(114819168,"f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf"))
  self.assertEqual(v7.TARGET_CLIP,"orbit-02")
  self.assertEqual(v7.ROOT_JOINT,34)
  self.assertEqual(v7.ANGLE,.18)
  self.assertEqual(v7.DONOR,"c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a")

 def test_missing_exact_original_v6_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root)
   output=root/"new.glb"
   with self.assertRaisesRegex(ValueError,"wrong exact V6"):
    v7.export("pathfinder",root/"missing.glb",output)
   self.assertFalse(output.exists())

 def test_existing_binary_never_overwritten(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root)
   output=root/"new.glb";output.write_bytes(b"existing")
   with self.assertRaisesRegex(ValueError,"unused destination"):
    v7.export("archivist",root/"missing.glb",output)
   self.assertEqual(output.read_bytes(),b"existing")

 def test_unknown_stage_cannot_repin_original(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root)
   with self.assertRaisesRegex(ValueError,"unqualified"):
    v7.export("hoarder",root/"missing.glb",root/"new.glb")
   with self.assertRaisesRegex(ValueError,"unknown"):
    byteproof.verify("hoarder",root/"missing.glb",root/"new.glb")

 def test_independent_verifier_fails_without_both_real_glbs(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root)
   with self.assertRaisesRegex(ValueError,"missing or linked original"):
    byteproof.verify("pathfinder",root/"wrong.glb",root/"wrong2.glb")

if __name__=="__main__":unittest.main()
