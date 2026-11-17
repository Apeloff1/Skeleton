"""Synthetic model/receipt trust-boundary tests; no physical acceptance."""
import copy
import json
from pathlib import Path
import unittest

import numpy as np

from emerald_v4_contact_geometry import (
 IncompleteAudit, contact_pairs, edge_face, point_tri2,
 segment_dist2, triangle_dist2, witness,
)
from emerald_v4_contact_scan import PAIRS, classify, source_pin, DONOR
from verify_emerald_v4_contact_receipt import verify

TRI=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
PIN=json.loads((Path(__file__).resolve().parents[1]/
    'frontend/src/features/Jeeves/companion/atelier/evolutionPin.json').read_text())

class GeometryTests(unittest.TestCase):
 def test_actual_distance_crossing_coplanar_and_parallel(self):
  passing=np.array([[.2,.2,-1],[.2,.2,1],[1.,.2,0.]])
  coplanar=np.array([[.2,.2,0],[1.5,.2,0],[.2,1.5,0]])
  above=TRI+np.array([0,0,.4])
  for b in (passing,coplanar,TRI):
   self.assertAlmostEqual(triangle_dist2(TRI,b),0)
   self.assertAlmostEqual(triangle_dist2(b,TRI),0)
  self.assertAlmostEqual(triangle_dist2(TRI,above),.16,places=9)

 def test_triangle_distance_scale_translation(self):
  b=TRI+np.array([0,0,.2])
  q=np.array([-13,12,2])
  d=triangle_dist2(TRI,b)
  self.assertAlmostEqual(triangle_dist2(TRI+q,b+q),d,places=9)
  self.assertAlmostEqual(triangle_dist2(TRI*3,b*3),d*9,places=9)

 def test_segment_degenerate_and_edge_piercing(self):
  z=np.zeros(3)
  self.assertAlmostEqual(segment_dist2(z,z,z,z),0)
  self.assertAlmostEqual(segment_dist2(z,z,np.array([0,1,0]),np.array([0,1,0])),1)
  self.assertTrue(edge_face(np.array([.2,.2,-1]),np.array([.2,.2,1]),TRI))
  self.assertFalse(edge_face(np.array([2,2,-1]),np.array([2,2,1]),TRI))
  self.assertAlmostEqual(point_tri2(np.array([.2,.2,.3]),TRI),.09)

 def test_bvh_can_find_extremely_long_triangle(self):
  large=np.array([[[0,0,0],[100,0,0],[0,100,0]]],float)
  small=np.array([[[98,0,0],[98,.5,0],[98.5,.5,0]]],float)
  self.assertEqual(contact_pairs(large,small,0)[0],[(0,0)])

 def test_margin_and_aabb_quota(self):
  a=TRI.reshape(1,3,3)
  b=(TRI+np.array([0,0,.005])).reshape(1,3,3)
  self.assertEqual(contact_pairs(a,b,.008)[0],[(0,0)])
  self.assertEqual(contact_pairs(a,b,.001)[0],[])
  with self.assertRaises(IncompleteAudit):
   contact_pairs(np.stack([TRI]*5),np.stack([TRI]*5),0,max_pairs=5)

 def test_centerline_contact_is_not_distal(self):
  a=TRI.reshape(1,3,3)
  report=witness(a,a,np.array([10]),np.array([25]),margin=0)
  self.assertEqual((report['root_centerline_contacts'],report['distal_contacts']),(1,0))
  self.assertEqual(report['contact_examples'][0]['faces'],[10,25])
  b=(TRI+np.array([0,0,.09])).reshape(1,3,3)
  self.assertEqual(witness(b,b,np.array([3]),np.array([4]),0)['distal_contacts'],1)

 def test_blended_faces_are_never_silently_qualified(self):
  faces=np.array([[0,1,2],[3,4,5],[0,2,4]])
  joints=np.array([[8,0,0,0],[8,0,0,0],[9,0,0,0],
                   [70,0,0,0],[71,0,0,0],[71,0,0,0]])
  weight=np.zeros((6,4));weight[:,0]=1
  groups,coverage=classify({'faces':faces,'joints':joints,'weights':weight})
  self.assertEqual(groups['head'].tolist(),[0])
  self.assertEqual(groups['wing_near'].tolist(),[1])
  self.assertEqual(coverage['unclassified_seam_and_other_triangles'],1)

