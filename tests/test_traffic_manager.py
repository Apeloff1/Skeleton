from __future__ import annotations

import unittest

from skeleton.automation.branch_merge_manager import (
    Branch,
    PullRequest,
    build_plan,
)
from skeleton.automation.traffic_manager import (
    TrafficPolicy,
    TrafficSnapshot,
    evaluate,
)


BASE = "a" * 40
NOW = 1_800_000_000


def run(
    *,
    name: str,
    status: str = "completed",
    conclusion: str = "success",
    head_sha: str = BASE,
    updated_at: str = "2027-01-15T07:55:00Z",
    database_id: int = 1,
) -> dict[str, object]:
    return {
        "databaseId": database_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "headSha": head_sha,
        "updatedAt": updated_at,
        "createdAt": updated_at,
    }


def snapshot(
    *,
    runs: tuple[dict[str, object], ...] = (),
    prs: tuple[dict[str, object], ...] = (),
    issues: tuple[dict[str, object], ...] = (),
    current_run_id: str = "999",
) -> TrafficSnapshot:
    return TrafficSnapshot(
        repository="Apeloff1/Skeleton",
        base_sha=BASE,
        observed_at=NOW,
        current_run_id=current_run_id,
        workflow_runs=runs,
        pull_requests=prs,
        issues=issues,
    )


class TrafficManagerAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = TrafficPolicy(
            max_active_runs=4,
            max_queued_runs=3,
            max_critical_active=2,
            cooldown_seconds=1800,
            maintenance_interval_seconds=7200,
            failure_window_seconds=21600,
        )

    def test_failure_demand_admits_repair_lane(self) -> None:
        decision = evaluate(
            snapshot(
                runs=(
                    run(
                        name="CI/CD",
                        conclusion="failure",
                        updated_at="2027-01-15T07:40:00Z",
                    ),
                )
            ),
            policy=self.policy,
        )
        self.assertTrue(decision.admit)
        self.assertEqual(decision.lane, "repair")
        self.assertEqual(decision.recent_failures, 1)

    def test_active_capacity_blocks_even_when_failures_exist(self) -> None:
        active = tuple(
            run(
                name=f"Background {i}",
                status="in_progress",
                conclusion="",
                database_id=i,
            )
            for i in range(4)
        )
        decision = evaluate(
            snapshot(runs=active),
            policy=self.policy,
            force=True,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "active-capacity-exhausted",
        )

    def test_queue_capacity_blocks_force(self) -> None:
        queued = tuple(
            run(
                name=f"Queued {i}",
                status="queued",
                conclusion="",
                database_id=i,
            )
            for i in range(3)
        )
        decision = evaluate(
            snapshot(runs=queued),
            policy=self.policy,
            force=True,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "queue-capacity-exhausted",
        )

    def test_critical_lane_contention_blocks(self) -> None:
        runs = (
            run(
                name="Merge Readiness",
                status="in_progress",
                conclusion="",
                database_id=10,
            ),
            run(
                name="Workflow Input Security",
                status="in_progress",
                conclusion="",
                database_id=11,
            ),
        )
        decision = evaluate(
            snapshot(runs=runs),
            policy=self.policy,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "critical-lane-contention",
        )

    def test_existing_managed_automation_blocks_duplicate(self) -> None:
        decision = evaluate(
            snapshot(
                runs=(
                    run(
                        name="Repository Supervisor",
                        status="in_progress",
                        conclusion="",
                    ),
                )
            ),
            policy=self.policy,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "managed-automation-already-active",
        )

    def test_current_traffic_manager_run_is_excluded(self) -> None:
        decision = evaluate(
            snapshot(
                runs=(
                    run(
                        name="Automation Traffic Manager",
                        status="in_progress",
                        conclusion="",
                        database_id=999,
                    ),
                    run(
                        name="CI/CD",
                        conclusion="failure",
                        database_id=1000,
                        updated_at="2027-01-15T07:40:00Z",
                    ),
                )
            ),
            policy=self.policy,
        )
        self.assertTrue(decision.admit)
        self.assertEqual(decision.managed_active, 0)

    def test_same_head_success_enforces_cooldown(self) -> None:
        decision = evaluate(
            snapshot(
                runs=(
                    run(
                        name="Repository Supervisor",
                        conclusion="success",
                        updated_at="2027-01-15T07:50:00Z",
                    ),
                    run(
                        name="CI/CD",
                        conclusion="failure",
                        database_id=2,
                        updated_at="2027-01-15T07:40:00Z",
                    ),
                )
            ),
            policy=self.policy,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "same-head-cooldown",
        )

    def test_force_bypasses_soft_cooldown(self) -> None:
        decision = evaluate(
            snapshot(
                runs=(
                    run(
                        name="Repository Supervisor",
                        conclusion="success",
                        updated_at="2027-01-15T07:50:00Z",
                    ),
                )
            ),
            policy=self.policy,
            force=True,
        )
        self.assertTrue(decision.admit)
        self.assertEqual(
            decision.reason,
            "forced-admission",
        )

    def test_authorized_issue_uses_build_lane(self) -> None:
        decision = evaluate(
            snapshot(
                issues=(
                    {
                        "number": 7,
                        "labels": [
                            {"name": "automation-approved"}
                        ],
                    },
                ),
            ),
            policy=self.policy,
        )
        self.assertTrue(decision.admit)
        self.assertEqual(decision.lane, "build")
        self.assertEqual(
            decision.authorized_issues,
            1,
        )

    def test_blocked_pr_uses_integration_lane(self) -> None:
        decision = evaluate(
            snapshot(
                prs=(
                    {
                        "number": 4,
                        "isDraft": False,
                        "mergeStateStatus": "BLOCKED",
                    },
                )
            ),
            policy=self.policy,
        )
        self.assertTrue(decision.admit)
        self.assertEqual(
            decision.lane,
            "integration",
        )

    def test_draft_blocked_pr_does_not_create_demand(self) -> None:
        recent = run(
            name="Repository Supervisor",
            conclusion="success",
            updated_at="2027-01-15T07:20:00Z",
        )
        decision = evaluate(
            snapshot(
                runs=(recent,),
                prs=(
                    {
                        "number": 4,
                        "isDraft": True,
                        "mergeStateStatus": "BLOCKED",
                    },
                ),
            ),
            policy=self.policy,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "no-actionable-demand",
        )

    def test_maintenance_admits_when_no_prior_success_exists(self) -> None:
        decision = evaluate(
            snapshot(),
            policy=self.policy,
        )
        self.assertTrue(decision.admit)
        self.assertEqual(
            decision.lane,
            "maintenance",
        )

    def test_old_failure_outside_window_is_not_demand(self) -> None:
        recent_success = run(
            name="Repository Supervisor",
            conclusion="success",
            updated_at="2027-01-15T07:00:00Z",
        )
        old_failure = run(
            name="CI/CD",
            conclusion="failure",
            database_id=2,
            updated_at="2026-12-01T00:00:00Z",
        )
        decision = evaluate(
            snapshot(
                runs=(recent_success, old_failure),
            ),
            policy=self.policy,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.recent_failures,
            0,
        )
        self.assertEqual(
            decision.reason,
            "no-actionable-demand",
        )


