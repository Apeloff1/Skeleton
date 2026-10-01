from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_quality_control",
    ROOT / "scripts/check_p2_quality_control.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class P2QualityControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.control = json.loads(
            (ROOT / "machine/p2_quality_control.json").read_text(encoding="utf-8")
        )
        cls.master = json.loads(
            (ROOT / "machine/ai_master_plan.json").read_text(encoding="utf-8")
        )
        cls.engineering = json.loads(
            (ROOT / "machine/ai_engineering_pass.json").read_text(encoding="utf-8")
        )

    def validate(self, control) -> dict:
        return M.validate_payload(
            control,
            self.master,
            self.engineering,
            root=ROOT,
        )

    def test_current_control_is_valid(self) -> None:
        result = self.validate(copy.deepcopy(self.control))
        self.assertEqual(result["quality_dimensions"], 15)
        self.assertEqual(result["formal_targets"], 2)
        self.assertEqual(result["project_metrics"], 5)
        self.assertEqual(result["final_assembly_gates"], 6)

    def test_dimension_loss_fails_closed(self) -> None:
        control = copy.deepcopy(self.control)
        control["quality_vector"]["dimensions"].pop()
        with self.assertRaisesRegex(M.P2QualityControlError, "dimension coverage"):
            self.validate(control)

    def test_compensable_dimension_is_rejected(self) -> None:
        control = copy.deepcopy(self.control)
        control["quality_vector"]["dimensions"][0]["non_compensable"] = False
        with self.assertRaisesRegex(M.P2QualityControlError, "compensable"):
            self.validate(control)

    def test_weighted_score_key_is_rejected(self) -> None:
        control = copy.deepcopy(self.control)
        control["quality_vector"]["overall_score"] = 100
        with self.assertRaisesRegex(M.P2QualityControlError, "score is forbidden"):
            self.validate(control)

    def test_metric_completion_authority_cannot_be_added(self) -> None:
        control = copy.deepcopy(self.control)
        control["project_metrics"]["policy"]["completion_rule"] = "metrics decide completion"
        with self.assertRaisesRegex(M.P2QualityControlError, "completion authority"):
            self.validate(control)

    def test_final_digest_algorithm_is_pinned(self) -> None:
        control = copy.deepcopy(self.control)
        control["final_assembly"]["promotion_binding"]["digest_algorithm"] = "sha1"
        with self.assertRaisesRegex(M.P2QualityControlError, "digest algorithm"):
            self.validate(control)


if __name__ == "__main__":
    unittest.main()
