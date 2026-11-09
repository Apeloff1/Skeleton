from __future__ import annotations

import unittest

from skeleton.quality.p2_quality import (
    P2QualityError,
    QualityObservation,
    evaluate_quality_vector,
)


class P2QualityVectorTests(unittest.TestCase):
    def test_all_dimensions_must_pass(self) -> None:
        result = evaluate_quality_vector(
            ("ENG-REQ", "ENG-TEST"),
            (
                QualityObservation("ENG-REQ", True, ("run://req",)),
                QualityObservation("ENG-TEST", False, ("run://test",)),
            ),
        )
        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.failed_dimensions, ("ENG-TEST",))

    def test_missing_dimension_blocks(self) -> None:
        result = evaluate_quality_vector(
            ("ENG-REQ", "ENG-TEST"),
            (QualityObservation("ENG-REQ", True, ("run://req",)),),
        )
        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.missing_dimensions, ("ENG-TEST",))

    def test_unknown_dimension_fails_closed(self) -> None:
        with self.assertRaisesRegex(P2QualityError, "unexpected quality dimensions"):
            evaluate_quality_vector(
                ("ENG-REQ",),
                (QualityObservation("ENG-OTHER", True, ("run://x",)),),
            )

    def test_weighted_compensation_is_not_an_api(self) -> None:
        self.assertFalse(hasattr(QualityObservation, "weight"))
        self.assertFalse(hasattr(QualityObservation, "score"))


if __name__ == "__main__":
    unittest.main()
