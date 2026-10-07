"""GB-20 kinematics determinism and geometry."""

from __future__ import annotations

import unittest

from skeleton.spine.chain import default_chain
from skeleton.spine.kinematics import (
    chord_length_mm,
    end_effector,
    forward_frames,
    jacobian_numeric,
    path_length_mm,
    stack_height_error,
)
from skeleton.spine.law import VERTEBRA_N
from skeleton.spine.posture import build_posture


class TestKinematicsDeterminism(unittest.TestCase):
    def test_forward_frames_stable(self) -> None:
        chain = default_chain()
        a = forward_frames(chain)
        b = forward_frames(chain)
        self.assertEqual(len(a), VERTEBRA_N)
        for fa, fb in zip(a, b):
            self.assertEqual((fa.x, fa.y, fa.z, fa.roll, fa.pitch, fa.yaw),
                             (fb.x, fb.y, fb.z, fb.roll, fb.pitch, fb.yaw))

    def test_end_effector_matches_last_frame(self) -> None:
        chain = default_chain()
        frames = forward_frames(chain)
        tip = end_effector(chain)
        last = frames[-1]
        self.assertAlmostEqual(tip.x, last.x)
        self.assertAlmostEqual(tip.y, last.y)
        self.assertAlmostEqual(tip.z, last.z)

    def test_path_and_chord_neutral(self) -> None:
        chain = default_chain()
        path = path_length_mm(chain)
        chord = chord_length_mm(chain)
        self.assertGreater(path, 0.0)
        self.assertGreater(chord, 0.0)
        # neutral upright: path ≈ chord
        self.assertAlmostEqual(path, chord, places=3)

    def test_flexion_shortens_chord(self) -> None:
        neutral = default_chain()
        flexed = build_posture("flexion_60", neutral)
        self.assertGreater(chord_length_mm(neutral), chord_length_mm(flexed) - 1e-6)
        # path length of disc stack roughly preserved
        self.assertAlmostEqual(path_length_mm(neutral), path_length_mm(flexed), places=3)

    def test_stack_height_error_small_neutral(self) -> None:
        chain = default_chain()
        err = stack_height_error(chain)
        self.assertIsInstance(err, float)

    def test_jacobian_numeric_shape(self) -> None:
        chain = default_chain()
        J = jacobian_numeric(chain, seg_index=0, axis=0)
        self.assertEqual(len(J), 3)
        self.assertTrue(all(isinstance(x, float) for x in J))

    def test_tip_z_positive(self) -> None:
        tip = end_effector(default_chain())
        self.assertGreater(tip.z, 100.0)

    def test_posture_tip_moves(self) -> None:
        base = default_chain()
        flexed = build_posture("flexion_30", base)
        t0 = end_effector(base)
        t1 = end_effector(flexed)
        delta = ((t0.x - t1.x) ** 2 + (t0.y - t1.y) ** 2 + (t0.z - t1.z) ** 2) ** 0.5
        self.assertGreater(delta, 1.0)


if __name__ == "__main__":
    unittest.main()
