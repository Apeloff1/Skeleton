"""Source-backed release_qualification contract, 20 adversarial inputs and ledger discipline."""
import unittest
from importlib import resources
from skeleton.ai.runtime.operational_ai.reliability_fabric.fixtures import run_domain
from skeleton.ai.runtime.operational_ai.reliability_fabric.states.release_qualification import Evidence
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected,strict_json
class ReleaseQualificationTest(unittest.TestCase):
    def test_source_casebook(self):
        row=run_domain("release_qualification")
        self.assertEqual((row["cases"],row["accepted"],row["rejected"]),(22,2,20))
    def test_bounded_receipt_ledger(self):
        entry=resources.files("skeleton.ai.runtime.operational_ai.reliability_fabric").joinpath("cases","release_qualification","00_valid.json")
        record=strict_json(entry.read_bytes(),maximum=131072)["record"]
        ledger=Evidence(maximum=1)
        self.assertEqual(ledger.observe("first",record)["status"],"input-claim-validated-not-proven")
        with self.assertRaises(Rejected):ledger.observe("first",record)
        with self.assertRaises(Rejected):ledger.observe("second",record)
        ledger.forget("first")
        self.assertIsNone(ledger.read("first"))
if __name__=="__main__":
    unittest.main()