class ReceiptTests(unittest.TestCase):
 def setUp(self):
  model=source_pin('hatchling')
  names=[a+'__'+b for a,b in PAIRS]
  self.receipt={
   'schema':'skeleton.emerald.sampled-triangle-contact.v2',
   'stage':'hatchling','sha256':model['sha256'],'bytes':model['bytes'],
   'donor_sha256':DONOR,'scan_complete':True,'poses':2,
   'clips':['ground-idle-1'],'fractions':[0,1],
   'triangle_coverage':{'classified_triangles':269919,
                        'unclassified_seam_and_other_triangles':449393},
   'sampled_contact_count':0,'unresolved_nonlinear_intervals':1,
   'continuous_collision_qualified':False,'all_morphs_qualified':False,
   'optional_equipment_enabled':False,'physical_rtx_verified':False,
   'artist_approved':False,'release_qualified':False,
   'evidence':[{'clip':'ground-idle-1','fraction':fraction,
                'contacts':{name:{'candidate_pairs':0,'contact_count':0,'near_count':0,
                                  'root_centerline_contacts':0,'distal_contacts':0}
                            for name in names}} for fraction in (0,1)],
  }

 def test_consistency_is_not_clearance_certificate(self):
  result=verify(self.receipt,PIN)
  self.assertTrue(result['sampled_zero_contact'])
  self.assertFalse(result['continuous_collision_qualified'])
  self.assertFalse(result['equipment_enabled'])
  self.assertFalse(result['release_qualified'])

 def test_fake_release_pass_rejected(self):
  self.receipt['release_qualified']=True
  with self.assertRaisesRegex(ValueError,'unjustified'):
   verify(self.receipt,PIN)

 def test_wrong_or_missing_pose_denied(self):
  self.receipt['evidence'].pop()
  with self.assertRaisesRegex(ValueError,'missing pose'):
   verify(self.receipt,PIN)

 def test_forged_aggregate_denied(self):
  self.receipt['sampled_contact_count']=100
  with self.assertRaisesRegex(ValueError,'aggregate'):
   verify(self.receipt,PIN)

 def test_true_contacts_preserved(self):
  witness=self.receipt['evidence'][0]['contacts']['wing_near__wing_far']
  witness['candidate_pairs']=1
  witness['contact_count']=1
  witness['root_centerline_contacts']=1
  self.receipt['sampled_contact_count']=1
  out=verify(self.receipt,PIN)
  self.assertEqual(out['sampled_contacts'],1)
  self.assertFalse(out['sampled_zero_contact'])

 def test_forged_negative_counts_denied(self):
  self.receipt['evidence'][0]['contacts']['wing_near__wing_far']['contact_count']=-1
  with self.assertRaisesRegex(ValueError,'invalid triangle'):
   verify(self.receipt,PIN)

 def test_omitted_pair_denied(self):
  del self.receipt['evidence'][0]['contacts']['wing_near__wing_far']
  with self.assertRaisesRegex(ValueError,'incomplete high-risk'):
   verify(self.receipt,PIN)

 def test_stale_asset_digest_denied(self):
  self.receipt['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'stale'):
   verify(self.receipt,PIN)

 def test_time_interval_omission_denied(self):
  self.receipt['unresolved_nonlinear_intervals']=0
  with self.assertRaisesRegex(ValueError,'silent omission'):
   verify(self.receipt,PIN)

 def test_missing_seam_coverage_denied(self):
  self.receipt['triangle_coverage']['unclassified_seam_and_other_triangles']=0
  with self.assertRaisesRegex(ValueError,'scope'):
   verify(self.receipt,PIN)

 def test_incomplete_timeout_denied(self):
  self.receipt['scan_complete']=False
  with self.assertRaisesRegex(ValueError,'incomplete'):
   verify(self.receipt,PIN)

if __name__=='__main__':unittest.main(verbosity=2)
