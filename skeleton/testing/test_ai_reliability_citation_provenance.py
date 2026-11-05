"""Exact real policy and bounded source corpus checks: citation_provenance."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.fixtures import run_domain
from skeleton.ai.runtime.operational_ai.reliability_fabric.states.citation_provenance import Evidence
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
from importlib import resources
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import strict_json

class CitationProvenanceTests(unittest.TestCase):
    def test_all_twenty_two_cases(self):
        result=run_domain("citation_provenance")
        self.assertEqual((result["accepted"],result["rejected"]),(2,20))
    def test_inprocess_receipt_ledger_has_no_silent_overwrite(self):
        root=resources.files("skeleton.ai.runtime.operational_ai.reliability_fabric").joinpath("cases","citation_provenance","00_valid.json")
        record=strict_json(root.read_bytes(),maximum=131072)["record"]
        ledger=Evidence(maximum=1)
        first=ledger.observe("r1",record)
        self.assertEqual(first["status"],"input-claim-validated-not-proven")
        with self.assertRaises(Rejected):
            ledger.observe("r1",record)
        with self.assertRaises(Rejected):
            ledger.observe("r2",record)
        ledger.forget("r1")
        self.assertIsNone(ledger.read("r1"))
if __name__=="__main__":
    unittest.main()
