from __future__ import annotations

import unittest

from skeleton.quality.project_metrics import MetricObservation, ProjectMetricError, ratio_observation


class ProjectMetricTests(unittest.TestCase):
    def test_ratio_exposes_numerator_and_denominator(self) -> None:
        obs = ratio_observation(
            "PM-X",
            "quality",
            3,
            4,
            ("machine/source.json",),
        )
        self.assertEqual(obs.value, 0.75)
        self.assertEqual(obs.numerator, 3)
        self.assertEqual(obs.denominator, 4)
        self.assertFalse(obs.completion_authority)

    def test_metric_cannot_gain_completion_authority(self) -> None:
        with self.assertRaises(ProjectMetricError):
            MetricObservation(
                "PM-X",
                "risk",
                1,
                ("machine/source.json",),
                completion_authority=True,
            )

    def test_zero_denominator_rejected(self) -> None:
        with self.assertRaises(ProjectMetricError):
            ratio_observation("PM-X", "outcome", 0, 0, ("x",))

    def test_ratio_value_must_match_components(self) -> None:
        with self.assertRaises(ValueError):
            MetricObservation(
                "PM-X",
                "quality",
                0.9,
                ("x",),
                numerator=1,
                denominator=2,
            )


if __name__ == "__main__":
    unittest.main()
