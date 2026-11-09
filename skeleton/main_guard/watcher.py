"""Post-push watcher for direct-to-main commits.

For every new commit on ``main`` the watcher collects the push-triggered
workflow runs (by default ``Merge Readiness`` and ``CI/CD``, whose jobs include
``Backend Test`` and ``Skeleton GameForge``), expands failing runs into their
failing jobs and steps, and attributes each failure to a commit and author.

Attribution walks first-parent history: a job that is red on a commit but green
on the nearest ancestor with a conclusive result is *introduced* somewhere in
that range (exactly the commit when the range has one element); a job that was
already red on the ancestor is *inherited* (pre-existing).  Because CI uses
``cancel-in-progress`` concurrency, intermediate commits frequently have only
cancelled runs, so ranges with several suspects are common; the notice then
recommends the bisect helper with a ready-to-run command.

The watcher is read-only by default.  Rendering never posts; posting commit
comments requires an explicit :class:`~skeleton.main_guard.github.CommentPoster`
which the CLI only builds behind ``--post``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .github import CommentPoster, GitHubClient, GitHubError
from .gitops import CommitInfo, Git, GitError

DEFAULT_WATCHED_WORKFLOWS: tuple[str, ...] = ("Merge Readiness", "CI/CD")
FOCUS_JOBS: tuple[str, ...] = ("Backend Test", "Skeleton GameForge")
FAILURE_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure", "action_required"})
SUCCESS_CONCLUSIONS = frozenset({"success"})
NEUTRAL_CONCLUSIONS = frozenset({"skipped", "neutral", "cancelled", "stale"})
PENDING_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})

JOB_FAILED = "failed"
JOB_PASSED = "passed"
JOB_PENDING = "pending"
JOB_NEUTRAL = "neutral"

ATTR_INTRODUCED = "introduced"
ATTR_RANGE = "introduced-in-range"
ATTR_INHERITED = "inherited"
ATTR_UNKNOWN = "unknown-baseline"


def job_state(status: str | None, conclusion: str | None) -> str:
    """Collapse GitHub's ``status``/``conclusion`` pair into a guard state."""
    if (status or "") in PENDING_STATUSES or (status == "completed" and conclusion is None):
        return JOB_PENDING
    if conclusion in FAILURE_CONCLUSIONS:
        return JOB_FAILED
    if conclusion in SUCCESS_CONCLUSIONS:
        return JOB_PASSED
    return JOB_NEUTRAL


@dataclass(frozen=True, slots=True)
class JobResult:
    workflow: str
    run_id: int
    run_attempt: int
    run_url: str
    job: str
    job_id: int
    state: str
    conclusion: str | None
    url: str
    failed_steps: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        return (self.workflow, self.job)

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "run_url": self.run_url,
            "job": self.job,
            "job_id": self.job_id,
            "state": self.state,
            "conclusion": self.conclusion,
            "url": self.url,
            "failed_steps": list(self.failed_steps),
        }


@dataclass(frozen=True, slots=True)
class RunSummary:
    workflow: str
    run_id: int
    run_attempt: int
    state: str
    conclusion: str | None
    url: str

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "state": self.state,
            "conclusion": self.conclusion,
            "url": self.url,
        }


@dataclass(slots=True)
class Failure:
    job: JobResult
    attribution: str
    baseline_sha: str | None = None
    suspects: list[CommitInfo] = field(default_factory=list)

    @property
    def focus(self) -> bool:
        return self.job.job in FOCUS_JOBS

    def to_dict(self) -> dict[str, object]:
        return {
            **self.job.to_dict(),
            "attribution": self.attribution,
            "baseline_sha": self.baseline_sha,
            "focus": self.focus,
            "suspects": [c.to_dict() for c in self.suspects],
        }


