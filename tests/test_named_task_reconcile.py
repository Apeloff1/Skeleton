from __future__ import annotations

import json
from pathlib import Path

from scripts.check_named_task_reconcile import (
    CLASSES,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    ISSUE_RANGE_END,
    ISSUE_RANGE_START,
    TASK_FIELDS,
    TASK_ID,
    build_report,
    classify_named_task,
    main,
    reconcile_named_tasks,
)


def _task(issue: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "issue": issue,
        "title": f"named-task-{issue}",
        "owner": None,
        "status": "open",
        "kind": "issue",
        "merge_state": "not_applicable",
        "superseded_by": None,
        "living_pr": None,
        "evidence_refs": [f"issue:#{issue}"],
    }
    row.update(overrides)
    return row


def _document(
    overrides_by_issue: dict[int, dict[str, object]] | None = None,
    extra_tasks: list[dict[str, object]] | None = None,
    **doc_overrides: object,
) -> dict[str, object]:
    by_issue = {number: _task(number) for number in range(ISSUE_RANGE_START, ISSUE_RANGE_END + 1)}
    if overrides_by_issue:
        for number, fields in overrides_by_issue.items():
            by_issue[number] = _task(number, **fields)
    tasks = [by_issue[number] for number in range(ISSUE_RANGE_START, ISSUE_RANGE_END + 1)]
    if extra_tasks:
        tasks.extend(extra_tasks)
    payload: dict[str, object] = {"schema_version": 1, "tasks": tasks}
    payload.update(doc_overrides)
    return payload


def test_closed_class_set_and_seed_identity() -> None:
    assert CLASSES == ("current", "superseded", "merged", "unknown")
    assert len(CLASSES) == len(set(CLASSES))
    assert TASK_ID == "reserve-S492-named-task-reconcile"
    assert CONFLICT_DOMAIN == "ops.readonly.named_reconcile"
    assert (ISSUE_RANGE_START, ISSUE_RANGE_END) == (929, 956)
    assert "tasks" in DOCUMENT_FIELDS
    assert "living_pr" in TASK_FIELDS


def test_open_issue_with_living_pr_is_current() -> None:
    task = _task(929, living_pr=975, owner="Apeloff1")
    assert classify_named_task(task) == "current"


def test_open_issue_without_pr_is_still_current() -> None:
    assert classify_named_task(_task(938)) == "current"


def test_merged_pull_is_merged() -> None:
    task = _task(
        939,
        kind="pull",
        status="closed",
        merge_state="merged",
        evidence_refs=["pull:#939"],
    )
    assert classify_named_task(task) == "merged"


def test_closed_issue_with_superseded_by_is_superseded() -> None:
    task = _task(941, status="closed", kind="pull", merge_state="unmerged", superseded_by=972)
    assert classify_named_task(task) == "superseded"


def test_closed_without_merge_or_supersedence_fails_closed() -> None:
    task = _task(930, status="closed", merge_state="not_applicable")
    assert classify_named_task(task) == "unknown"


def test_unknown_fields_and_types_fail_closed() -> None:
    assert classify_named_task(["not", "an", "object"]) == "unknown"
    assert classify_named_task(_task(929, extra=True)) == "unknown"
    assert classify_named_task(_task(929, status="triaged")) == "unknown"
    assert classify_named_task(_task(929, kind="ticket")) == "unknown"
    assert classify_named_task(_task(929, merge_state="maybe")) == "unknown"
    assert classify_named_task(_task(1000)) == "unknown"
    assert classify_named_task(_task(929, issue=True)) == "unknown"


def test_inconsistent_merge_and_open_or_living_pr_fail_closed() -> None:
    open_merged = _task(951, kind="pull", status="open", merge_state="merged")
    assert classify_named_task(open_merged) == "unknown"
    merged_with_living = _task(
        951,
        kind="pull",
        status="closed",
        merge_state="merged",
        living_pr=951,
    )
    assert classify_named_task(merged_with_living) == "unknown"


def test_pull_cannot_use_not_applicable_merge_state() -> None:
    task = _task(939, kind="pull", status="open", merge_state="not_applicable")
    assert classify_named_task(task) == "unknown"


def test_self_supersedence_and_invalid_living_pr_fail_closed() -> None:
    assert classify_named_task(_task(932, superseded_by=932)) == "unknown"
    assert classify_named_task(_task(932, superseded_by=0)) == "unknown"
    assert classify_named_task(_task(932, living_pr=False)) == "unknown"
    assert classify_named_task(_task(932, owner="")) == "unknown"
    assert classify_named_task(_task(932, title=" ")) == "unknown"
    assert classify_named_task(_task(932, evidence_refs=[])) == "unknown"
    assert classify_named_task(_task(932, evidence_refs=[" "])) == "unknown"


