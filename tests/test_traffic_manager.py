from __future__ import annotations

import unittest

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
            stale_queued_seconds=900,
            max_stale_queued_runs=2,
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
        self.assertTrue(decision.relieve)
        self.assertEqual(
            decision.relief_reason,
            "queue-capacity-exhausted",
        )

    def test_stale_queue_pressure_requests_relief_before_capacity_limit(self) -> None:
        queued = tuple(
            run(
                name=f"Queued stale {i}",
                status="queued",
                conclusion="",
                database_id=20 + i,
                updated_at="2027-01-15T07:00:00Z",
            )
            for i in range(2)
        )
        decision = evaluate(
            snapshot(runs=queued),
            policy=self.policy,
            force=True,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "stale-queue-pressure",
        )
        self.assertTrue(decision.relieve)
        self.assertEqual(
            decision.relief_reason,
            "stale-queue-pressure",
        )
        self.assertEqual(decision.stale_queued_runs, 2)
        self.assertEqual(
            decision.oldest_queued_age_seconds,
            3600,
        )

    def test_saturated_run_inventory_requests_fail_closed_relief(self) -> None:
        completed = tuple(
            run(
                name=f"Completed {i}",
                database_id=1000 + i,
            )
            for i in range(100)
        )
        decision = evaluate(
            snapshot(runs=completed),
            policy=self.policy,
            force=True,
        )
        self.assertFalse(decision.admit)
        self.assertEqual(
            decision.reason,
            "run-inventory-saturated",
        )
        self.assertTrue(decision.inventory_saturated)
        self.assertTrue(decision.relieve)
        self.assertEqual(
            decision.relief_reason,
            "run-inventory-saturated",
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
        self.assertFalse(decision.relieve)
        self.assertEqual(decision.relief_reason, "none")

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


if __name__ == "__main__":
    unittest.main()
