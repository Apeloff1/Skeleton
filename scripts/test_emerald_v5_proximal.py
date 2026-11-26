"""Synthetic source controls for both full-density proximal wing candidates."""
import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import emerald_v5_proximal_wingfold as build
import verify_emerald_v5_proximal as proof

class ProximalWingTests(unittest.TestCase):
 def test_exact_stage_sources_and_outputs(self):
  self.assertEqual(set(build.SOURCES),{"pathfinder","archivist"})
  self.assertEqual([x[0] for x in build.OUTPUTS.values()],[114687832,114810480])
  self.assertEqual(build.ANGLES[68],('Y',-.30))
  self.assertEqual(build.ANGLES[79],('Z',.18))
  self.assertEqual(build.ANGLES[80],('Y',-.30))
  self.assertEqual(build.ANGLES[91],('Z',.18))

 def test_hamilton_local_y_and_z(self):
  source=np.array([[0,0,0,1],[0,0,1,0]],dtype=np.float32)
  y=build.corrected(source,"Y",-.30)
  self.assertTrue(np.allclose(y[0],[0,np.sin(-.15),0,np.cos(-.15)],atol=1e-7))
  z=build.corrected(source,"Z",.18)
  self.assertTrue(np.allclose(z[0],[0,0,np.sin(.09),np.cos(.09)],atol=1e-7))
  self.assertTrue(np.allclose(np.linalg.norm(y,axis=1),1,atol=1e-7))
  self.assertTrue(np.array_equal(source,np.array([[0,0,0,1],[0,0,1,0]],dtype=np.float32)))

 def test_unapproved_parameters_rejected(self):
  original=np.array([[0,0,0,1]],dtype=np.float32)
  for axis,angle in [("Y",.30),("Z",-.18),("X",.18),("Y",0),("Z",.35)]:
   with self.assertRaises(ValueError):build.corrected(original,axis,angle)
  for bad in [np.zeros((1,4)),np.array([1,0,0,0]),np.array([[0,float("nan"),0,1]])]:
   with self.assertRaises(ValueError):build.corrected(bad,'Y',-.30)

 def test_no_existing_output_overwrite(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);output=root/'candidate.glb';output.write_bytes(b'retain')
   with self.assertRaisesRegex(ValueError,'trusted empty output'):
    build.build('pathfinder',root/'no-source.glb',output)
   self.assertEqual(output.read_bytes(),b'retain')

 def test_missing_source_denied(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   with self.assertRaisesRegex(ValueError,'original source'):
    build.build('pathfinder',root/'missing.glb',root/'out.glb')

 def test_unqualified_candidate_cannot_fake_evidence(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   with self.assertRaisesRegex(ValueError,'source identity'):
    proof.check('archivist',root/'source.glb',root/'candidate.glb')

if __name__=="__main__":unittest.main()