def test_full_range_document_classifies_without_violations() -> None:
    document = _document(
        {
            929: {"living_pr": 975, "owner": "Apeloff1"},
            930: {"status": "closed", "superseded_by": 901},
            939: {
                "kind": "pull",
                "status": "closed",
                "merge_state": "merged",
                "evidence_refs": ["pull:#939"],
            },
            941: {
                "kind": "pull",
                "status": "closed",
                "merge_state": "unmerged",
                "superseded_by": 972,
                "living_pr": 972,
            },
            951: {
                "kind": "pull",
                "status": "closed",
                "merge_state": "merged",
                "evidence_refs": ["pull:#951"],
            },
        }
    )
    rows, errors = reconcile_named_tasks(document)
    assert errors == []
    by_issue = {row["issue"]: row["class"] for row in rows}
    assert by_issue[929] == "current"
    assert by_issue[930] == "superseded"
    assert by_issue[939] == "merged"
    assert by_issue[941] == "superseded"
    assert by_issue[951] == "merged"
    assert by_issue[956] == "current"
    assert len(rows) == ISSUE_RANGE_END - ISSUE_RANGE_START + 1


def test_unknown_rows_are_violations() -> None:
    document = _document({933: {"status": "closed"}})
    rows, errors = reconcile_named_tasks(document)
    closed = next(row for row in rows if row["issue"] == 933)
    assert closed["class"] == "unknown"
    assert any("named-reconcile unknown unclassified" in item for item in errors)
    assert any("tasks[" in item and "933" in item for item in errors)


def test_missing_issue_in_range_fails_closed() -> None:
    document = _document()
    tasks = list(document["tasks"])
    tasks = [task for task in tasks if task["issue"] != 940]
    document["tasks"] = tasks
    _rows, errors = reconcile_named_tasks(document)
    assert any("named-reconcile missing_value issue" in item for item in errors)
    assert any("#940" in item for item in errors)


def test_duplicate_and_out_of_range_issues_fail_closed() -> None:
    document = _document(extra_tasks=[_task(929, title="clone")])
    _rows, errors = reconcile_named_tasks(document)
    assert any("named-reconcile unknown duplicate" in item for item in errors)

    outside = _document(extra_tasks=[_task(957)])
    _rows, outside_errors = reconcile_named_tasks(outside)
    assert any("named-reconcile unknown unclassified" in item for item in outside_errors)


def test_unknown_document_fields_fail_closed() -> None:
    errors = reconcile_named_tasks(_document(owner_team="idle"))[1]
    assert any("named-reconcile unknown field" in item for item in errors)
    wrong = reconcile_named_tasks(_document(schema_version=2))[1]
    assert any("named-reconcile unknown schema_version" in item for item in wrong)
    assert reconcile_named_tasks(["nope"])[1][0].startswith("named-reconcile unknown root_type")


def test_report_retires_stale_targets_and_lists_living_prs_only() -> None:
    document = _document(
        {
            929: {"living_pr": 975},
            931: {"living_pr": 971},
            941: {
                "kind": "pull",
                "status": "closed",
                "merge_state": "unmerged",
                "superseded_by": 972,
                "living_pr": 972,
            },
            951: {
                "kind": "pull",
                "status": "closed",
                "merge_state": "merged",
                "evidence_refs": ["pull:#951"],
            },
        }
    )
    rows, errors = reconcile_named_tasks(document)
    assert errors == []
    report = build_report(rows)
    assert report["task_id"] == TASK_ID
    assert report["conflict_domain"] == CONFLICT_DOMAIN
    assert report["retire"] == [941]
    assert report["do_not_duplicate"] == [971, 972, 975]
    assert report["counts"]["merged"] == 1
    assert report["counts"]["superseded"] == 1
    assert report["counts"]["unknown"] == 0
    assert 951 not in report["retire"]
    assert 951 not in report["do_not_duplicate"]


def test_shared_living_pr_is_not_treated_as_a_new_pr() -> None:
    document = _document({944: {"living_pr": 1036}, 953: {"living_pr": 1036}})
    rows, errors = reconcile_named_tasks(document)
    assert errors == []
    report = build_report(rows)
    assert report["do_not_duplicate"] == [1036]
    assert {row["issue"] for row in rows if row["class"] == "current"} >= {944, 953}


def test_cli_accepts_valid_fixture_and_prints_retire_list(tmp_path: Path, capsys) -> None:
    document = _document(
        {
            941: {
                "kind": "pull",
                "status": "closed",
                "merge_state": "unmerged",
                "superseded_by": 972,
                "living_pr": 972,
            }
        }
    )
    path = tmp_path / "named-tasks.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert main([str(path)]) == 0
    output = capsys.readouterr().out
    assert "superseded=1" in output
    assert "unknown=0" in output
    assert "retire: #941" in output
    assert "do_not_duplicate: #972" in output


def test_cli_rejects_unknown_named_tasks(tmp_path: Path) -> None:
    path = tmp_path / "named-tasks.json"
    path.write_text(json.dumps(_document({930: {"status": "closed"}})), encoding="utf-8")
    assert main([str(path)]) == 1
