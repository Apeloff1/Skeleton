"""Negative assurance: no silent source admission or security-gate downgrades."""
import copy
import json
import unittest

from scripts.check_draft19_reconciliation import LEDGER, AdmissionError, validate


class Draft19LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(LEDGER.read_text(encoding="utf-8"))

    def bad(self, mutate):
        value = copy.deepcopy(self.data)
        mutate(value)
        with self.assertRaises(AdmissionError):
            validate(value)

    def test_all_19_are_held(self):
        result = validate(self.data)
        self.assertEqual((result["sources"], result["admitted"]), (19, 0))
        self.assertEqual(result["classes"], {"historical": 1, "overlap": 16, "quarantine": 1, "unwired": 1})
        self.assertFalse(result["remote_ci_verified"])

    def test_no_omitted_duplicate_or_unknown_donor(self):
        self.bad(lambda d: d["source_prs"].pop())
        self.bad(lambda d: d["source_prs"][1].__setitem__("number", 5069))
        self.bad(lambda d: d["source_prs"][0].__setitem__("number", 999999))

    def test_invalid_source_identity_denied(self):
        self.bad(lambda d: d["source_prs"][0].__setitem__("head_sha", "deadbeef"))
        self.bad(lambda d: d.__setitem__("baseline_head", "z" * 40))
        self.bad(lambda d: d["source_prs"][0].__setitem__("changed_paths", True))

    def test_security_holds_cannot_be_promoted(self):
        self.bad(lambda d: d.__setitem__("merge_approved", True))
        self.bad(lambda d: d.__setitem__("release_approved", True))
        self.bad(lambda d: d["source_prs"][0].__setitem__("source_admitted", True))
        self.bad(lambda d: d["source_prs"][0].__setitem__("release_approved", True))

    def test_quarantine_and_historical_classes_immutable(self):
        for number in (5022, 4991, 5038):
            def change(d, number=number):
                next(s for s in d["source_prs"] if s["number"] == number)["classification"] = "overlap"
            self.bad(change)

    def test_required_exact_head_gates_stay_in_force(self):
        self.bad(lambda d: d["required_gates"].remove("Malware Gate"))
        self.bad(lambda d: d["required_gates"].append("Workflow Input Security"))


if __name__ == "__main__":
    unittest.main()
