from __future__ import annotations

import math
import unittest

from skeleton.jeeves.decision import policy
from skeleton.jeeves.decision import provenance
from skeleton.jeeves.decision import scoring


class DecisionRuleGenerationTests(unittest.TestCase):
    def assert_plane(self, module, kind_type, prefix: str, count: int) -> None:
        rules = module.RULES
        self.assertEqual(len(rules), count)
        self.assertEqual(rules[0].name, f"{prefix}_001")
        self.assertEqual(rules[-1].name, f"{prefix}_{count:03d}")

        # Preserve the original intended i % 5 kind cycle.
        self.assertIs(rules[0].kind, kind_type.SECONDARY)
        self.assertIs(rules[1].kind, kind_type.TERTIARY)
        self.assertIs(rules[2].kind, kind_type.BLOCKING)
        self.assertIs(rules[3].kind, kind_type.ADVISORY)
        self.assertIs(rules[4].kind, kind_type.PRIMARY)

        # Preserve the generated threshold sequence, including wrap at 100.
        self.assertEqual(rules[0].threshold, 0.01)
        self.assertEqual(rules[98].threshold, 0.99)
        self.assertEqual(rules[99].threshold, 0.0)
        self.assertEqual(rules[100].threshold, 0.01)

        self.assertEqual(rules[0].rationale, f"bounded {prefix} rule 1")
        self.assertEqual(
            sum(len(module.by_kind(kind)) for kind in kind_type),
            count,
        )
        self.assertEqual(len({rule.name for rule in rules}), count)

        with self.assertRaises(ValueError):
            module.active(True)
        with self.assertRaises(ValueError):
            module.active(math.nan)
        with self.assertRaises(ValueError):
            module.active(math.inf)

    def test_policy_rules(self) -> None:
        self.assert_plane(policy, policy.PolicyKind, "policy", 240)

    def test_provenance_rules(self) -> None:
        self.assert_plane(provenance, provenance.ProvenanceKind, "provenance", 180)

    def test_scoring_rules(self) -> None:
        self.assert_plane(scoring, scoring.ScoringKind, "scoring", 220)


if __name__ == "__main__":
    unittest.main()
