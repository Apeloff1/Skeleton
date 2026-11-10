"""Post-merge gate policy tests: no ancestor, skipped or fixture can certify main."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_post_merge_main import ESSENTIAL_JOBS, inspect, main


HEAD = "a" * 40
OTHER = "b" * 40


def fixture():
    status = {
        "commit": {"sha": HEAD},
        "protected": True,
        "protection": {
            "required_status_checks": {
                "enforcement_level": "everyone",
                "contexts": list(ESSENTIAL_JOBS),
                "checks": [],
            }
        },
    }
    runs = []
    jobs = {}
    for i, (name, required) in enumerate(ESSENTIAL_JOBS.items(), 1):
        run_id = 51000 + i
        runs.append({
            "id": run_id, "name": name, "event": "push",
            "head_sha": HEAD, "status": "completed", "conclusion": "success",
            "run_attempt": 1, "created_at": f"2026-11-10T01:{i:02d}:00Z",
        })
        jobs[str(run_id)] = [
            {"name": job, "status": "completed", "conclusion": "success"}
            for job in required
        ]
        if name == "Merge Readiness":
            jobs[str(run_id)].extend([
                {"name": "Canonical Domain Suite (1)",
                 "status": "completed", "conclusion": "success"},
                {"name": "Canonical Domain Suite (2)",
                 "status": "completed", "conclusion": "success"},
            ])
    return {
        "head": HEAD,
        "branch_before": deepcopy(status),
        "branch_after": deepcopy(status),
        "runs": runs,
        "jobs_by_run": jobs,
    }


def verify(data):
    return inspect(**data)


class ExactMainEvidenceTests(unittest.TestCase):
    def test_synthetic_complete_evidence_is_only_workflow_qualification(self):
        result = verify(fixture())
        self.assertTrue(result["exact_main_workflow_gates_qualified"])
        self.assertTrue(result["current_main_unchanged"])
        self.assertEqual(result["blocking_reasons"], [])
        self.assertFalse(result["first_install_certified"])
        self.assertFalse(result["production_release_approved"])

    def test_unprotected_branch_refuses_even_green_workflows(self):
        data = fixture()
        data["branch_after"]["protected"] = False
        result = verify(data)
        self.assertFalse(result["exact_main_workflow_gates_qualified"])
        self.assertIn("main_branch_unprotected", result["blocking_reasons"])

    def test_inadequate_admin_scope_cannot_qualify(self):
        data = fixture()
        data["branch_after"]["protection"]["required_status_checks"]["enforcement_level"] = "non_admins"
        result = verify(data)
        self.assertIn("main_required_checks_not_enforced_for_everyone", result["blocking_reasons"])

    def test_missing_required_context_blocks_independent_of_success(self):
        data = fixture()
        contexts = data["branch_after"]["protection"]["required_status_checks"]["contexts"]
        contexts.remove("App Foundation E2E")
        result = verify(data)
        self.assertIn("main_required_check_not_configured:App Foundation E2E",
                      result["blocking_reasons"])

    def test_pending_cancelled_skipped_and_failed_are_all_blocks(self):
        for status, conclusion in [
            ("queued", None), ("completed", "cancelled"),
            ("completed", "skipped"), ("completed", "failure"),
        ]:
            with self.subTest(status=status, conclusion=conclusion):
                data = fixture()
                data["runs"][0]["status"] = status
                data["runs"][0]["conclusion"] = conclusion
                result = verify(data)
                self.assertIn(
                    "exact_main_workflow_not_success:Workflow Input Security",
                    result["blocking_reasons"],
                )

    def test_prior_head_success_does_not_count(self):
        data = fixture()
        data["runs"][0]["head_sha"] = OTHER
        result = verify(data)
        self.assertIn("exact_main_push_workflow_missing:Workflow Input Security",
                      result["blocking_reasons"])

    def test_wrong_event_does_not_count(self):
        data = fixture()
        data["runs"][0]["event"] = "pull_request"
        result = verify(data)
        self.assertIn("exact_main_push_workflow_missing:Workflow Input Security",
                      result["blocking_reasons"])

    def test_new_failed_attempt_supersedes_old_success_on_same_head(self):
        data = fixture()
        later = dict(data["runs"][0])
        later.update({
            "id": 60000, "run_attempt": 2,
            "created_at": "2026-11-10T02:00:00Z",
            "conclusion": "failure",
        })
        data["runs"].append(later)
        result = verify(data)
        self.assertEqual(result["workflow_evidence"]["Workflow Input Security"]["run_id"], 60000)
        self.assertIn("exact_main_workflow_not_success:Workflow Input Security",
                      result["blocking_reasons"])

    def test_required_e2e_job_skipped_is_not_accepted(self):
        data = fixture()
        target = next(r for r in data["runs"] if r["name"] == "App Foundation E2E")
        data["jobs_by_run"][str(target["id"])][0]["conclusion"] = "skipped"
        result = verify(data)
        self.assertIn(
            "essential_job_not_success:App Foundation E2E:App Foundation E2E (stack + Playwright)",
            result["blocking_reasons"],
        )

    def test_no_job_inventory_is_not_a_success(self):
        data = fixture()
        data["jobs_by_run"] = {}
        result = verify(data)
        self.assertIn("exact_main_job_inventory_missing:Malware Gate",
                      result["blocking_reasons"])

    def test_domain_shards_must_exist_and_all_succeed(self):
        data = fixture()
        mr = next(r for r in data["runs"] if r["name"] == "Merge Readiness")
        jobs = data["jobs_by_run"][str(mr["id"])]
        for job in jobs:
            if job["name"] == "Canonical Domain Suite (2)":
                job["conclusion"] = "cancelled"
        result = verify(data)
        self.assertIn("canonical_domain_suite_not_success:Canonical Domain Suite (2)",
                      result["blocking_reasons"])
        data["jobs_by_run"][str(mr["id"])] = [
            j for j in jobs if not j["name"].startswith("Canonical Domain Suite (")
        ]
        result = verify(data)
        self.assertIn("canonical_domain_suite_evidence_missing", result["blocking_reasons"])

    def test_duplicate_job_identity_fails_closed(self):
        data = fixture()
        run = data["runs"][0]
        jobs = data["jobs_by_run"][str(run["id"])]
        jobs.append(dict(jobs[0]))
        self.assertIn(
            "ambiguous_duplicate_job_identity:Workflow Input Security",
            verify(data)["blocking_reasons"],
        )

    def test_main_moves_before_or_after_checks_rejects_stale_evidence(self):
        for key, reason in (
            ("branch_before", "main_head_before_not_exact"),
            ("branch_after", "main_head_after_changed"),
        ):
            data = fixture()
            data[key]["commit"]["sha"] = OTHER
            self.assertIn(reason, verify(data)["blocking_reasons"])

    def test_offline_snapshot_never_claims_real_post_merge_qualification(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "synthetic.json"
            snapshot.write_text(json.dumps(data), encoding="utf-8")
            from contextlib import redirect_stdout
            from io import StringIO
            stdout = StringIO()
            with redirect_stdout(stdout):
                status = main(["--snapshot", str(snapshot), "--sha", HEAD])
            report = json.loads(stdout.getvalue())
            self.assertNotEqual(status, 0)
            self.assertFalse(report["exact_main_workflow_gates_qualified"])
            self.assertFalse(report["first_install_certified"])
            self.assertIn("offline_fixture_not_authoritative", report["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
