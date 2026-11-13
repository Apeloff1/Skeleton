"""Source-backed device_probe contract, 20 adversarial inputs and ledger discipline."""
import unittest
from importlib import resources
from skeleton.ai.runtime.operational_ai.reliability_fabric.fixtures import run_domain
from skeleton.ai.runtime.operational_ai.reliability_fabric.states.device_probe import Evidence
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected,strict_json
class DeviceProbeTest(unittest.TestCase):
    def test_source_casebook(self):
        row=run_domain("device_probe")
        self.assertEqual((row["cases"],row["accepted"],row["rejected"]),(22,2,20))
    def test_bounded_receipt_ledger(self):
        entry=resources.files("skeleton.ai.runtime.operational_ai.reliability_fabric").joinpath("cases","device_probe","00_valid.json")
        record=strict_json(entry.read_bytes(),maximum=131072)["record"]
        ledger=Evidence(maximum=1)
        self.assertEqual(ledger.observe("first",record)["status"],"input-claim-validated-not-proven")
        with self.assertRaises(Rejected):ledger.observe("first",record)
        with self.assertRaises(Rejected):ledger.observe("second",record)
        ledger.forget("first")
        self.assertIsNone(ledger.read("first"))
if __name__=="__main__":
    unittest.main()
