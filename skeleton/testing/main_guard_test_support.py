"""Shared fixtures for the main-guard test suites.

Everything here is hermetic: temporary git repositories with pinned identities
and dates, and an in-memory GitHub API that never touches the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping

from skeleton.main_guard.github import FakeTransport, build_path

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Committer",
    "GIT_COMMITTER_EMAIL": "committer@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def git_env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(GIT_ENV)
    env["HOME"] = env.get("MAIN_GUARD_TEST_HOME", env.get("HOME", "/tmp"))
    env.update(extra)
    return env


def git(repo: Path, *args: str, check: bool = True, **extra_env: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), env=git_env(**extra_env), capture_output=True,
                          text=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}{proc.stdout}")
    return proc.stdout.strip()


def init_repo(path: Path, *, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", f"--initial-branch={branch}")
    git(path, "config", "user.name", GIT_ENV["GIT_AUTHOR_NAME"])
    git(path, "config", "user.email", GIT_ENV["GIT_AUTHOR_EMAIL"])
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "core.hooksPath", str(path / ".no-hooks"))
    return path


_counter = {"n": 0}


def commit(
    repo: Path,
    files: Mapping[str, str | None],
    message: str,
    *,
    author: str = "Test Author",
    email: str = "author@example.invalid",
) -> str:
    """Write/delete ``files`` then commit; ``None`` deletes a path."""
    for rel, content in files.items():
        target = repo / rel
        if content is None:
            if target.exists():
                git(repo, "rm", "-q", "--", rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        git(repo, "add", "--", rel)
    _counter["n"] += 1
    stamp = f"2026-01-01T00:{_counter['n'] // 60 % 60:02d}:{_counter['n'] % 60:02d}+00:00"
    git(repo, "commit", "-q", "--allow-empty", "-m", message,
        GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    return git(repo, "rev-parse", "HEAD")


def make_bare_remote(tmp: Path, source: Path, *, name: str = "origin", branch: str = "main") -> Path:
    remote = tmp / f"{name}.git"
    git(tmp, "init", "-q", "--bare", f"--initial-branch={branch}", str(remote))
    git(source, "remote", "add", name, str(remote))
    git(source, "push", "-q", name, f"{branch}:{branch}")
    git(source, "branch", "-q", f"--set-upstream-to={name}/{branch}", branch)
    return remote


def clone(remote: Path, dest: Path) -> Path:
    subprocess.run(["git", "clone", "-q", str(remote), str(dest)], env=git_env(), check=True,
                   capture_output=True)
    git(dest, "config", "user.name", GIT_ENV["GIT_AUTHOR_NAME"])
    git(dest, "config", "user.email", GIT_ENV["GIT_AUTHOR_EMAIL"])
    git(dest, "config", "commit.gpgsign", "false")
    git(dest, "config", "core.hooksPath", str(dest / ".no-hooks"))
    return dest


# ------------------------------------------------------------ fake GitHub
@dataclass
class FakeRun:
    run_id: int
    name: str
    sha: str
    status: str = "completed"
    conclusion: str | None = "success"
    attempt: int = 1
    jobs: list[dict[str, Any]] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.run_id,
            "name": self.name,
            "head_sha": self.sha,
            "status": self.status,
            "conclusion": self.conclusion,
            "run_attempt": self.attempt,
            "event": "push",
            "html_url": f"https://github.test/o/r/actions/runs/{self.run_id}",
        }


def job(name: str, conclusion: str | None = "success", *, status: str = "completed",
        failed_step: str | None = None, job_id: int = 0) -> dict[str, Any]:
    steps = [{"name": "Set up job", "conclusion": "success"}]
    if failed_step:
        steps.append({"name": failed_step, "conclusion": "failure"})
    return {
        "id": job_id or abs(hash((name, conclusion, failed_step))) % 10_000_000,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.test/job/{name.replace(' ', '-')}",
        "steps": steps,
    }


class FakeGitHub:
    """Programmable fake of the subset of the REST API main-guard reads."""

    def __init__(self, repo: str = "o/r") -> None:
        self.repo = repo
        self.runs: list[FakeRun] = []
        self.commits: dict[str, dict[str, Any]] = {}
        self.pulls: list[dict[str, Any]] = []
        self.pull_files_map: dict[int, list[dict[str, Any]]] = {}
        self.pull_commits_map: dict[int, list[dict[str, Any]]] = {}
        self.compares: dict[tuple[str, str], dict[str, Any]] = {}
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.transport = FakeTransport()
        self._next_run = 1000
        self.transport.routes = _Router(self)  # type: ignore[assignment]

    def add_run(self, sha: str, name: str, *, conclusion: str | None = "success", status: str = "completed",
                jobs: Iterable[dict[str, Any]] = (), attempt: int = 1) -> FakeRun:
        self._next_run += 1
        run = FakeRun(self._next_run, name, sha, status=status, conclusion=conclusion, attempt=attempt,
                      jobs=list(jobs))
        self.runs.append(run)
        return run

    def mutating_calls(self) -> list[tuple[str, str]]:
        return [(m, p) for (m, p, _q, _b) in self.transport.calls if m != "GET"]


class _Router(dict):
    """Dict-like route table resolving REST paths dynamically."""

    def __init__(self, gh: FakeGitHub) -> None:
        super().__init__()
        self.gh = gh

    def __contains__(self, key: object) -> bool:  # FakeTransport probes several keys
        return isinstance(key, str) and not key.startswith(("GET ", "POST ", "PATCH ", "PUT ", "DELETE ")) \
            and "?" not in key

    def __getitem__(self, key: str) -> Any:
        return self.handle

    def handle(self, method: str, path: str, params: dict[str, object], body: Any) -> Any:
        gh = self.gh
        prefix = f"repos/{gh.repo}/"
        if not path.startswith(prefix):
            raise AssertionError(f"unexpected path {path}")
        rest = path[len(prefix):]
        page = int(params.get("page", 1) or 1)
        per_page = int(params.get("per_page", 100) or 100)

        def paged(items: list[Any]) -> list[Any]:
            start = (page - 1) * per_page
            return items[start:start + per_page]

        if method == "GET" and rest == "actions/runs":
            sha = params.get("head_sha")
            runs = [r.payload() for r in gh.runs if (sha is None or r.sha == sha)]
            return {"total_count": len(runs), "workflow_runs": paged(runs)}
        if method == "GET" and rest.startswith("actions/runs/") and rest.endswith("/jobs"):
            run_id = int(rest.split("/")[2])
            for r in gh.runs:
                if r.run_id == run_id:
                    return {"total_count": len(r.jobs), "jobs": paged(r.jobs)}
            raise AssertionError(f"unknown run {run_id}")
        if rest.startswith("commits/") and rest.endswith("/comments"):
            sha = rest.split("/")[1]
            if method == "GET":
                return paged(gh.comments.get(sha, []))
            if method == "POST":
                comment = {"id": len(gh.comments.get(sha, [])) + 1, "body": body["body"],
                           "html_url": f"https://github.test/commit/{sha}#c"}
                gh.comments.setdefault(sha, []).append(comment)
                return comment
        if method == "GET" and rest.startswith("commits/"):
            sha = rest.split("/")[1]
            if sha in gh.commits:
                return gh.commits[sha]
            raise AssertionError(f"unknown commit {sha}")
        if method == "GET" and rest == "pulls":
            return paged([p for p in gh.pulls if p.get("state", "open") == params.get("state", "open")])
        if method == "GET" and rest.startswith("pulls/"):
            parts = rest.split("/")
            number = int(parts[1])
            if len(parts) == 2:
                for p in gh.pulls:
                    if p["number"] == number:
                        return p
                raise AssertionError(f"unknown pull {number}")
            if parts[2] == "files":
                return paged(gh.pull_files_map.get(number, []))
            if parts[2] == "commits":
                return paged(gh.pull_commits_map.get(number, []))
        if method == "GET" and rest.startswith("compare/"):
            spec = rest[len("compare/"):]
            base, _, head = spec.partition("...")
            if (base, head) in gh.compares:
                return gh.compares[(base, head)]
            raise AssertionError(f"unknown compare {spec}")
        raise AssertionError(f"unhandled {method} {build_path(path, params)}")
