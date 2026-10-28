"""Pure source/CI governance regression tests; no GitHub credentials needed."""
import unittest

from scripts.release_governance_verdict import assess, collect


SHA = "a" * 40


def branch(*, protected=True, sha=SHA, checks=True):
    return {
        "name": "main",
        "commit": {"sha": sha},
        "protected": protected,
        "protection": {
            "required_status_checks": {
                "checks": [{"context": "Merge Readiness", "app_id": 15368}] if checks else []
            }
        },
    }


def run(name, *, conclusion="success", status="completed", run_id=100, sha=SHA):
    return {
        "id": run_id,
        "name": name,
        "conclusion": conclusion,
        "status": status,
        "head_branch": "main",
        "head_sha": sha,
        "event": "push",
    }


def green():
    return [
        run("Merge Readiness", run_id=100),
        run("Malware Gate", run_id=101),
        run("Secret scanning", run_id=102),
    ]


class ReleaseGovernanceVerdictTests(unittest.TestCase):
    def test_green_exact_head_and_protected_branch(self):
        report = assess(SHA, branch(), green())
        self.assertEqual(report["verdict"], "READY")
        self.assertFalse(report["production_deployment_attested"])
        self.assertEqual(report["workflow_results"]["Artifact Policy"] if "Artifact Policy" in report["workflow_results"] else "not-pr-required", "not-pr-required")

    def test_unprotected_branch_cannot_be_released(self):
        report = assess(SHA, branch(protected=False), green())
        self.assertEqual(report["verdict"], "BLOCKED")
        self.assertIn("GitHub branch protection is not enabled", report["blocking"])

    def test_missing_required_check_binding_denies_release(self):
        self.assertEqual(assess(SHA, branch(checks=False), green())["verdict"], "BLOCKED")

    def test_stale_tag_sha_denies_release(self):
        self.assertEqual(assess(SHA, branch(sha="b" * 40), green())["verdict"], "BLOCKED")

    def test_queued_workflow_is_not_success(self):
        runs = green()
        runs[0] = run("Merge Readiness", conclusion=None, status="queued")
        self.assertEqual(assess(SHA, branch(), runs)["verdict"], "PENDING")

    def test_missing_required_workflow_is_pending(self):
        self.assertEqual(assess(SHA, branch(), green()[:2])["verdict"], "PENDING")

    def test_failed_or_cancelled_are_blockers(self):
        for conclusion in ("failure", "cancelled", "skipped", "timed_out", None):
            with self.subTest(conclusion=conclusion):
                rows = green()
                rows[1] = run("Malware Gate", conclusion=conclusion, run_id=101)
                self.assertEqual(assess(SHA, branch(), rows)["verdict"], "BLOCKED")

    def test_later_success_does_not_hide_earlier_failure(self):
        self.assertEqual(
            assess(SHA, branch(), green() + [run("Malware Gate", conclusion="failure", run_id=50)])["verdict"],
            "BLOCKED",
        )

    def test_path_scoped_failure_blocks_if_triggered(self):
        rows = green() + [run("Workflow Input Security", conclusion="failure", run_id=110)]
        self.assertEqual(assess(SHA, branch(), rows)["verdict"], "BLOCKED")

    def test_another_branch_or_event_cannot_satisfy_required_checks(self):
        rows = green()[:2]
        wrong = run("Secret scanning", run_id=105)
        wrong["event"] = "pull_request"
        rows.append(wrong)
        self.assertEqual(assess(SHA, branch(), rows)["verdict"], "PENDING")

    def test_incomplete_api_inventory_fails_closed(self):
        def fake_api(path):
            if "/branches/" in path:
                return branch()
            return {"total_count": 4, "workflow_runs": green()}
        with self.assertRaisesRegex(ValueError, "truncated"):
            collect("Apeloff1/Skeleton", SHA, "main", fake_api)

    def test_malformed_workflow_id_blocks(self):
        rows = green()
        rows[0]["id"] = "bad"
        self.assertEqual(assess(SHA, branch(), rows)["verdict"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
