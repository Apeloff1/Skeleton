"""Cross-FPS, era-physics guard tests for frontier timing integration."""
import unittest

from skeleton.jeeves.game_engine_lab import EngineEra, engine_era_profile
from skeleton.jeeves.game_frontier_timing import (
    FrontierEraTiming, compare_presentation_modes,
)


class FrameToEngineBridgeTests(unittest.TestCase):
    def test_mode_preserves_authoritative_era_physics(self):
        for era in (EngineEra.EARLY_3D, EngineEra.FIXED_3D, EngineEra.SHADER,
                    EngineEra.MODERN, EngineEra.NEXT):
            for fps in (30, 50, 120):
                bridge = FrontierEraTiming(era, fps=fps)
                self.assertEqual(bridge.simulation_hz, engine_era_profile(era).tick_hz)
                self.assertEqual(bridge.simulation.policy.presentation_hz, fps)
                self.assertEqual(bridge.presentation_fps, fps)

    def test_same_one_second_simulated_for_all_modes(self):
        for era in (EngineEra.EARLY_3D, EngineEra.MODERN, EngineEra.NEXT):
            result = compare_presentation_modes(era, seconds=1)
            self.assertTrue(result["simulation_rate_identical"], result)
            for fps, record in result["modes"].items():
                self.assertEqual(record["frames"], fps)
                self.assertEqual(record["presentation_deadline_ns"], 1_000_000_000)
                self.assertEqual(record["simulation_ticks"], record["simulation_hz"])

    def test_manual_advance_not_a_second_physics(self):
        first = FrontierEraTiming(EngineEra.MODERN, fps=50)
        timings = [first.advance_one_frame() for _ in range(50)]
        self.assertEqual(len(timings), 50)
        self.assertEqual(first.simulation.simulation_tick, first.simulation_hz)
        self.assertEqual(timings[-1].presentation_index, 49)


if __name__ == "__main__":
    unittest.main()
