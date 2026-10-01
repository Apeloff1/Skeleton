from __future__ import annotations

import unittest

from skeleton.quality.formal import FormalModelError, check_finite_state_model


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


if __name__ == "__main__":
    unittest.main()
