"""Reject inflated synthetic clearance receipts; consistency does not prove CCD."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_emerald_v5_contact_evidence as audit

class ContactEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.before=json.loads((audit.FOLDER/"sampled-contact-receipt.json").read_bytes())
        self.expanded=json.loads((audit.FOLDER/"expanded-contact-evidence.json").read_bytes())

    def test_consistent_record_keeps_held_claims(self):
        result=audit.verify(self.before,self.expanded)
        self.assertEqual(result["checked_pose_receipts"],31)
        self.assertEqual(result["observed_contacts"],0)
        self.assertFalse(result["continuous_collision_qualified"])
        self.assertFalse(result["independently_replayed_in_ci"])

    def test_fabricated_full_continuous_clearance_denied(self):
        self.expanded["full_continuous_collision_qualified"]=True
        with self.assertRaisesRegex(ValueError,"false continuous"):
            audit.verify(self.before,self.expanded)

    def test_extra_receipt_contacts_denied(self):
        self.expanded["poses"][0]["contacts"]=1
        with self.assertRaisesRegex(ValueError,"counts inconsistent"):
            audit.verify(self.before,self.expanded)

    def test_duplicate_pose_denied(self):
        self.expanded["poses"][1]=copy.deepcopy(self.expanded["poses"][0])
        with self.assertRaisesRegex(ValueError,"duplicated pose"):
            audit.verify(self.before,self.expanded)

    def test_coverage_inflation_denied(self):
        self.expanded["unclassified_triangles"]=0
        with self.assertRaisesRegex(ValueError,"anatomical coverage"):
            audit.verify(self.before,self.expanded)

    def test_falsely_approved_equipment_denied(self):
        self.before["equipment_enabled"]=True
        with self.assertRaisesRegex(ValueError,"false continuous"):
            audit.verify(self.before,self.expanded)

    def test_falsely_approved_release_denied(self):
        self.expanded["release_qualified"]=True
        with self.assertRaisesRegex(ValueError,"false-positive"):
            audit.verify(self.before,self.expanded)

if __name__=="__main__":unittest.main()
