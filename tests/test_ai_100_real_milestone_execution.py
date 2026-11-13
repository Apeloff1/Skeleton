"""Real MDM-001..100 execution, exact-source checks and negative recovery."""

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.execute_ai_100_large_milestones import (
    ExecutionPlan, ExecutionReport, CheckOutcome, MilestoneExecutionError,
    PlannedCheck, _hash, _safe_selection, _safe_test,
    create_execution_plan, execute_plan, audit_milestone_coverage,
    verify_execution_report, ROOT,
)


COMMIT = "a" * 40


def _test_file(name="tests/test_ai_100_large_milestones.py"):
    kind, resolved = _safe_test(name, ROOT)
    return PlannedCheck(name, kind, ("VOL-000",), ("MDM-001",),
                        _hash(resolved.read_bytes()))


def test_real_masterplan_first_milestone_maps_to_real_implementation_tests():
    plan = create_execution_plan(
        ("MDM-001",), commit=COMMIT, require_clean=False,
    )
    assert plan.source_commit == COMMIT
    assert len(plan.checks) >= 5
    assert all(c.milestones == ("MDM-001",) for c in plan.checks)
    assert all(c.source_digest == _hash((ROOT / c.path).read_bytes()) for c in plan.checks)
    assert any(c.path.endswith("test_ai_master_plan.py") for c in plan.checks)
    assert "none" == plan.preview()["completion_claim"]


def test_actual_two_milestone_selection_deduplicates_only_exact_tests():
    plan = create_execution_plan(
        ("MDM-001", "MDM-002"), commit=COMMIT, require_clean=False,
    )
    assert len(plan.checks) == len({c.path for c in plan.checks})
    assert set(c for item in plan.checks for c in item.milestones) == {
        "MDM-001", "MDM-002",
    }


def test_100_ids_are_the_original_canonical_mdm_ids():
    selection = _safe_selection(tuple(f"MDM-{i:03d}" for i in range(1, 101)))
    assert len(selection) == 100
    assert selection[0] == "MDM-001"
    assert selection[-1] == "MDM-100"


@pytest.mark.parametrize("bad", (
    ["MDM-000"], ["MDM-101"], ["M001"], ["MDM-01"],
    ["../../outside"], ["MDM-001;echo secret"], [],
))
def test_unsafe_or_noncanonical_milestone_identifier_fails_closed(bad):
    with pytest.raises(MilestoneExecutionError):
        _safe_selection(bad)


@pytest.mark.parametrize("testpath", (
    "/etc/passwd", "../test.py", "tests/../secrets.py",
    "tests//test.py", "tests/./test.py", "scripts/run_arbitrary.py",
    "tests/unsafe.txt", "skeleton/jeeves/main.py", "tests/fake_missing.py",
))
def test_test_runner_rejects_unsafe_missing_or_out_of_scope_test(testpath):
    with pytest.raises(MilestoneExecutionError):
        _safe_test(testpath, ROOT)


def test_executor_writes_hash_linked_proof_from_actual_test_callbacks():
    test_file = _test_file()
    plan = ExecutionPlan(COMMIT, ("MDM-001",), "b" * 64,
                         (test_file, test_file))
    seen = []
    def trusted(check, root, timeout):
        seen.append((check.path, timeout))
        return ("passed", 0, 12, _hash(b"real test output"), 16, "host check passed")

    report = execute_plan(
        plan, root=ROOT, executor=trusted,
        check_worktree=False,
    )
    assert seen == [(test_file.path, 120)] * 2
    assert report.summary()["status"] == "candidate_checks_passed"
    assert report.summary()["independent_milestone_signoff"] is False
    assert report.summary()["qualifying_milestones"] == []
    assert report.outcomes[1].previous == report.outcomes[0].receipt
    verify_execution_report(report)


def test_first_failing_test_stops_without_false_green():
    test_file = _test_file()
    plan = ExecutionPlan(
        COMMIT, ("MDM-001",), "b" * 64,
        (test_file, test_file, test_file),
    )
    attempts = []
    def failing(check, root, timeout):
        attempts.append(check)
        return ("failed", 1, 50, _hash(b"assert failed"), 13, "nonzero")

    report = execute_plan(
        plan, root=ROOT, executor=failing,
        check_worktree=False,
    )
    assert len(attempts) == 1
    assert len(report.outcomes) == 1
    assert report.summary()["status"] == "blocked"
    assert report.summary()["failed_checks"] == [test_file.path]


