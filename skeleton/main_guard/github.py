"""GitHub transport for main-guard.

The guard talks to GitHub through a tiny interface, :class:`GitHubTransport`,
with a single production implementation that shells out to the authenticated
``gh api`` CLI.  Tests inject :class:`FakeTransport` so no network is ever used.

Read paths and write paths are deliberately separated:

* :class:`GitHubClient` exposes read helpers only and wraps its transport in a
  :class:`ReadOnlyTransport`, which refuses every non-GET request.
* Mutations (currently only commit comments from the post-push watcher) live in
  :class:`CommentPoster`, which must be constructed explicitly and is only
  reachable behind the watcher's ``--post`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import subprocess
from typing import Any, Callable, Iterator, Mapping, Protocol, Sequence
from urllib.parse import urlencode

DEFAULT_PER_PAGE = 100
DEFAULT_MAX_PAGES = 10


class GitHubError(RuntimeError):
    """A GitHub request failed or returned an unexpected payload."""


class ReadOnlyViolation(GitHubError):
    """A mutating request was attempted through a read-only transport."""


class GitHubTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
    ) -> Any:  # pragma: no cover - protocol
        ...


def build_path(path: str, params: Mapping[str, object] | None = None) -> str:
    """Normalize ``path`` (no leading slash) and append encoded query params."""
    clean = path.lstrip("/")
    if not params:
        return clean
    filtered = {k: v for k, v in params.items() if v is not None}
    if not filtered:
        return clean
    sep = "&" if "?" in clean else "?"
    return f"{clean}{sep}{urlencode(sorted(filtered.items()), doseq=True)}"


class GhCliTransport:
    """Transport that executes ``gh api`` with an explicit argument vector."""

    def __init__(
        self,
        *,
        executable: str = "gh",
        timeout_s: float = 60.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.executable = executable
        self.timeout_s = timeout_s
        self._runner = runner or subprocess.run

    def argv(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
    ) -> list[str]:
        method = method.upper()
        argv = [self.executable, "api", "--method", method, build_path(path, params)]
        argv.extend(["-H", "Accept: application/vnd.github+json"])
        if body is not None:
            argv.extend(["--input", "-"])
        return argv

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
    ) -> Any:
        argv = self.argv(method, path, params=params, body=body)
        try:
            proc = self._runner(
                argv,
                input=json.dumps(body) if body is not None else None,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitHubError(f"gh CLI not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitHubError(f"gh api timed out after {exc.timeout}s: {path}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise GitHubError(f"gh api {method} {path} failed: {detail[-1] if detail else proc.returncode}")
        text = (proc.stdout or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise GitHubError(f"gh api {path} returned non-JSON output") from exc


class ReadOnlyTransport:
    """Wrap a transport and refuse every non-GET request."""

    def __init__(self, inner: GitHubTransport) -> None:
        self.inner = inner

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
    ) -> Any:
        if method.upper() != "GET" or body is not None:
            raise ReadOnlyViolation(f"read-only transport refused {method.upper()} {path}")
        return self.inner.request("GET", path, params=params)


@dataclass
class FakeTransport:
    """In-memory transport for tests.

    ``routes`` maps a normalized path (including sorted query string) or a bare
    path to a payload, or to a callable receiving ``(method, path, params, body)``.
    Every request is appended to ``calls``.
    """

    routes: dict[str, Any] = field(default_factory=dict)
    calls: list[tuple[str, str, dict[str, object] | None, Any]] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
    ) -> Any:
        method = method.upper()
        self.calls.append((method, path.lstrip("/"), dict(params) if params else None, body))
        full = build_path(path, params)
        for key in (f"{method} {full}", full, f"{method} {path.lstrip('/')}", path.lstrip("/")):
            if key in self.routes:
                value = self.routes[key]
                if callable(value):
                    return value(method, path.lstrip("/"), dict(params) if params else {}, body)
                return json.loads(json.dumps(value))
        raise GitHubError(f"FakeTransport: no route for {method} {full}")

    @property
    def methods(self) -> set[str]:
        return {call[0] for call in self.calls}


def _page_items(payload: Any, key: str | None) -> list[Any]:
    if key is None:
        if not isinstance(payload, list):
            raise GitHubError("expected a JSON list page")
        return payload
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise GitHubError(f"expected a JSON object with list field {key!r}")
    return payload[key]


class GitHubClient:
    """Read-only GitHub helpers for one repository slug (``owner/repo``)."""

    def __init__(
        self,
        repo: str,
        transport: GitHubTransport | None = None,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        if not repo or repo.count("/") != 1:
            raise ValueError(f"repository must be 'owner/name', got {repo!r}")
        self.repo = repo
        self.transport = ReadOnlyTransport(transport or GhCliTransport())
        self.max_pages = max(1, int(max_pages))

    def get(self, path: str, params: Mapping[str, object] | None = None) -> Any:
        return self.transport.request("GET", path, params=params)

    def paginate(
        self,
        path: str,
        params: Mapping[str, object] | None = None,
        *,
        key: str | None = None,
        per_page: int = DEFAULT_PER_PAGE,
        limit: int | None = None,
    ) -> Iterator[Any]:
        yielded = 0
        for page in range(1, self.max_pages + 1):
            merged = dict(params or {})
            merged.update({"per_page": per_page, "page": page})
            items = _page_items(self.get(path, merged), key)
            for item in items:
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            if len(items) < per_page:
                return

    # ----------------------------------------------------------- endpoints
    def _r(self, suffix: str) -> str:
        return f"repos/{self.repo}/{suffix.lstrip('/')}"

    def workflow_runs_for_sha(self, sha: str, *, event: str | None = "push") -> list[dict[str, Any]]:
        params: dict[str, object] = {"head_sha": sha}
        if event:
            params["event"] = event
        return list(self.paginate(self._r("actions/runs"), params, key="workflow_runs"))

    def workflow_runs_for_branch(self, branch: str, *, event: str | None = "push",
                                 limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, object] = {"branch": branch}
        if event:
            params["event"] = event
        return list(self.paginate(self._r("actions/runs"), params, key="workflow_runs", limit=limit))

    def run_jobs(self, run_id: int) -> list[dict[str, Any]]:
        return list(self.paginate(self._r(f"actions/runs/{int(run_id)}/jobs"), {"filter": "latest"},
                                  key="jobs"))

    def check_runs_for_sha(self, sha: str, *, check_name: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, object] = {"filter": "latest"}
        if check_name:
            params["check_name"] = check_name
        return list(self.paginate(self._r(f"commits/{sha}/check-runs"), params, key="check_runs"))

    def commit(self, sha: str) -> dict[str, Any]:
        payload = self.get(self._r(f"commits/{sha}"))
        if not isinstance(payload, dict):
            raise GitHubError("commit payload must be an object")
        return payload

    def branch_commits(self, branch: str, *, limit: int = 30) -> list[dict[str, Any]]:
        return list(self.paginate(self._r("commits"), {"sha": branch}, limit=limit))

    def commit_comments(self, sha: str) -> list[dict[str, Any]]:
        return list(self.paginate(self._r(f"commits/{sha}/comments")))

    def open_pulls(self, *, base: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
        params: dict[str, object] = {"state": "open"}
        if base:
            params["base"] = base
        return list(self.paginate(self._r("pulls"), params, limit=limit))

    def pull(self, number: int) -> dict[str, Any]:
        payload = self.get(self._r(f"pulls/{int(number)}"))
        if not isinstance(payload, dict):
            raise GitHubError("pull payload must be an object")
        return payload

    def pull_files(self, number: int, *, limit: int = 3000) -> list[dict[str, Any]]:
        return list(self.paginate(self._r(f"pulls/{int(number)}/files"), limit=limit))

    def pull_commits(self, number: int, *, limit: int = 250) -> list[dict[str, Any]]:
        return list(self.paginate(self._r(f"pulls/{int(number)}/commits"), limit=limit))

    def compare(self, base: str, head: str) -> dict[str, Any]:
        payload = self.get(self._r(f"compare/{base}...{head}"), {"per_page": 1})
        if not isinstance(payload, dict):
            raise GitHubError("compare payload must be an object")
        return payload


class CommentPoster:
    """The only mutating GitHub surface in main-guard: commit comments.

    Constructing a poster is an explicit opt-in; the CLI only does so when the
    operator passes ``--post``.  A hidden marker makes posting idempotent so a
    re-run does not spam the same notice twice.
    """

    MARKER_PREFIX = "<!-- main-guard:notice "

    def __init__(self, repo: str, transport: GitHubTransport) -> None:
        if not repo or repo.count("/") != 1:
            raise ValueError(f"repository must be 'owner/name', got {repo!r}")
        self.repo = repo
        self.transport = transport

    @classmethod
    def marker(cls, key: str) -> str:
        return f"{cls.MARKER_PREFIX}{key} -->"

    def already_posted(self, sha: str, key: str) -> bool:
        reader = GitHubClient(self.repo, self.transport)
        needle = self.marker(key)
        return any(needle in str(c.get("body", "")) for c in reader.commit_comments(sha))

    def post_commit_comment(self, sha: str, body: str, *, key: str) -> dict[str, Any] | None:
        if self.already_posted(sha, key):
            return None
        payload = self.transport.request(
            "POST",
            f"repos/{self.repo}/commits/{sha}/comments",
            body={"body": f"{body.rstrip()}\n\n{self.marker(key)}\n"},
        )
        return payload if isinstance(payload, dict) else {}


def workflow_names(runs: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(r.get("name", "")) for r in runs if r.get("name")})
