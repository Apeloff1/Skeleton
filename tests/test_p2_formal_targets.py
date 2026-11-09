from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from skeleton.quality.formal import FormalModelError, check_finite_state_model


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_p2_formal_targets",
    ROOT / "scripts" / "check_p2_formal_targets.py",
)
assert SPEC and SPEC.loader
FORMAL_TARGETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FORMAL_TARGETS)


class FormalModelTests(unittest.TestCase):
    def test_valid_model_passes(self) -> None:
        result = check_finite_state_model(
            states={"created", "running", "done", "failed"},
            transitions={
                "created": {"running", "failed"},
                "running": {"done", "failed"},
                "done": set(),
                "failed": set(),
            },
            terminals={"done", "failed"},
            initial="created",
        )
        self.assertEqual(result.state_count, 4)

    def test_terminal_resurrection_is_counterexample(self) -> None:
        with self.assertRaisesRegex(FormalModelError, "outgoing"):
            check_finite_state_model(
                states={"created", "done"},
                transitions={"created": {"done"}, "done": {"created"}},
                terminals={"done"},
                initial="created",
            )

    def test_unreachable_state_is_counterexample(self) -> None:
        with self.assertRaisesRegex(FormalModelError, "unreachable"):
            check_finite_state_model(
                states={"created", "done", "orphan"},
                transitions={
                    "created": {"done"},
                    "done": set(),
                    "orphan": {"done"},
                },
                terminals={"done"},
                initial="created",
            )

    def test_nonterminal_cycle_without_terminal_path_is_counterexample(self) -> None:
        with self.assertRaisesRegex(FormalModelError, "cannot reach a terminal"):
            check_finite_state_model(
                states={"created", "loop", "done"},
                transitions={
                    "created": {"loop", "done"},
                    "loop": {"loop"},
                    "done": set(),
                },
                terminals={"done"},
                initial="created",
            )

    def test_repository_formal_targets_pass_static_dispatch(self) -> None:
        result = FORMAL_TARGETS.validate(ROOT)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["target_count"], 2)

    def test_unknown_formal_module_is_rejected_without_dynamic_import(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="formal-target-dispatch-"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        paths = (
            "machine/p2_quality_control.json",
            "machine/ai_master_plan.json",
            "machine/state_machine_catalogue.json",
            "skeleton/testing/test_operation_runtime.py",
            "skeleton/testing/test_engine_execution_service.py",
            "skeleton/testing/test_engine_execution_coordinator.py",
            "skeleton/contracts/operation.py",
            "skeleton/contracts/ai_execution.py",
        )
        for relative in paths:
            src = ROOT / relative
            dst = temp / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        control_path = temp / "machine/p2_quality_control.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["formal_methods"]["targets"][0]["module"] = "attacker.plugin"
        control_path.write_text(json.dumps(control), encoding="utf-8")
        with self.assertRaisesRegex(
            FORMAL_TARGETS.FormalTargetError,
            "not an approved formal target",
        ):
            FORMAL_TARGETS.validate(temp)


if __name__ == "__main__":
    unittest.main()