@dataclass(slots=True)
class CommitReport:
    commit: CommitInfo
    runs: list[RunSummary] = field(default_factory=list)
    jobs: list[JobResult] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    missing_workflows: list[str] = field(default_factory=list)

    @property
    def pending(self) -> bool:
        return any(r.state == JOB_PENDING for r in self.runs) or any(j.state == JOB_PENDING for j in self.jobs)

    @property
    def new_failures(self) -> list[Failure]:
        return [f for f in self.failures if f.attribution in (ATTR_INTRODUCED, ATTR_RANGE)]

    @property
    def inherited_failures(self) -> list[Failure]:
        return [f for f in self.failures if f.attribution == ATTR_INHERITED]

    @property
    def verdict(self) -> str:
        if self.new_failures:
            return "red-new"
        if self.failures and all(f.attribution == ATTR_INHERITED for f in self.failures):
            return "red-inherited"
        if self.failures:
            return "red-unknown"
        if self.pending:
            return "pending"
        if not self.runs:
            return "no-runs"
        return "green"

    def notice_key(self) -> str:
        material = json.dumps(
            sorted((f.job.workflow, f.job.job, f.attribution) for f in self.failures),
            separators=(",", ":"),
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
        return f"{self.commit.sha}:{digest}"

    def to_dict(self) -> dict[str, object]:
        return {
            "commit": self.commit.to_dict(),
            "verdict": self.verdict,
            "runs": [r.to_dict() for r in self.runs],
            "failures": [f.to_dict() for f in self.failures],
            "missing_workflows": list(self.missing_workflows),
        }


@dataclass(slots=True)
class WatchReport:
    repo: str
    branch: str
    commits: list[CommitReport] = field(default_factory=list)

    @property
    def has_new_failures(self) -> bool:
        return any(c.new_failures for c in self.commits)

    def to_dict(self) -> dict[str, object]:
        return {
            "repo": self.repo,
            "branch": self.branch,
            "has_new_failures": self.has_new_failures,
            "commits": [c.to_dict() for c in self.commits],
        }


def latest_runs_by_workflow(runs: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Keep the newest attempt of each workflow (highest ``run_attempt`` then id)."""
    best: dict[str, Mapping[str, Any]] = {}
    for run in runs:
        name = str(run.get("name") or "")
        if not name:
            continue
        rank = (int(run.get("run_attempt") or 1), int(run.get("id") or 0))
        current = best.get(name)
        if current is None or rank > (int(current.get("run_attempt") or 1), int(current.get("id") or 0)):
            best[name] = run
    return best


def _failed_steps(job: Mapping[str, Any]) -> tuple[str, ...]:
    steps = job.get("steps") or []
    names = [
        str(step.get("name"))
        for step in steps
        if isinstance(step, Mapping) and step.get("conclusion") in FAILURE_CONCLUSIONS and step.get("name")
    ]
    return tuple(names)


class CommitResolver:
    """Resolve commit identity locally when possible, else through the API."""

    def __init__(self, git: Git | None, client: GitHubClient | None) -> None:
        self.git = git
        self.client = client
        self._cache: dict[str, CommitInfo] = {}

    def get(self, sha: str) -> CommitInfo:
        if sha in self._cache:
            return self._cache[sha]
        info: CommitInfo | None = None
        if self.git is not None:
            try:
                info = self.git.commit(sha)
            except (GitError, ValueError):
                info = None
        if info is None and self.client is not None:
            info = commit_info_from_api(self.client.commit(sha))
        if info is None:
            raise GitHubError(f"cannot resolve commit {sha}")
        self._cache[info.sha] = info
        self._cache[sha] = info
        return info

    def first_parent(self, sha: str) -> str | None:
        info = self.get(sha)
        return info.parents[0] if info.parents else None


def commit_info_from_api(payload: Mapping[str, Any]) -> CommitInfo:
    commit = payload.get("commit") or {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    login = (payload.get("author") or {}).get("login") if isinstance(payload.get("author"), Mapping) else None
    message = str(commit.get("message") or "")
    return CommitInfo(
        sha=str(payload.get("sha") or ""),
        parents=tuple(str(p.get("sha")) for p in payload.get("parents") or [] if isinstance(p, Mapping)),
        author_name=str(author.get("name") or login or "unknown"),
        author_email=str(author.get("email") or ""),
        committer_name=str(committer.get("name") or ""),
        committer_email=str(committer.get("email") or ""),
        authored_at=str(author.get("date") or ""),
        subject=message.splitlines()[0] if message else "",
    )


class PostPushWatcher:
    """Collect CI evidence for commits on a branch and attribute failures."""

    def __init__(
        self,
        client: GitHubClient,
        *,
        git: Git | None = None,
        branch: str = "main",
        workflows: Sequence[str] = DEFAULT_WATCHED_WORKFLOWS,
        baseline_depth: int = 25,
        event: str | None = "push",
    ) -> None:
        self.client = client
        self.git = git
        self.branch = branch
        self.workflows = tuple(workflows)
        self.baseline_depth = max(1, int(baseline_depth))
        self.event = event
        self.commits = CommitResolver(git, client)
        self._jobs_cache: dict[str, tuple[list[RunSummary], list[JobResult]]] = {}

    # --------------------------------------------------------------- evidence
    def evidence(self, sha: str) -> tuple[list[RunSummary], list[JobResult]]:
        """Return watched run summaries and their job results for ``sha``."""
        if sha in self._jobs_cache:
            return self._jobs_cache[sha]
        runs = self.client.workflow_runs_for_sha(sha, event=self.event)
        latest = latest_runs_by_workflow(runs)
        summaries: list[RunSummary] = []
        jobs: list[JobResult] = []
        for name in self.workflows:
            run = latest.get(name)
            if run is None:
                continue
            run_id = int(run.get("id") or 0)
            state = job_state(run.get("status"), run.get("conclusion"))
            summaries.append(
                RunSummary(
                    workflow=name,
                    run_id=run_id,
                    run_attempt=int(run.get("run_attempt") or 1),
                    state=state,
                    conclusion=run.get("conclusion"),
                    url=str(run.get("html_url") or ""),
                )
            )
            if state == JOB_NEUTRAL and run.get("conclusion") == "skipped":
                continue
            for job in self.client.run_jobs(run_id):
                jobs.append(
                    JobResult(
                        workflow=name,
                        run_id=run_id,
                        run_attempt=int(run.get("run_attempt") or 1),
                        run_url=str(run.get("html_url") or ""),
                        job=str(job.get("name") or ""),
                        job_id=int(job.get("id") or 0),
                        state=job_state(job.get("status"), job.get("conclusion")),
                        conclusion=job.get("conclusion"),
                        url=str(job.get("html_url") or ""),
                        failed_steps=_failed_steps(job),
                    )
                )
        self._jobs_cache[sha] = (summaries, jobs)
        return summaries, jobs

    def job_state_at(self, sha: str, key: tuple[str, str]) -> str | None:
        _, jobs = self.evidence(sha)
        for job in jobs:
            if job.key == key:
                return job.state
        return None

    def find_baseline(self, sha: str, key: tuple[str, str]) -> tuple[str | None, str | None, list[str]]:
        """Walk first parents from ``sha`` for a conclusive state of ``key``.

        Returns ``(baseline_sha, baseline_state, skipped)`` where ``skipped``
        lists the inconclusive commits walked through (newest first).  The
        baseline is ``None`` when no conclusive state was found in depth.
        """
        skipped: list[str] = []
        current = self.commits.first_parent(sha)
        for _ in range(self.baseline_depth):
            if current is None:
                break
            state = self.job_state_at(current, key)
            if state in (JOB_PASSED, JOB_FAILED):
                return current, state, skipped
            skipped.append(current)
            current = self.commits.first_parent(current)
        return None, None, skipped

    def attribute(self, sha: str, job: JobResult) -> Failure:
        baseline, state, skipped = self.find_baseline(sha, job.key)
        if baseline is None:
            return Failure(job=job, attribution=ATTR_UNKNOWN, suspects=[self.commits.get(sha)])
        if state == JOB_FAILED:
            return Failure(job=job, attribution=ATTR_INHERITED, baseline_sha=baseline,
                           suspects=[])
        suspects = [self.commits.get(s) for s in reversed(skipped)] + [self.commits.get(sha)]
        attribution = ATTR_INTRODUCED if len(suspects) == 1 else ATTR_RANGE
        return Failure(job=job, attribution=attribution, baseline_sha=baseline, suspects=suspects)

    def inspect(self, sha: str) -> CommitReport:
        commit = self.commits.get(sha)
        runs, jobs = self.evidence(commit.sha)
        report = CommitReport(commit=commit, runs=runs, jobs=jobs)
        seen = {r.workflow for r in runs}
        report.missing_workflows = [w for w in self.workflows if w not in seen]
        for job in jobs:
            if job.state == JOB_FAILED:
                report.failures.append(self.attribute(commit.sha, job))
        report.failures.sort(key=lambda f: (not f.focus, f.job.workflow, f.job.job))
        return report

    def watch(self, shas: Sequence[str]) -> WatchReport:
        report = WatchReport(repo=self.client.repo, branch=self.branch)
        for sha in shas:
            report.commits.append(self.inspect(sha))
        return report


# ---------------------------------------------------------------- selection
def select_commits(
    git: Git,
    *,
    until: str,
    since: str | None = None,
    last: int | None = None,
) -> list[str]:
    """Return first-parent commits oldest-first in ``(since, until]`` or the last N."""
    if since:
        if not git.is_ancestor(since, until):
            raise GitError(["git", "merge-base", "--is-ancestor", since, until], 1, "",
                           f"{since} is not an ancestor of {until}")
        return git.rev_list([f"{since}..{until}"], first_parent=True, reverse=True)
    count = max(1, int(last or 5))
    return list(reversed(git.rev_list([until], first_parent=True, max_count=count)))


class WatchState:
    """Persist the last fully-evaluated commit so re-runs only see new pushes."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def for_repo(cls, git: Git, branch: str) -> "WatchState":
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in branch)
        return cls(git.common_dir() / "main_guard" / f"watch-{safe}.json")

    def load(self) -> str | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = data.get("last_evaluated_sha") if isinstance(data, dict) else None
        return value if isinstance(value, str) and len(value) == 40 else None

    def save(self, sha: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_evaluated_sha": sha}, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


def settled_prefix(report: WatchReport) -> str | None:
    """Newest commit such that it and every older commit is no longer pending."""
    last: str | None = None
    for commit in report.commits:
        if commit.pending:
            break
        last = commit.commit.sha
    return last


def post_notices(
    report: WatchReport,
    poster: CommentPoster,
    render: Any,
    *,
    include_inherited: bool = False,
) -> list[dict[str, object]]:
    """Post one commit comment per commit with new failures (idempotent)."""
    receipts: list[dict[str, object]] = []
    for commit in report.commits:
        if not commit.new_failures and not (include_inherited and commit.failures):
            continue
        body = render(commit, report)
        result = poster.post_commit_comment(commit.commit.sha, body, key=commit.notice_key())
        receipts.append({
            "sha": commit.commit.sha,
            "posted": result is not None,
            "url": (result or {}).get("html_url") if isinstance(result, dict) else None,
        })
    return receipts
