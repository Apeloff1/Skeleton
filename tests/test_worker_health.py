from __future__ import annotations

import unittest

from skeleton.automation.worker_health import (
    MAX_ACTIVE_WORKERS,
    MAX_OBSERVED_PULL_REQUESTS,
    classify_worker_pr,
    classify_worker_prs,
    summarize_checks,
)


def pr(**overrides):
    value = {
        "number": 17,
        "headRefName": "bot/specialist-root-cause-0123456789abcdef",
        "mergeStateStatus": "CLEAN",
        "isDraft": False,
        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
    }
    value.update(overrides)
    return value


class CheckSummaryTests(unittest.TestCase):
    def test_success_is_passing(self) -> None:
        self.assertEqual(
            summarize_checks([{"conclusion": "SUCCESS"}]),
            ("passing", 1, 0, 0),
        )

    def test_failure_dominates_pending(self) -> None:
        self.assertEqual(
            summarize_checks([
                {"conclusion": "FAILURE"},
                {"status": "IN_PROGRESS"},
                {"conclusion": "SUCCESS"},
            ]),
            ("failing", 3, 1, 1),
        )

    def test_pending_without_failure_is_pending(self) -> None:
        self.assertEqual(
            summarize_checks([{"status": "QUEUED"}]),
            ("pending", 1, 0, 1),
        )

    def test_unknown_status_fails_to_unknown_not_success(self) -> None:
        self.assertEqual(
            summarize_checks([{"status": "ALIEN"}]),
            ("unknown", 1, 0, 0),
        )

    def test_non_list_rollup_is_unknown(self) -> None:
        self.assertEqual(summarize_checks(None), ("unknown", 0, 0, 0))
        self.assertEqual(summarize_checks({}), ("unknown", 0, 0, 0))

    def test_check_rollup_is_bounded(self) -> None:
        checks = [{"conclusion": "SUCCESS"}] * 100
        self.assertEqual(summarize_checks(checks), ("passing", 64, 0, 0))


