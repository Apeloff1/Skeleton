"""Tests for the main-guard post-push watcher (no network: fake GitHub API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.main_guard import cli
from skeleton.main_guard.github import (
    CommentPoster,
    FakeTransport,
    GhCliTransport,
    GitHubClient,
    GitHubError,
    ReadOnlyTransport,
    ReadOnlyViolation,
    build_path,
)
from skeleton.main_guard.gitops import Git
from skeleton.main_guard.notice import render_commit_notice, render_watch_report
from skeleton.main_guard.watcher import (
    ATTR_INHERITED,
    ATTR_INTRODUCED,
    ATTR_RANGE,
    ATTR_UNKNOWN,
    JOB_FAILED,
    JOB_NEUTRAL,
    JOB_PASSED,
    JOB_PENDING,
    PostPushWatcher,
    WatchState,
    commit_info_from_api,
    job_state,
    latest_runs_by_workflow,
    post_notices,
    select_commits,
    settled_prefix,
)
from skeleton.testing.main_guard_test_support import FakeGitHub, commit, init_repo, job


@pytest.fixture()
def history(tmp_path: Path):
    repo = init_repo(tmp_path / "repo")
    shas = [commit(repo, {"a.txt": "0\n"}, "c0 base", author="Alice", email="alice@example.invalid")]
    shas.append(commit(repo, {"a.txt": "1\n"}, "c1 feature", author="Bob",
                       email="1234+bobby@users.noreply.github.com"))
    shas.append(commit(repo, {"b.txt": "2\n"}, "c2 docs", author="Carol", email="carol@example.invalid"))
    shas.append(commit(repo, {"c.txt": "3\n"}, "c3 refactor", author="Dan", email="dan@example.invalid"))
    return repo, shas


def _ci(gh: FakeGitHub, sha: str, backend: str | None, gameforge: str | None = "success",
        *, run_conclusion: str | None = None, status: str = "completed") -> None:
    jobs = []
    if backend is not None:
        jobs.append(job("Backend Test", backend, failed_step="Run in-process backend suite"
                        if backend == "failure" else None))
    if gameforge is not None:
        jobs.append(job("Skeleton GameForge", gameforge,
                        failed_step="Test forge / jeeves / context" if gameforge == "failure" else None))
    conclusion = run_conclusion
    if conclusion is None and status == "completed":
        conclusion = "failure" if "failure" in (backend, gameforge) else "success"
    gh.add_run(sha, "CI/CD", conclusion=conclusion, status=status, jobs=jobs)


def _mr(gh: FakeGitHub, sha: str, lint: str = "success") -> None:
    gh.add_run(sha, "Merge Readiness", conclusion="failure" if lint == "failure" else "success",
               jobs=[job("Lint Type Security", lint, failed_step="Canonical lint" if lint == "failure" else None)])


# ----------------------------------------------------------------- unit
@pytest.mark.parametrize(
    ("status", "conclusion", "expected"),
    [
        ("completed", "success", JOB_PASSED),
        ("completed", "failure", JOB_FAILED),
        ("completed", "timed_out", JOB_FAILED),
        ("completed", "startup_failure", JOB_FAILED),
        ("completed", "cancelled", JOB_NEUTRAL),
        ("completed", "skipped", JOB_NEUTRAL),
        ("in_progress", None, JOB_PENDING),
        ("queued", None, JOB_PENDING),
        ("completed", None, JOB_PENDING),
    ],
)
def test_job_state_mapping(status, conclusion, expected) -> None:
    assert job_state(status, conclusion) == expected


def test_latest_runs_prefers_highest_attempt_then_id() -> None:
    runs = [
        {"id": 5, "name": "CI/CD", "run_attempt": 1},
        {"id": 3, "name": "CI/CD", "run_attempt": 2},
        {"id": 9, "name": "Merge Readiness", "run_attempt": 1},
        {"id": 10, "name": "Merge Readiness", "run_attempt": 1},
        {"id": 11, "name": ""},
    ]
    best = latest_runs_by_workflow(runs)
    assert best["CI/CD"]["id"] == 3
    assert best["Merge Readiness"]["id"] == 10
    assert "" not in best


def test_commit_info_from_api_payload() -> None:
    info = commit_info_from_api({
        "sha": "a" * 40,
        "parents": [{"sha": "b" * 40}],
        "author": {"login": "octo"},
        "commit": {"author": {"name": "Octo Cat", "email": "o@example.invalid", "date": "2026-01-01"},
                   "committer": {"name": "GitHub", "email": "noreply@github.com"},
                   "message": "subject line\n\nbody"},
    })
    assert info.parents == ("b" * 40,)
    assert info.subject == "subject line"
    assert info.author_name == "Octo Cat"


# ----------------------------------------------------------- attribution
def test_new_failure_on_single_commit_is_attributed_to_author(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _ci(gh, shas[1], "failure")
    watcher = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo))
    report = watcher.watch([shas[1]])
    [c] = report.commits
    assert c.verdict == "red-new"
    [failure] = c.failures
    assert failure.attribution == ATTR_INTRODUCED
    assert failure.baseline_sha == shas[0]
    assert failure.job.failed_steps == ("Run in-process backend suite",)
    assert [s.sha for s in failure.suspects] == [shas[1]]
    notice = render_commit_notice(c, report)
    assert "@bobby (Bob)" in notice
    assert "went red with this commit" in notice
    assert "Backend Test" in notice
    assert report.has_new_failures
    assert gh.mutating_calls() == []


def test_failure_after_cancelled_runs_is_reported_as_range_with_bisect_hint(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _ci(gh, shas[1], "cancelled", "cancelled", run_conclusion="cancelled")
    # shas[2] has no CI run at all (docs-only push filtered by paths)
    _ci(gh, shas[3], "failure")
    watcher = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo))
    report = watcher.watch([shas[3]])
    [failure] = report.commits[0].failures
    assert failure.attribution == ATTR_RANGE
    assert [s.sha for s in failure.suspects] == shas[1:]
    notice = render_commit_notice(report.commits[0], report)
    assert "3 commits" in notice
    assert "main_guard_bisect.py --good " + shas[0][:12] in notice
    assert "Carol" in notice and "Dan" in notice


def test_inherited_failure_is_not_blamed_on_new_commit(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[1], "failure")
    _mr(gh, shas[1], "failure")
    _ci(gh, shas[2], "failure", "failure")
    _mr(gh, shas[2], "failure")
    _ci(gh, shas[0], "success", "success")
    watcher = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo))
    report = watcher.watch([shas[2]])
    by_job = {f.job.job: f for f in report.commits[0].failures}
    assert by_job["Backend Test"].attribution == ATTR_INHERITED
    assert by_job["Lint Type Security"].attribution == ATTR_INHERITED
    assert by_job["Skeleton GameForge"].attribution == ATTR_INTRODUCED
    assert report.commits[0].verdict == "red-new"
    # focus jobs sort first
    assert [f.job.job for f in report.commits[0].failures][:2] == ["Backend Test", "Skeleton GameForge"]
    notice = render_commit_notice(report.commits[0], report)
    assert "Inherited reds" in notice


def test_only_inherited_failures_yield_red_inherited_verdict(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[0], "failure")
    _ci(gh, shas[1], "failure")
    report = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo)).watch([shas[1]])
    assert report.commits[0].verdict == "red-inherited"
    assert not report.has_new_failures


def test_unknown_baseline_when_history_has_no_conclusive_result(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[1], "failure")
    watcher = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo), baseline_depth=5)
    report = watcher.watch([shas[1]])
    assert report.commits[0].failures[0].attribution == ATTR_UNKNOWN
    assert report.commits[0].verdict == "red-unknown"
    assert "No conclusive earlier result" in render_commit_notice(report.commits[0])


def test_baseline_depth_limits_walk(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _ci(gh, shas[3], "failure")
    watcher = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo), baseline_depth=2)
    [failure] = watcher.watch([shas[3]]).commits[0].failures
    assert failure.attribution == ATTR_UNKNOWN


def test_pending_and_green_and_missing_workflows(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _mr(gh, shas[0])
    _ci(gh, shas[1], None, None, status="in_progress")
    watcher = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo))
    report = watcher.watch([shas[0], shas[1], shas[2]])
    verdicts = [c.verdict for c in report.commits]
    assert verdicts == ["green", "pending", "no-runs"]
    assert report.commits[1].missing_workflows == ["Merge Readiness"]
    assert settled_prefix(report) == shas[0]
    text = render_watch_report(report)
    assert "No failing watched jobs" in text


def test_skipped_run_does_not_fetch_jobs(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    gh.add_run(shas[0], "CI/CD", conclusion="skipped")
    watcher = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo))
    watcher.watch([shas[0]])
    assert not any(p.endswith("/jobs") for (_m, p, _q, _b) in gh.transport.calls)


def test_unwatched_workflows_are_ignored_and_custom_list_respected(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    gh.add_run(shas[1], "Backend Quality", conclusion="failure", jobs=[job("ruff", "failure")])
    report = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo)).watch([shas[1]])
    assert report.commits[0].failures == []
    report = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo),
                             workflows=["Backend Quality"]).watch([shas[1]])
    assert [f.job.job for f in report.commits[0].failures] == ["ruff"]


def test_commit_resolution_falls_back_to_api_without_local_git() -> None:
    gh = FakeGitHub()
    child, parent = "c" * 40, "p" * 40
    gh.commits[child] = {"sha": child, "parents": [{"sha": parent}],
                         "commit": {"author": {"name": "Remote"}, "message": "remote change"}}
    gh.commits[parent] = {"sha": parent, "parents": [], "commit": {"author": {"name": "Root"}, "message": "r"}}
    _ci(gh, parent, "success")
    _ci(gh, child, "failure")
    report = PostPushWatcher(GitHubClient("o/r", gh.transport), git=None).watch([child])
    assert report.commits[0].failures[0].attribution == ATTR_INTRODUCED
    assert report.commits[0].commit.author_name == "Remote"


def test_report_json_is_serializable(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _ci(gh, shas[1], "failure")
    report = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo)).watch([shas[1]])
    data = json.loads(json.dumps(report.to_dict()))
    assert data["has_new_failures"] is True
    assert data["commits"][0]["failures"][0]["focus"] is True


# ----------------------------------------------------------- selection
def test_select_commits_since_and_last(history) -> None:
    repo, shas = history
    g = Git(repo)
    assert select_commits(g, until="main", since=shas[1]) == shas[2:]
    assert select_commits(g, until="main", last=2) == shas[2:]
    with pytest.raises(Exception):
        select_commits(g, until=shas[1], since=shas[3])


def test_watch_state_round_trip(tmp_path: Path, history) -> None:
    repo, shas = history
    state = WatchState.for_repo(Git(repo), "main")
    assert state.load() is None
    state.save(shas[2])
    assert state.load() == shas[2]
    state.path.write_text("{broken", encoding="utf-8")
    assert state.load() is None


# ------------------------------------------------------------ transport
def test_read_only_transport_refuses_mutation() -> None:
    fake = FakeTransport(routes={"repos/o/r/x": {"ok": True}})
    ro = ReadOnlyTransport(fake)
    assert ro.request("GET", "repos/o/r/x") == {"ok": True}
    for method in ("POST", "PATCH", "PUT", "DELETE"):
        with pytest.raises(ReadOnlyViolation):
            ro.request(method, "repos/o/r/x")
    with pytest.raises(ReadOnlyViolation):
        ro.request("GET", "repos/o/r/x", body={"a": 1})
    assert fake.methods == {"GET"}


def test_client_is_read_only_even_with_mutable_transport() -> None:
    client = GitHubClient("o/r", FakeTransport())
    with pytest.raises(ReadOnlyViolation):
        client.transport.request("POST", "repos/o/r/issues")


def test_client_rejects_bad_slug() -> None:
    with pytest.raises(ValueError):
        GitHubClient("not-a-slug", FakeTransport())


def test_pagination_stops_on_short_page() -> None:
    pages = {1: list(range(100)), 2: list(range(100, 130))}
    fake = FakeTransport(routes={"repos/o/r/items": lambda m, p, q, b: pages.get(int(q["page"]), [])})
    items = list(GitHubClient("o/r", fake).paginate("repos/o/r/items"))
    assert len(items) == 130
    assert len(fake.calls) == 2
    limited = list(GitHubClient("o/r", fake).paginate("repos/o/r/items", limit=5))
    assert limited == [0, 1, 2, 3, 4]


def test_build_path_encodes_sorted_params() -> None:
    assert build_path("/repos/o/r/actions/runs", {"head_sha": "abc", "event": "push", "x": None}) == \
        "repos/o/r/actions/runs?event=push&head_sha=abc"


def test_gh_cli_transport_builds_argv_and_parses_json() -> None:
    seen = {}

    class Proc:
        returncode = 0
        stdout = '{"ok": true}'
        stderr = ""

    def runner(argv, **kwargs):
        seen["argv"] = argv
        seen["input"] = kwargs.get("input")
        return Proc()

    t = GhCliTransport(runner=runner)
    assert t.request("GET", "repos/o/r/commits/abc", params={"per_page": 1}) == {"ok": True}
    assert seen["argv"][:5] == ["gh", "api", "--method", "GET", "repos/o/r/commits/abc?per_page=1"]
    assert seen["input"] is None
    t.request("POST", "repos/o/r/commits/abc/comments", body={"body": "x"})
    assert "--input" in seen["argv"] and json.loads(seen["input"]) == {"body": "x"}


def test_gh_cli_transport_errors() -> None:
    class Bad:
        returncode = 1
        stdout = ""
        stderr = "HTTP 404: Not Found"

    with pytest.raises(GitHubError, match="404"):
        GhCliTransport(runner=lambda argv, **k: Bad()).request("GET", "repos/o/r/x")

    class NotJson:
        returncode = 0
        stdout = "<html>"
        stderr = ""

    with pytest.raises(GitHubError, match="non-JSON"):
        GhCliTransport(runner=lambda argv, **k: NotJson()).request("GET", "repos/o/r/x")


# --------------------------------------------------------------- posting
def test_post_notices_is_idempotent_and_only_for_new_failures(history) -> None:
    repo, shas = history
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _ci(gh, shas[1], "failure")
    _ci(gh, shas[2], "failure")
    report = PostPushWatcher(GitHubClient("o/r", gh.transport), git=Git(repo)).watch([shas[1], shas[2]])
    poster = CommentPoster("o/r", gh.transport)
    receipts = post_notices(report, poster, render_commit_notice)
    assert [r["sha"] for r in receipts] == [shas[1]]  # shas[2] only inherits
    assert receipts[0]["posted"] is True
    assert "main-guard:notice" in gh.comments[shas[1]][0]["body"]
    again = post_notices(report, poster, render_commit_notice)
    assert again[0]["posted"] is False
    assert len(gh.comments[shas[1]]) == 1
    with_inherited = post_notices(report, poster, render_commit_notice, include_inherited=True)
    assert {r["sha"] for r in with_inherited} == {shas[1], shas[2]}


# ------------------------------------------------------------------- CLI
def _cli_repo(history):
    repo, shas = history
    Git(repo).run("remote", "add", "origin", "https://github.com/o/r.git")
    return repo, shas


def test_cli_dry_run_never_mutates(history, capsys) -> None:
    repo, shas = _cli_repo(history)
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _ci(gh, shas[1], "failure")
    code = cli.watch_main(["--repo-dir", str(repo), "--sha", shas[1], "--fail-on-new"],
                         transport_factory=lambda: gh.transport)
    out = capsys.readouterr().out
    assert code == 1
    assert "Dry run: nothing was posted" in out
    assert gh.mutating_calls() == []


def test_cli_post_flag_posts_commit_comment(history, capsys) -> None:
    repo, shas = _cli_repo(history)
    gh = FakeGitHub()
    _ci(gh, shas[0], "success")
    _ci(gh, shas[1], "failure")
    code = cli.watch_main(["--repo-dir", str(repo), "--sha", shas[1], "--post"],
                          transport_factory=lambda: gh.transport)
    assert code == 0
    assert gh.mutating_calls() == [("POST", f"repos/o/r/commits/{shas[1]}/comments")]
    assert "Posted 1 notice(s)" in capsys.readouterr().out


def test_cli_json_and_state(history, capsys, tmp_path: Path) -> None:
    repo, shas = _cli_repo(history)
    gh = FakeGitHub()
    for sha in shas:
        _ci(gh, sha, "success")
    out_file = tmp_path / "report.json"
    code = cli.watch_main(["--repo-dir", str(repo), "--last", "2", "--format", "json", "--update-state",
                           "--output", str(out_file)], transport_factory=lambda: gh.transport)
    assert code == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert [c["commit"]["sha"] for c in data["commits"]] == shas[2:]
    assert WatchState.for_repo(Git(repo), "main").load() == shas[3]
    capsys.readouterr()
    # next run with remembered state selects nothing new -> empty report
    code = cli.watch_main(["--repo-dir", str(repo), "--format", "json"], transport_factory=lambda: gh.transport)
    assert code == 0
    assert json.loads(capsys.readouterr().out)["commits"] == []


def test_cli_reports_errors_with_exit_2(history, capsys) -> None:
    repo, _ = history  # no origin remote -> slug cannot be inferred
    assert cli.watch_main(["--repo-dir", str(repo), "--last", "1"], transport_factory=FakeTransport) == 2
    assert "--repo" in capsys.readouterr().err


def test_dispatcher_help_and_unknown(capsys) -> None:
    assert cli.main(["--help"]) == 0
    assert cli.main(["nope"]) == 2
    assert cli.main([]) == 2
