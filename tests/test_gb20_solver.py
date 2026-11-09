"""GB-20 constraint solver projection / satisfy / optimize."""

from __future__ import annotations

import unittest

from skeleton.spine.articulation import all_rom_ok, total_soft_penalty
from skeleton.spine.chain import default_chain, rebind_segments
from skeleton.spine.constraint_solver import (
    SolverResult,
    feasible,
    gradient_descent_rom,
    project_rom,
    random_feasible_perturbation,
    satisfy,
)
from skeleton.spine.optimize import (
    coordinate_descent,
    optimize_flexion_target,
    total_cost,
)
from skeleton.spine.segment import apply_relative_map
from skeleton.spine.vertebra import Pose6


class TestSolverProjection(unittest.TestCase):
    def test_project_clears_violation(self) -> None:
        chain = default_chain()
        seg = next(s for s in chain.segments if not s.locked)
        bad = rebind_segments(
            chain, apply_relative_map(chain.segments, {seg.label: Pose6(rx=400.0, ry=-400.0)})
        )
        self.assertFalse(all_rom_ok(bad.segments))
        fixed = project_rom(bad)
        self.assertTrue(all_rom_ok(fixed.segments))
        self.assertEqual(total_soft_penalty(fixed.segments), 0.0)

    def test_satisfy_alias(self) -> None:
        chain = default_chain()
        seg = next(s for s in chain.segments if not s.locked)
        bad = rebind_segments(
            chain, apply_relative_map(chain.segments, {seg.label: Pose6(rz=999.0)})
        )
        sat = satisfy(bad)
        self.assertTrue(all_rom_ok(sat.segments))

    def test_feasible_default(self) -> None:
        self.assertTrue(feasible(default_chain()))

    def test_gradient_descent_reduces_penalty(self) -> None:
        chain = default_chain()
        seg = next(s for s in chain.segments if not s.locked)
        bad = rebind_segments(
            chain, apply_relative_map(chain.segments, {seg.label: Pose6(rx=50.0)})
        )
        # may already be in or out of rom depending on region; force far
        bad = rebind_segments(
            chain, apply_relative_map(chain.segments, {seg.label: Pose6(rx=200.0)})
        )
        before = total_soft_penalty(bad.segments)
        result = gradient_descent_rom(bad, steps=30, lr=0.2)
        self.assertIsInstance(result, SolverResult)
        self.assertLessEqual(result.penalty_after, before + 1e-9)
        self.assertTrue(all_rom_ok(result.chain.segments))

    def test_random_feasible_perturbation(self) -> None:
        chain = default_chain()
        pert = random_feasible_perturbation(chain, scale=0.3, seed=7)
        self.assertTrue(all_rom_ok(pert.segments))
        self.assertTrue(feasible(pert))

    def test_idempotent_project_on_clean(self) -> None:
        chain = default_chain()
        once = project_rom(chain)
        twice = project_rom(once)
        self.assertTrue(all_rom_ok(once.segments))
        self.assertTrue(all_rom_ok(twice.segments))


class TestOptimize(unittest.TestCase):
    def test_total_cost_nonnegative(self) -> None:
        self.assertGreaterEqual(total_cost(default_chain()), 0.0)

    def test_coordinate_descent_runs(self) -> None:
        result = coordinate_descent(default_chain(), sweeps=2, delta=0.25)
        self.assertTrue(all_rom_ok(result.chain.segments))

    def test_optimize_flexion_target(self) -> None:
        result = optimize_flexion_target(default_chain(), target_sum_rx=20.0, steps=25)
        self.assertTrue(all_rom_ok(result.chain.segments))
        total_rx = sum(s.relative.rx for s in result.chain.segments)
        self.assertGreater(total_rx, 0.0)


if __name__ == "__main__":
    unittest.main()