def test_receipt_forgery_and_reordering_rejected():
    file = _test_file()
    plan = ExecutionPlan(COMMIT, ("MDM-001",), "b" * 64, (file, file))
    def checked(check, root, timeout):
        return "passed", 0, 1, _hash(b"log"), 3, "verified"

    report = execute_plan(plan, root=ROOT, executor=checked, check_worktree=False)
    with pytest.raises(MilestoneExecutionError, match="altered"):
        verify_execution_report(replace(report, outcomes=(
            replace(report.outcomes[0], reason="forged"),
            report.outcomes[1],
        )))
    with pytest.raises(MilestoneExecutionError, match="reordered"):
        verify_execution_report(replace(report, outcomes=tuple(reversed(report.outcomes))))


def test_timeout_and_output_limits_are_bounded():
    plan = ExecutionPlan(COMMIT, ("MDM-001",), "b" * 64, (_test_file(),))
    with pytest.raises(MilestoneExecutionError, match="timeout"):
        execute_plan(plan, timeout=0, check_worktree=False)
    with pytest.raises(MilestoneExecutionError, match="timeout"):
        execute_plan(plan, timeout=901, check_worktree=False)


def test_stale_source_path_is_blocked_before_external_execution():
    original = _test_file()
    changed = replace(original, source_digest="0" * 64)
    # The native process runner must refuse a source after the plan was made.
    from scripts.execute_ai_100_large_milestones import _run_check
    status, *_ = _run_check(changed, ROOT, 1)
    assert status == "blocked"


def test_report_never_labels_candidate_checks_as_feature_complete():
    f = _test_file()
    plan = ExecutionPlan(COMMIT, ("MDM-001",), "b" * 64, (f,))
    def checker(check, root, timeout):
        return "passed", 0, 1, _hash(b"ok"), 2, "passed"

    report = execute_plan(plan, executor=checker, check_worktree=False)
    summary = report.summary()
    assert summary["status"] == "candidate_checks_passed"
    assert summary["qualifying_milestones"] == []
    assert summary["independent_milestone_signoff"] is False



def test_audit_all_original_hundred_milestones_without_claiming_completion():
    requested = tuple(f"MDM-{i:03d}" for i in range(1, 101))
    result = audit_milestone_coverage(requested)
    assert result["kind"] == "source_coverage_audit"
    assert result["milestones_examined"] == 100
    assert result["volumes_examined"] == 421
    assert result["production_completed_milestones"] == 0
    assert result["completion_signoff"] is False
    assert result["unique_planned_tests"] > 0
    assert result["test_path_ready_milestones"] + result["blocked_milestones"] == 100
    assert len(result["audit_receipt"]) == 64
    assert {row["milestone_id"] for row in result["milestones"]} == set(requested)


def test_source_coverage_reports_planned_wildcard_and_missing_tests_separately(monkeypatch):
    from scripts import execute_ai_100_large_milestones as executor

    canonical = "tests/test_ai_100_real_milestone_execution.py"
    fake = {
        "milestones": [{
            "id": "MDM-001",
            "title": "Actual source coverage",
            "volumes": [{
                "id": "VOL-000",
                "acceptance_tests": [
                    canonical,
                    "planned:tests/does_not_exist.py",
                    "skeleton/testing/test_shell_*.py",
                    "tests/this_test_is_missing.py",
                ],
                "contract_targets": ["scripts", "scripts/does_not_exist.py"],
            }],
        }],
    }
    monkeypatch.setattr(executor, "_load_roadmap", lambda root: (fake, "f" * 64))
    report = executor.audit_milestone_coverage(("MDM-001",))
    row = report["milestones"][0]
    assert row["status"] == "blocked_missing_test_implementation"
    assert canonical in row["existing_tests"]
    assert row["missing_tests"] == ["tests/this_test_is_missing.py"]
    assert row["planned_tests"] == ["planned:tests/does_not_exist.py"]
    assert row["unsupported_test_bindings"] == ["skeleton/testing/test_shell_*.py"]
    assert row["existing_implementation_paths"]["scripts"] == "directory-present"
    assert row["missing_implementation_paths"] == ["scripts/does_not_exist.py"]
    assert report["completion_signoff"] is False
