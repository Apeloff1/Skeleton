from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_machine_review",
    ROOT / "skeleton" / "repo_machine" / "review.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class RepositoryReviewRoutingTests(unittest.TestCase):
    def test_routes_distinct_reviewer_and_verifier(self) -> None:
        route = M.route_independent_review(
            "builder-a",
            ["builder-a", "reviewer-b"],
            ["reviewer-b", "verifier-c"],
        )
        self.assertEqual(route.reviewer_id, "reviewer-b")
        self.assertEqual(route.verifier_id, "verifier-c")

    def test_self_review_route_rejected(self) -> None:
        with self.assertRaises(M.ReviewRoutingError):
            M.ReviewRoute("same", "same", "same")

    def test_exception_ref_does_not_bypass_independence(self) -> None:
        with self.assertRaises(M.ReviewRoutingError):
            M.ReviewRoute("same", "same", "same", exception_ref="issue://emergency")

    def test_verdict_timestamps_must_be_utc_z(self) -> None:
        with self.assertRaises(ValueError):
            M.ReviewVerdict(
                "reviewer-b",
                "approve",
                ("run://1",),
                "2026-10-01T00:00:00",
            )

    def test_verdict_evidence_refs_must_be_unique(self) -> None:
        with self.assertRaises(ValueError):
            M.VerificationVerdict(
                "verifier-c",
                True,
                ("run://1", "run://1"),
                "2026-10-01T00:00:00Z",
            )

    def test_verification_cannot_predate_review(self) -> None:
        route = M.ReviewRoute("builder-a", "reviewer-b", "verifier-c")
        review = M.ReviewVerdict(
            "reviewer-b",
            "approve",
            ("review://exact-head",),
            "2026-10-01T00:02:00Z",
        )
        verification = M.VerificationVerdict(
            "verifier-c",
            True,
            ("verify://exact-head",),
            "2026-10-01T00:01:00Z",
        )
        with self.assertRaisesRegex(
            M.ReviewRoutingError,
            "cannot predate",
        ):
            M.validate_verdicts(route, review, verification)

    def test_verdicts_must_match_route_and_pass(self) -> None:
        route = M.ReviewRoute("builder-a", "reviewer-b", "verifier-c")
        review = M.ReviewVerdict(
            "reviewer-b",
            "approve",
            ("test://focused",),
            "2026-10-01T00:00:00Z",
        )
        verification = M.VerificationVerdict(
            "verifier-c",
            True,
            ("run://exact-head",),
            "2026-10-01T00:01:00Z",
        )
        M.validate_verdicts(route, review, verification)
        with self.assertRaises(M.ReviewRoutingError):
            M.validate_verdicts(
                route,
                M.ReviewVerdict(
                    "reviewer-b",
                    "block",
                    ("x",),
                    "2026-10-01T00:00:00Z",
                ),
                verification,
            )


if __name__ == "__main__":
    unittest.main()