class WorkerPrClassificationTests(unittest.TestCase):
    def test_passing_clean_pr_is_healthy(self) -> None:
        health = classify_worker_pr(pr())
        self.assertIsNotNone(health)
        self.assertEqual(health.classification, "healthy")
        self.assertEqual(health.worker, "root-cause")
        self.assertEqual(health.base_prefix, "0123456789abcdef")

    def test_failing_ci_is_explicit(self) -> None:
        health = classify_worker_pr(
            pr(statusCheckRollup=[{"conclusion": "FAILURE"}])
        )
        self.assertEqual(health.classification, "failing-ci")
        self.assertEqual(health.check_failures, 1)

    def test_pending_checks_are_explicit(self) -> None:
        health = classify_worker_pr(
            pr(statusCheckRollup=[{"status": "IN_PROGRESS"}])
        )
        self.assertEqual(health.classification, "awaiting-checks")
        self.assertEqual(health.check_pending, 1)

    def test_missing_checks_are_not_assumed_green(self) -> None:
        health = classify_worker_pr(pr(statusCheckRollup=[]))
        self.assertEqual(health.classification, "awaiting-checks")
        self.assertEqual(health.check_state, "unknown")

    def test_conflict_is_distinct_from_ci_failure(self) -> None:
        health = classify_worker_pr(
            pr(mergeStateStatus="DIRTY", statusCheckRollup=[{"conclusion": "SUCCESS"}])
        )
        self.assertEqual(health.classification, "conflicted")

    def test_blocked_with_passing_checks_is_blocked(self) -> None:
        health = classify_worker_pr(pr(mergeStateStatus="BLOCKED"))
        self.assertEqual(health.classification, "blocked")

    def test_draft_takes_precedence(self) -> None:
        health = classify_worker_pr(
            pr(isDraft=True, statusCheckRollup=[{"conclusion": "FAILURE"}])
        )
        self.assertEqual(health.classification, "draft")

    def test_human_branch_is_not_worker_evidence(self) -> None:
        self.assertIsNone(classify_worker_pr(pr(headRefName="feature/human")))

    def test_malformed_base_prefix_is_rejected(self) -> None:
        self.assertIsNone(
            classify_worker_pr(pr(headRefName="bot/specialist-root-cause-not-a-digest"))
        )
        self.assertIsNone(
            classify_worker_pr(
                pr(headRefName="bot/specialist-root-cause-0123456789abcdeG")
            )
        )

    def test_malformed_worker_namespace_is_rejected(self) -> None:
        self.assertIsNone(
            classify_worker_pr(
                pr(headRefName="bot/specialist-Root_Cause-0123456789abcdef")
            )
        )
        self.assertIsNone(
            classify_worker_pr(
                pr(headRefName="bot/specialist--root-0123456789abcdef")
            )
        )
        self.assertIsNone(
            classify_worker_pr(
                pr(headRefName="bot/specialist-røøt-0123456789abcdef")
            )
        )

    def test_non_mapping_pr_is_ignored(self) -> None:
        self.assertIsNone(classify_worker_pr(None))
        self.assertIsNone(classify_worker_pr("not-a-pr"))

    def test_invalid_pr_number_is_rejected(self) -> None:
        self.assertIsNone(classify_worker_pr(pr(number=True)))
        self.assertIsNone(classify_worker_pr(pr(number=0)))
        self.assertIsNone(classify_worker_pr(pr(number="17")))

    def test_output_does_not_retain_check_names_urls_or_text(self) -> None:
        health = classify_worker_pr(
            pr(statusCheckRollup=[{
                "name": "untrusted check name",
                "detailsUrl": "https://example.invalid/untrusted",
                "output": {"text": "untrusted provider text"},
                "conclusion": "SUCCESS",
            }])
        )
        payload = health.as_dict()
        self.assertNotIn("name", payload)
        self.assertNotIn("detailsUrl", payload)
        self.assertNotIn("output", payload)
        self.assertEqual(payload["check_state"], "passing")


class WorkerPrSetTests(unittest.TestCase):
    def test_set_is_sorted_and_counted(self) -> None:
        result = classify_worker_prs([
            pr(
                number=20,
                headRefName="bot/specialist-security-auditor-aaaaaaaaaaaaaaaa",
                statusCheckRollup=[{"conclusion": "FAILURE"}],
            ),
            pr(number=19),
            pr(number=18, headRefName="feature/human"),
        ])
        self.assertEqual(result["active_count"], 2)
        self.assertEqual(
            [item["worker"] for item in result["active_workers"]],
            ["root-cause", "security-auditor"],
        )
        self.assertEqual(
            result["classification_counts"],
            {"failing-ci": 1, "healthy": 1},
        )
        self.assertTrue(result["non_authoritative"])

    def test_limit_is_enforced_after_deterministic_sort(self) -> None:
        result = classify_worker_prs([
            pr(number=30, headRefName="bot/specialist-zeta-aaaaaaaaaaaaaaaa"),
            pr(number=20, headRefName="bot/specialist-alpha-bbbbbbbbbbbbbbbb"),
        ], limit=1)
        self.assertEqual(result["active_count"], 1)
        self.assertEqual(result["active_workers"][0]["worker"], "alpha")

    def test_invalid_limits_fail_closed(self) -> None:
        for value in (0, -1, True, 1.5, "1", MAX_ACTIVE_WORKERS + 1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    classify_worker_prs([], limit=value)

    def test_input_iteration_is_hard_bounded(self) -> None:
        consumed = 0

        def endless():
            nonlocal consumed
            while True:
                consumed += 1
                yield pr(number=consumed)

        result = classify_worker_prs(endless(), limit=1)

        self.assertEqual(consumed, MAX_OBSERVED_PULL_REQUESTS)
        self.assertEqual(result["active_count"], 1)


if __name__ == "__main__":
    unittest.main()
