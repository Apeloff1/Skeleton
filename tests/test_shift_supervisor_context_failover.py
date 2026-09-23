from core.shift_supervisor.context_budget import build_bounded_project_context


def _issue(number, *, updated, labels=None):
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": "bounded evidence",
        "labels": [{"name": value} for value in (labels or [])],
        "updatedAt": updated,
        "url": f"https://example.invalid/{number}",
    }


def _context(issues):
    return build_bounded_project_context(
        repository="Apeloff1/Skeleton",
        base_sha="a" * 40,
        issues=issues,
        pulls=[],
        workflow_runs=[],
        code_scanning_alerts=[],
        plan_title="[Shift Supervisor] Canonical Night + Idle Plan",
    )


def test_context_retains_bootstrap_authority_outside_newest_window():
    issues = [_issue(i, updated=f"2026-09-23T18:{i:02d}:00Z") for i in range(1, 14)]
    issues.append(_issue(1685, updated="2026-09-01T00:00:00Z"))
    numbers = [row["number"] for row in _context(issues)["open_issues"]]
    assert 1685 in numbers
    assert len(numbers) == 12


def test_context_retains_explicitly_approved_intake():
    issues = [_issue(i, updated=f"2026-09-23T18:{i:02d}:00Z") for i in range(1, 14)]
    issues.append(_issue(9001, updated="2026-08-01T00:00:00Z", labels=["supervisor-ready"]))
    numbers = [row["number"] for row in _context(issues)["open_issues"]]
    assert 9001 in numbers


def test_context_does_not_expand_budget_for_authorized_work():
    issues = [
        _issue(2000 + i, updated=f"2026-09-{(i % 28) + 1:02d}T00:00:00Z", labels=["build-approved"])
        for i in range(30)
    ]
    context = _context(issues)
    assert len(context["open_issues"]) == 12
    assert context["snapshot_budget"]["serialized_bytes"] <= context["snapshot_budget"]["max_serialized_bytes"]
