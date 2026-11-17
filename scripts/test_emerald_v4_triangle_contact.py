"""Synthetic boundary tests only; never a real GLB/physical collision pass."""
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from emerald_v4_contact_geometry import (
    IncompleteAudit, contact_pairs, edge_face, point_tri2, segment_dist2,
    triangle_dist2, witness,
)
from emerald_v4_contact_scan import GLB, PAIRS, classify, source_pin, DONOR

TRI=np.asarray([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])

class ContactGeometryTests(unittest.TestCase):
 def test_crossing_and_coplanar_contacts(self):
  crossing=np.asarray([[.2,.2,-1],[.2,.2,1],[1,.2,0.]])
  inside=np.asarray([[.2,.2,0],[1.5,.2,0],[.2,1.5,0]])
  for b in [TRI,crossing,inside]:
   self.assertAlmostEqual(triangle_dist2(TRI,b),0,places=9)
   self.assertAlmostEqual(triangle_dist2(b,TRI),0,places=9)

 def test_parallel_and_perpendicular_separation(self):
  b=TRI.copy();b[:,2]=.4
  self.assertAlmostEqual(triangle_dist2(TRI,b),.16,places=9)
  self.assertAlmostEqual(triangle_dist2(TRI,b),triangle_dist2(b,TRI),places=9)
  distant=TRI.copy();distant[:,0]+=2;distant[:,1]+=2
  self.assertAlmostEqual(triangle_dist2(TRI,distant),4.5,places=9)

 def test_edge_face_pierce_and_miss(self):
  self.assertTrue(edge_face(np.array([.2,.2,-1]),np.array([.2,.2,1]),TRI))
  self.assertFalse(edge_face(np.array([2.,2.,-1]),np.array([2.,2.,1]),TRI))

 def test_point_and_degenerate_segment(self):
  self.assertAlmostEqual(point_tri2(np.array([.2,.2,.3]),TRI),.09)
  z=np.zeros(3)
  self.assertAlmostEqual(segment_dist2(z,z,z,z),0)
  self.assertAlmostEqual(segment_dist2(z,z,np.array([0,1,0]),np.array([0,1,0])),1)

 def test_scale_and_translation_invariance(self):
  b=TRI.copy();b[:,2]=.33
  amount=triangle_dist2(TRI,b)
  offset=np.array([9,-21,13])
  self.assertAlmostEqual(triangle_dist2(TRI+offset,b+offset),amount,places=9)
  self.assertAlmostEqual(triangle_dist2(TRI*2,b*2),amount*4,places=9)

 def test_aabb_bvh_does_not_drop_long_edges(self):
  big=np.asarray([[[0,0,0],[100,0,0],[0,100,0]]],dtype=float)
  small=np.asarray([[[98,0,0],[98,.5,0],[98.5,.5,0]]],dtype=float)
  self.assertEqual(contact_pairs(big,small,0)[0],[(0,0)])

 def test_far_and_margin_pairs(self):
  a=TRI.reshape(1,3,3)
  b=(TRI+np.array([0,0,.005])).reshape(1,3,3)
  self.assertEqual(contact_pairs(a,b,.008)[0],[(0,0)])
  self.assertEqual(contact_pairs(a,b,.001)[0],[])
  self.assertEqual(contact_pairs(a,b+100,0)[0],[])

 def test_budget_and_timeout_are_not_passes(self):
  a=np.stack([TRI]*5)
  with self.assertRaises(IncompleteAudit):
   contact_pairs(a,a,0,max_pairs=5)
  with self.assertRaises(IncompleteAudit):
   contact_pairs(a,a,0,deadline=0.)

 def test_centerline_vs_distal_witnesses(self):
  one=TRI.reshape(1,3,3)
  root=witness(one,one,np.array([2]),np.array([7]),0)
  self.assertEqual(root['root_centerline_contacts'],1)
  self.assertEqual(root['distal_contacts'],0)
  shifted=(TRI+np.array([0,0,.09])).reshape(1,3,3)
  far=witness(shifted,shifted,np.array([3]),np.array([9]),0)
  self.assertEqual(far['root_centerline_contacts'],0)
  self.assertEqual(far['distal_contacts'],1)
  self.assertEqual(root['contact_examples'][0]['faces'],[2,7])

 def test_reject_bad_shape(self):
  with self.assertRaises(ValueError):
   contact_pairs(np.ones((3,3)),TRI.reshape(1,3,3))

class ScannerContractTests(unittest.TestCase):
 def test_original_donor_and_disabled_equipment_are_immutable(self):
  p=source_pin('hatchling')
  self.assertEqual(p['joints'],108)
  self.assertEqual(p['clips'],381)
  self.assertFalse(p['equipmentEnabled'])
  self.assertEqual(DONOR,'c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a')
  self.assertEqual(len(PAIRS),7)

 def test_bad_model_digest_and_size_fail_before_decode(self):
  with tempfile.TemporaryDirectory() as folder:
   file=Path(folder)/'hatchling.glb'
   file.write_bytes(b'not a glb')
   p=source_pin('hatchling')
   with self.assertRaisesRegex(ValueError,'model byte identity'):
    GLB(file,p,'hatchling')

 def test_blended_joint_seams_are_explicitly_unclassified(self):
  positions=np.zeros((6,3))
  faces=np.array([[0,1,2],[3,4,5],[0,2,4]])
  joints=np.asarray([[8,0,0,0],[8,0,0,0],[9,0,0,0],
                     [70,0,0,0],[71,0,0,0],[71,0,0,0]])
  weights=np.zeros((6,4));weights[:,0]=1
  groups,census=classify({'faces':faces,'joints':joints,'weights':weights})
  self.assertEqual(groups['head'].tolist(),[0])
  self.assertEqual(groups['wing_near'].tolist(),[1])
  self.assertEqual(census['unclassified_seam_and_other_triangles'],1)

 def test_unknown_stage(self):
  with self.assertRaisesRegex(ValueError,'unknown'):
   source_pin('untrusted')

if __name__=='__main__':
 unittest.main(verbosity=2)
