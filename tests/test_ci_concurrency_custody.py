"""Regression for immutable main-SHA CI evidence in the core workflows."""
from __future__ import annotations

import unittest

from scripts.check_ci_concurrency_custody import WORKFLOWS, validate, validate_text

GROUP = "$" + "{{ github.event.pull_request.number || github.sha }}"
CANCEL = "$" + "{{ github.event_name == 'pull_request' }}"


def template(name: str) -> str:
    prefix = WORKFLOWS[name]
    return (
        "name: Test\n"
        "on: push\n"
        "concurrency:\n"
        f"  group: {prefix}-{GROUP}\n"
        f"  cancel-in-progress: {CANCEL}\n"
        "jobs:\n  audit:\n    runs-on: ubuntu-latest\n"
    )


class ImmutableCiConcurrencyContract(unittest.TestCase):
    def test_live_core_workflow_concurrency_contract(self) -> None:
        self.assertEqual(validate(), [])

    def test_good_contract_for_each_required_workflow(self) -> None:
        for name in WORKFLOWS:
            with self.subTest(name=name):
                self.assertEqual(validate_text(name, template(name)), [])

    def test_main_ref_based_cancellation_fails_closed(self) -> None:
        for name in WORKFLOWS:
            with self.subTest(name=name):
                bad = template(name).replace("github.sha", "github.ref")
                self.assertTrue(any("grouping drifted" in x for x in validate_text(name, bad)))

    def test_permanent_cancel_in_progress_true_fails_closed(self) -> None:
        for name in WORKFLOWS:
            with self.subTest(name=name):
                bad = template(name).replace(CANCEL, "true")
                self.assertTrue(any("must not be cancelled" in x for x in validate_text(name, bad)))

    def test_missing_and_duplicate_concurrency_rejected(self) -> None:
        for name in WORKFLOWS:
            with self.subTest(name=name):
                self.assertTrue(validate_text(name, "name: Test\non: push\n"))
                bad = template(name).replace(
                    "  cancel-in-progress:",
                    "  group: duplicate\n  cancel-in-progress:",
                )
                self.assertTrue(any("duplicated group" in x for x in validate_text(name, bad)))

    def test_unreviewed_workflow_refused(self) -> None:
        self.assertEqual(validate_text("unknown.yml", "concurrency:\n"),
                         ["unknown.yml: unreviewed workflow"])


if __name__ == "__main__":
    unittest.main()