class BranchMergePlanningTests(unittest.TestCase):
    def test_non_draft_branch_backed_pr_dispatches(self) -> None:
        plan = build_plan(
            "Apeloff1/Skeleton",
            "main",
            (
                Branch("main", protected=True),
                Branch("fix/a"),
                Branch("feat/b"),
            ),
            (
                PullRequest(12, "fix/a", "main", False, (), "clean"),
                PullRequest(13, "feat/b", "main", False, (), "blocked"),
            ),
            complete=True,
            observed_at=NOW,
        )
        self.assertTrue(plan.dispatch)
        self.assertEqual(plan.eligible_count, 2)
        self.assertEqual([item.number for item in plan.candidates], [12, 13])
        self.assertEqual(plan.max_merges, 2)

    def test_draft_and_opt_out_are_held(self) -> None:
        plan = build_plan(
            "Apeloff1/Skeleton",
            "main",
            (Branch("fix/a"), Branch("fix/b")),
            (
                PullRequest(1, "fix/a", "main", True, (), "clean"),
                PullRequest(
                    2,
                    "fix/b",
                    "main",
                    False,
                    ("do-not-merge",),
                    "clean",
                ),
            ),
            complete=True,
            observed_at=NOW,
        )
        self.assertFalse(plan.dispatch)
        self.assertEqual(plan.draft_count, 1)
        self.assertEqual(plan.opt_out_count, 1)

    def test_backup_and_protected_branches_are_excluded(self) -> None:
        plan = build_plan(
            "Apeloff1/Skeleton",
            "main",
            (
                Branch("backup/old"),
                Branch("release/protected", protected=True),
            ),
            (
                PullRequest(1, "backup/old", "main", False, (), "clean"),
                PullRequest(
                    2,
                    "release/protected",
                    "main",
                    False,
                    (),
                    "clean",
                ),
            ),
            complete=True,
            observed_at=NOW,
        )
        self.assertFalse(plan.dispatch)
        self.assertEqual(plan.eligible_count, 0)

    def test_truncated_branch_inventory_fails_closed(self) -> None:
        plan = build_plan(
            "Apeloff1/Skeleton",
            "main",
            (Branch("fix/a"),),
            (PullRequest(1, "fix/a", "main", False, (), "clean"),),
            complete=False,
            observed_at=NOW,
        )
        self.assertFalse(plan.dispatch)
        self.assertEqual(plan.reason, "repository-inventory-truncated")

    def test_ambiguous_duplicate_head_is_held(self) -> None:
        plan = build_plan(
            "Apeloff1/Skeleton",
            "main",
            (Branch("fix/a"),),
            (
                PullRequest(1, "fix/a", "main", False, (), "clean"),
                PullRequest(2, "fix/a", "main", False, (), "clean"),
            ),
            complete=True,
            observed_at=NOW,
        )
        self.assertFalse(plan.dispatch)
        self.assertEqual(plan.ambiguous_count, 1)

    def test_clean_candidates_sort_before_blocked_and_budget_caps(self) -> None:
        plan = build_plan(
            "Apeloff1/Skeleton",
            "main",
            (
                Branch("fix/a"),
                Branch("fix/b"),
                Branch("fix/c"),
            ),
            (
                PullRequest(7, "fix/a", "main", False, (), "blocked"),
                PullRequest(8, "fix/b", "main", False, (), "clean"),
                PullRequest(9, "fix/c", "main", False, (), "unstable"),
            ),
            complete=True,
            max_merges=1,
            observed_at=NOW,
        )
        self.assertEqual([item.number for item in plan.candidates], [8, 9, 7])
        self.assertEqual(plan.max_merges, 1)


if __name__ == "__main__":
    unittest.main()
