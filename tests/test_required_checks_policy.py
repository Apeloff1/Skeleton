"""Tests for the #127 required-check policy guard and merge-readiness reporter."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load("check_required_checks_policy")
status = _load("merge_readiness_status")
POLICY = json.loads(
    (ROOT / ".github/ci/required-checks.json").read_text(encoding="utf-8")
)
SHA = "a" * 40


@pytest.fixture()
def repo_copy(tmp_path: Path) -> Path:
    """Copy just the files the guard reads into an isolated tree."""

    files = [
        ".github/ci/required-checks.json",
        "scripts/configure_main_protection.sh",
        "scripts/check_merge_readiness_contract.py",
        *POLICY["documentation"],
        *POLICY["name_references"],
    ]
    for relative in files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (tmp_path / ".github/workflows").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".github/workflows/merge-readiness.yml",
        tmp_path / ".github/workflows/merge-readiness.yml",
    )
    return tmp_path


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture drift: {old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --- guard -----------------------------------------------------------------


def test_current_repository_satisfies_policy() -> None:
    failures, policy = guard.run(ROOT, guard.DEFAULT_POLICY)
    assert failures == []
    assert policy["required_status_checks"][0]["context"] == "Merge Readiness"


def test_copy_fixture_is_clean(repo_copy: Path) -> None:
    assert guard.run(repo_copy, guard.DEFAULT_POLICY)[0] == []


def test_detects_dropped_lane_dependency(repo_copy: Path) -> None:
    _edit(
        repo_copy / ".github/workflows/merge-readiness.yml",
        "      - pr_automation\n",
        "",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("aggregate needs" in item for item in failures)


def test_detects_renamed_required_job(repo_copy: Path) -> None:
    _edit(
        repo_copy / ".github/workflows/merge-readiness.yml",
        "    name: Merge Readiness\n",
        "    name: Ready Gate\n",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("must be named 'Merge Readiness'" in item for item in failures)


def test_detects_renamed_lane(repo_copy: Path) -> None:
    _edit(
        repo_copy / ".github/workflows/merge-readiness.yml",
        "    name: Integration Smoke\n",
        "    name: Smoke\n",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("'integration_smoke' must be named" in item for item in failures)


def test_detects_missing_result_binding(repo_copy: Path) -> None:
    _edit(
        repo_copy / ".github/workflows/merge-readiness.yml",
        "UNIT_RESULT: ${{ needs.unit.result }}",
        "UNIT_RESULT: success",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("result binding" in item for item in failures)


def test_detects_duplicate_required_check_publisher(repo_copy: Path) -> None:
    (repo_copy / ".github/workflows/impostor.yml").write_text(
        "name: Impostor\non: [pull_request]\njobs:\n  fake:\n    name: 'Merge Readiness'\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    (repo_copy / ".github/workflows/by-id.yaml").write_text(
        "name: ById\non: [push]\njobs:\n  Merge Readiness:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("impostor.yml" in item and "also publishes" in item for item in failures)


def test_detects_protection_script_drift(repo_copy: Path) -> None:
    _edit(
        repo_copy / "scripts/configure_main_protection.sh",
        '"allow_force_pushes": false',
        '"allow_force_pushes": true',
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("allow_force_pushes" in item for item in failures)


def test_detects_protection_app_drift(repo_copy: Path) -> None:
    _edit(
        repo_copy / "scripts/configure_main_protection.sh",
        'required_app_id="15368"',
        'required_app_id="1"',
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("required_app_id" in item for item in failures)


def test_detects_contract_checker_drift(repo_copy: Path) -> None:
    _edit(
        repo_copy / "scripts/check_merge_readiness_contract.py",
        '    "pr_automation",\n)',
        ")",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("REQUIRED_NEEDS" in item for item in failures)


def test_detects_stale_doc_name(repo_copy: Path) -> None:
    doc = repo_copy / "docs/SECURITY_STATUS.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nRequire `CI/CD / Merge Readiness`.\n",
        encoding="utf-8",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any("stale required check name" in item for item in failures)


def test_detects_undocumented_lane(repo_copy: Path) -> None:
    doc = repo_copy / "docs/MERGE_READINESS.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("PR Automation Tests", "PR tests"),
        encoding="utf-8",
    )
    failures, _ = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert any(
        "MERGE_READINESS.md: must document required lane 'PR Automation Tests'" in item
        for item in failures
    )


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda p: p.update(schema_version=2), "schema_version"),
        (
            lambda p: p["required_status_checks"].append(
                dict(p["required_status_checks"][0])
            ),
            "exactly one",
        ),
        (
            lambda p: p["aggregate_lanes"].append(dict(p["aggregate_lanes"][0])),
            "duplicated",
        ),
        (
            lambda p: p["protection"].update(allow_force_pushes=True),
            "forbid force-pushes",
        ),
        (lambda p: p["required_status_checks"][0].update(app_id="15368"), "app_id"),
    ],
)
def test_malformed_policy_fails_closed(repo_copy: Path, mutate, message: str) -> None:
    path = repo_copy / ".github/ci/required-checks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    failures, policy = guard.run(repo_copy, guard.DEFAULT_POLICY)
    assert policy is None
    assert len(failures) == 1 and message in failures[0]


def test_guard_cli_exit_codes(repo_copy: Path, capsys) -> None:
    assert guard.main(["--root", str(repo_copy)]) == 0
    _edit(repo_copy / ".github/workflows/merge-readiness.yml", "      - unit\n", "")
    assert guard.main(["--root", str(repo_copy)]) == 1
    assert "Required-check policy violations" in capsys.readouterr().out


def test_parse_jobs_stops_at_next_top_level_key() -> None:
    jobs = guard.parse_jobs(
        'name: X\njobs:\n  a:\n    name: "A"\n  b:\n    runs-on: x\nenv:\n  c:\n    name: C\n'
    )
    assert jobs["a"]["name"] == "A"
    assert jobs["b"]["name"] is None
    assert "c" not in jobs


# --- reporter --------------------------------------------------------------


def _run(
    name: str,
    conclusion: str | None,
    status_: str = "completed",
    *,
    suite: int = 1,
    started: str = "2026-10-03T10:00:00Z",
    app: int = 15368,
    run_id: int = 1,
):
    return {
        "id": run_id,
        "name": name,
        "status": status_,
        "conclusion": conclusion,
        "started_at": started,
        "app": {"id": app},
        "check_suite": {"id": suite},
        "html_url": f"https://example.invalid/{run_id}",
    }


def _all_green() -> list[dict]:
    names = ["Merge Readiness", *(lane["name"] for lane in POLICY["aggregate_lanes"])]
    return [_run(name, "success", run_id=i) for i, name in enumerate(names, 1)]


def _pull(**overrides):
    pull = {
        "number": 7,
        "title": "t",
        "state": "open",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {"sha": SHA, "ref": "feat/x"},
        "base": {"ref": "main"},
    }
    pull.update(overrides)
    return pull


def test_ready_when_everything_green() -> None:
    report = status.evaluate(POLICY, SHA, _all_green(), _pull())
    assert report["verdict"] == "READY"
    assert report["blockers"] == [] and report["waiting"] == []


def test_failed_lane_blocks() -> None:
    runs = _all_green()
    runs[2] = _run(runs[2]["name"], "failure", run_id=99)
    report = status.evaluate(POLICY, SHA, runs)
    assert report["verdict"] == "NOT_READY"


def test_cancelled_and_skipped_are_failures() -> None:
    for conclusion in ("cancelled", "skipped", "timed_out"):
        state = status.classify_run("Unit", [_run("Unit", conclusion)], 15368)
        assert state.state == "failure"


def test_missing_required_check_is_pending() -> None:
    runs = [run for run in _all_green() if run["name"] != "Merge Readiness"]
    report = status.evaluate(POLICY, SHA, runs)
    assert report["verdict"] == "PENDING"
    assert any("Merge Readiness" in item for item in report["waiting"])


def test_wrong_app_does_not_satisfy_required_check() -> None:
    runs = [run for run in _all_green() if run["name"] != "Merge Readiness"]
    runs.append(_run("Merge Readiness", "success", app=42, run_id=77))
    assert (
        status.evaluate(POLICY, SHA, runs)["required_checks"][0]["state"] == "missing"
    )


def test_rerun_supersedes_within_suite() -> None:
    runs = [
        _run("Unit", "failure", started="2026-10-03T10:00:00Z", run_id=1),
        _run("Unit", "success", started="2026-10-03T11:00:00Z", run_id=2),
    ]
    assert status.classify_run("Unit", runs, 15368).state == "success"


def test_same_name_from_other_suite_cannot_mask_failure() -> None:
    runs = [
        _run("Unit", "failure", suite=1, started="2026-10-03T10:00:00Z", run_id=1),
        _run("Unit", "success", suite=2, started="2026-10-03T12:00:00Z", run_id=2),
    ]
    assert status.classify_run("Unit", runs, 15368).state == "failure"


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"draft": True}, "draft"),
        ({"state": "closed"}, "closed"),
        ({"mergeable": False, "mergeable_state": "dirty"}, "conflicts"),
        ({"base": {"ref": "dev"}}, "targets"),
        ({"head": {"sha": "b" * 40, "ref": "feat/x"}}, "historical"),
    ],
)
def test_pr_state_blockers(overrides, fragment: str) -> None:
    report = status.evaluate(POLICY, SHA, _all_green(), _pull(**overrides))
    assert report["verdict"] == "NOT_READY"
    assert any(fragment in item for item in report["blockers"])


def test_behind_branch_is_pending() -> None:
    report = status.evaluate(POLICY, SHA, _all_green(), _pull(mergeable_state="behind"))
    assert report["verdict"] == "PENDING"


def test_protection_states() -> None:
    assert (
        status.evaluate_protection(POLICY, {"protected": False}, None)["state"]
        == "not_enforced"
    )
    assert (
        status.evaluate_protection(POLICY, {"protected": True}, None)["state"]
        == "unknown"
    )
    good = {
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": "Merge Readiness", "app_id": 15368}],
        },
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    assert (
        status.evaluate_protection(POLICY, {"protected": True}, good)["state"]
        == "enforced"
    )
    bad = json.loads(json.dumps(good))
    bad["required_status_checks"]["checks"] = []
    bad["allow_force_pushes"]["enabled"] = True
    result = status.evaluate_protection(POLICY, {"protected": True}, bad)
    assert result["state"] == "mismatch" and "force-pushes" in result["detail"]


class FakeApi:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, path: str):
        self.calls.append(path)
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise status.ApiError(path, 404, "not found")


def test_main_end_to_end_with_fake_api(capsys) -> None:
    api = FakeApi(
        {
            "repos/o/r/pulls/7": _pull(),
            f"repos/o/r/commits/{SHA}/check-runs": {
                "total_count": 6,
                "check_runs": _all_green(),
            },
            "repos/o/r/branches/main/protection": status.ApiError(
                "p", 403, "forbidden"
            ),
            "repos/o/r/branches/main": {"protected": True},
        }
    )
    code = status.main(["--pr", "7", "--repo", "o/r", "--json"], api_get=api)
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report["verdict"] == "READY"
    assert report["protection"]["state"] == "unknown"
    assert all(not call.startswith(("POST", "PUT")) for call in api.calls)


def test_main_reports_api_error(capsys) -> None:
    api = FakeApi({})
    assert status.main(["--ref", "main", "--repo", "o/r"], api_get=api) == 2
    assert "merge-readiness-status" in capsys.readouterr().err


def test_main_rejects_bad_arguments() -> None:
    with pytest.raises(SystemExit):
        status.main(["--sha", "abc"], api_get=FakeApi({}))
    with pytest.raises(SystemExit):
        status.main(["--ref", "../etc"], api_get=FakeApi({}))


def test_pagination_collects_all_pages() -> None:
    first = [_run(f"c{i}", "success", run_id=i) for i in range(100)]
    second = [_run("Unit", "success", run_id=1000)]
    pages = iter(
        [
            {"total_count": 101, "check_runs": first},
            {"total_count": 101, "check_runs": second},
        ]
    )
    runs = status.fetch_check_runs(lambda path: next(pages), "o/r", SHA)
    assert len(runs) == 101


def test_render_text_is_deterministic() -> None:
    report = status.evaluate(POLICY, SHA, _all_green(), _pull())
    report["repo"] = "o/r"
    assert status.render_text(report) == status.render_text(
        json.loads(json.dumps(report))
    )
    assert "READY" in status.render_text(report)
