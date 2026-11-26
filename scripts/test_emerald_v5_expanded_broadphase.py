"""Synthetic AABB math and hostile receipt regression; no simulated physical safety."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import emerald_v5_expanded_broadphase as aabb
import check_emerald_v5_expanded_bounds as evidence

class BroadphaseTests(unittest.TestCase):
 def test_axis_aligned_global_lower_bound(self):
  A=(np.array([0.,0.,0.]),np.array([1.,1.,1.]))
  B=(np.array([3.,0.,0.]),np.array([4.,1.,1.]))
  self.assertAlmostEqual(aabb.pair_lower_bound(A,B),2)
  self.assertAlmostEqual(aabb.pair_lower_bound(A,(np.array([.5,0.,0.]),np.array([2.,2.,2.]))),0)
  self.assertAlmostEqual(aabb.pair_lower_bound(A,(np.array([1.006,0.,0.]),np.array([2.,1.,1.]))),.006)

 def test_do_not_clear_boxes_within_contact_margin(self):
  A=(np.array([0.,0.,0.]),np.array([1.,1.,1.]))
  names={n for p in aabb.RISK_PAIRS for n in p}
  bounds={n:(np.array([2.,0.,0.]),np.array([3.,1.,1.])) for n in names}
  bounds["torso"]=A
  rows=aabb.screen(bounds)
  self.assertEqual(len(rows),19)
  self.assertEqual(next(x for x in rows if x["pair"]=="wing_flight_near__torso")["status"],"separated-at-pose")
  bounds["wing_flight_near"]=(np.array([1.004,0.,0.]),np.array([2.,1.,1.]))
  rows=aabb.screen(bounds)
  self.assertEqual(next(x for x in rows if x["pair"]=="wing_flight_near__torso")["status"],"overlap-needs-triangle-test")

 def test_empty_region_is_not_safe(self):
  names={n for p in aabb.RISK_PAIRS for n in p}
  bounds={n:(np.zeros(3),np.ones(3)) for n in names}
  bounds["wing_primary_near"]=None
  row=next(x for x in aabb.screen(bounds) if x["pair"]=="wing_primary_near__torso")
  self.assertEqual(row["status"],"empty-unqualified")
  self.assertIsNone(row["gap_lower_bound_m"])

 def test_invalid_numeric_bounds_denied(self):
  A=(np.zeros(3),np.ones(3))
  bad=(np.array([float("nan"),0,0]),np.ones(3))
  with self.assertRaisesRegex(ValueError,"bounds"):
   aabb.pair_lower_bound(A,bad)

 def test_unreviewed_tool_denied(self):
  with tempfile.TemporaryDirectory() as directory:
   x=Path(directory)/"contact_audit.py"
   x.write_text("pretend to pass every contact\\n")
   with self.assertRaisesRegex(ValueError,"trusted original"):
    aabb.vetted_auditor(x)

 def test_bad_clearance_margin_denied(self):
  with self.assertRaisesRegex(ValueError,"margin"):
   aabb.screen({},float("nan"))

class EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.record=json.loads(evidence.RECEIPT.read_bytes())
 def test_actual_record_preserves_missing_evidence(self):
  out=evidence.verify(self.record)
  self.assertEqual(out["anatomical_pair_instances"],266)
  self.assertEqual(out["overlap_unresolved"],176)
  self.assertFalse(out["continuous_collision_qualified"])
  self.assertFalse(out["models_replayed_by_source_only_ci"])
 def test_wrong_model_hash_denied(self):
  self.record["model_sources"][1]["sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"SHA differs"):
   evidence.verify(self.record)
 def test_missing_pose_denied(self):
  self.record["compressed_pair_states"].pop()
  with self.assertRaisesRegex(ValueError,"missing exported"):
   evidence.verify(self.record)
 def test_forged_separation_denied(self):
  self.record["compressed_pair_states"][0]["codes"]="S"*19
  with self.assertRaisesRegex(ValueError,"pair evidence changed"):
   evidence.verify(self.record)
 def test_empty_group_promoted_to_safe_denied(self):
  self.record["compressed_pair_states"][0]["codes"]=self.record["compressed_pair_states"][0]["codes"].replace("E","S")
  with self.assertRaisesRegex(ValueError,"pair evidence changed"):
   evidence.verify(self.record)
 def test_contrived_full_ccd_denied(self):
  for field in ("all_intervals_qualified","full_triangle_narrowphase_completed",
                "continuous_collision_qualified","equipment_enabled",
                "artist_approved","physical_rtx_verified","release_qualified"):
   row=copy.deepcopy(self.record);row[field]=True
   with self.assertRaisesRegex(ValueError,"attempt to certify"):
    evidence.verify(row)

if __name__=="__main__":unittest.main()
