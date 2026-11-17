"""Synthetic rejection and complete-cohort tests; not collision clearance."""
import sys
from pathlib import Path
import tempfile
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import emerald_v5_anatomical_census as census


class AnatomicalCensusTests(unittest.TestCase):
    def setUp(self):
        # Torso x2, flight-near x2, head x1, tail x1.
        self.joints = np.zeros((6,4), dtype=np.uint16)
        self.joints[:,0] = [4, 4, 68, 79, 10, 38]
        self.weights = np.zeros((6,4), dtype="<f4")
        self.weights[:,0] = 1.
        self.faces = np.array([
            [0,1,2],  # torso-majority
            [2,3,4],  # wing-majority
            [1,2,4],  # three-way mixed; do NOT force classification
            [1,4,5],  # also three-way mixed
            [0,1,5],  # torso-majority
        ], dtype=np.uint32)

    def test_all_108_joints_have_unique_region(self):
        lookup = census.cohort_table()
        self.assertEqual(len(lookup),108)
        self.assertGreaterEqual(lookup.min(),0)
        self.assertEqual(lookup[68],lookup[79])
        self.assertNotEqual(lookup[79],lookup[80])
        self.assertNotEqual(lookup[68],lookup[4])
        self.assertNotEqual(lookup[67],lookup[68])
        self.assertNotEqual(lookup[91],lookup[92])

    def test_majority_and_three_way_mixed(self):
        cohort,counts = census.classify(self.weights,self.joints,self.faces)
        self.assertEqual(counts["torso"],2)
        self.assertEqual(counts["wing_flight_near"],1)
        self.assertEqual(counts["three_way_mixed"],2)
        self.assertEqual(len(cohort),5)
        self.assertEqual(int((cohort == -1).sum()),2)
        self.assertEqual(sum(counts.values()),5)

    def test_old_strict_coverage_distinct_from_new_classification(self):
        strict = census.prior_coverage(self.weights,self.joints,self.faces)
        self.assertEqual(strict["old_region_counts"]["wing_near"],0)
        self.assertEqual(strict["old_classified_triangles"],0)
        self.assertEqual(strict["old_unclassified_triangles"],len(self.faces))

    def test_reject_non_normalized_weights(self):
        bad = self.weights.copy()
        bad[0,0] = .7
        with self.assertRaisesRegex(ValueError,"unsafe skin weights"):
            census.classify(bad,self.joints,self.faces)

    def test_reject_negative_and_nonfinite_weights(self):
        for value in (-.001,float("nan"),float("inf")):
            bad=self.weights.copy()
            bad[0,0]=value
            with self.assertRaisesRegex(ValueError,"unsafe skin weights"):
                census.classify(bad,self.joints,self.faces)

    def test_reject_invalid_joint_and_face_ids(self):
        badj=self.joints.copy()
        badj[0,0]=108
        with self.assertRaisesRegex(ValueError,"unsafe skin weights"):
            census.classify(self.weights,badj,self.faces)
        badf=self.faces.copy()
        badf[0,0]=len(self.weights)
        with self.assertRaisesRegex(ValueError,"out-of-range"):
            census.classify(self.weights,self.joints,badf)

    def test_reject_fractional_joint_identifiers(self):
        with self.assertRaisesRegex(ValueError,"unsafe skin weights"):
            census.classify(self.weights,self.joints.astype(np.float32),self.faces)

    def test_every_new_worklist_pair_is_explicitly_unqualified(self):
        _,counts=census.classify(self.weights,self.joints,self.faces)
        worklist=census.worklist(counts)
        self.assertEqual(len(worklist),len(census.RISK_PAIRS)+1)
        self.assertTrue(all(x["status"].startswith("unqualified") for x in worklist))
        self.assertEqual(worklist[-1]["triangles_a"],2)

    def test_unknown_stage_is_rejected_before_io(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,"stage/version"):
                census.classify_model(Path(root)/"missing.glb","hoarder","v5")

    def test_forged_model_is_not_admitted(self):
        with tempfile.TemporaryDirectory() as root:
            model=Path(root)/"scholar.glb"
            model.write_bytes(b"glTF\\0\\0\\0\\0")
            with self.assertRaisesRegex(ValueError,"source SHA-256"):
                census.classify_model(model,"scholar","v5")

    def test_all_version_pins_inherit_exact_original_donor(self):
        self.assertEqual(census.DONOR_SHA,
                         "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a")
        self.assertEqual(len(census.PINNED),8)
        self.assertEqual(census.PINNED["pathfinder","v5"][0],114687832)
        self.assertEqual(census.PINNED["archivist","v5"][0],114810480)


if __name__=="__main__":
    unittest.main()
