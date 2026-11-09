"""Small, dependency-free git adapter used by every main-guard component.

Every git invocation goes through :class:`Git`, which always passes an explicit
argument vector (never a shell string), pins the working directory, and turns
non-zero exits into :class:`GitError` carrying the captured stderr.  Keeping the
process boundary in one place makes the other modules trivially testable with
temporary repositories and keeps the process-safety posture auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable, Mapping, Sequence

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = "0" * 40
DEFAULT_TIMEOUT_S = 300.0


class GitError(RuntimeError):
    """A git command failed; ``returncode``/``stderr`` describe the failure."""

    def __init__(self, argv: Sequence[str], returncode: int, stdout: str, stderr: str) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        detail = (stderr or stdout).strip().splitlines()
        tail = detail[-1] if detail else "no output"
        super().__init__(f"git {' '.join(self.argv[1:])} failed ({returncode}): {tail}")


@dataclass(frozen=True, slots=True)
class CommitInfo:
    """Identity and attribution for one commit."""

    sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str
    authored_at: str
    subject: str

    @property
    def short(self) -> str:
        return self.sha[:8]

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    def to_dict(self) -> dict[str, object]:
        return {
            "sha": self.sha,
            "parents": list(self.parents),
            "author_name": self.author_name,
            "author_email": self.author_email,
            "committer_name": self.committer_name,
            "committer_email": self.committer_email,
            "authored_at": self.authored_at,
            "subject": self.subject,
        }


_LOG_FORMAT = "%H%x1f%P%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%aI%x1f%s%x1e"


def _parse_log_records(raw: str) -> list[CommitInfo]:
    commits: list[CommitInfo] = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) != 8:
            raise ValueError(f"unexpected git log record with {len(fields)} fields")
        sha, parents, an, ae, cn, ce, at, subject = fields
        commits.append(
            CommitInfo(
                sha=sha,
                parents=tuple(p for p in parents.split() if p),
                author_name=an,
                author_email=ae,
                committer_name=cn,
                committer_email=ce,
                authored_at=at,
                subject=subject,
            )
        )
    return commits


class Git:
    """Run git in one repository with an explicit argument vector."""

    def __init__(
        self,
        repo: str | os.PathLike[str] = ".",
        *,
        env: Mapping[str, str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        executable: str = "git",
    ) -> None:
        self.repo = Path(repo)
        self._env = dict(env) if env is not None else None
        self.timeout_s = timeout_s
        self.executable = executable

    # ------------------------------------------------------------------ core
    def _environment(self) -> dict[str, str]:
        base = dict(os.environ)
        # Never let an interactive editor or pager block automation.
        base.setdefault("GIT_EDITOR", "true")
        base["GIT_PAGER"] = "cat"
        base["GIT_TERMINAL_PROMPT"] = "0"
        if self._env:
            base.update(self._env)
        return base

    def run(
        self,
        *args: str,
        check: bool = True,
        input_text: str | None = None,
        timeout_s: float | None = None,
        strip: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        argv = [self.executable, *args]
        try:
            proc = subprocess.run(
                argv,
                cwd=str(self.repo),
                env=self._environment(),
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout_s or self.timeout_s,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitError(argv, 127, "", f"git executable not found: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitError(argv, 124, "", f"timed out after {exc.timeout}s") from exc
        if check and proc.returncode != 0:
            raise GitError(argv, proc.returncode, proc.stdout, proc.stderr)
        if strip:
            proc.stdout = proc.stdout.strip()
        return proc

    def out(self, *args: str, **kwargs: object) -> str:
        return self.run(*args, **kwargs).stdout  # type: ignore[arg-type]

    def ok(self, *args: str) -> bool:
        return self.run(*args, check=False).returncode == 0

    # --------------------------------------------------------------- queries
    def toplevel(self) -> Path:
        return Path(self.out("rev-parse", "--show-toplevel"))

    def git_dir(self) -> Path:
        raw = self.out("rev-parse", "--git-dir")
        path = Path(raw)
        return path if path.is_absolute() else (self.repo / path).resolve()

    def common_dir(self) -> Path:
        raw = self.out("rev-parse", "--git-common-dir")
        path = Path(raw)
        return path if path.is_absolute() else (self.repo / path).resolve()

    def rev_parse(self, rev: str) -> str:
        return self.out("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")

    def try_rev_parse(self, rev: str) -> str | None:
        proc = self.run("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False)
        return proc.stdout if proc.returncode == 0 and proc.stdout else None

    def head_sha(self) -> str:
        return self.rev_parse("HEAD")

    def current_branch(self) -> str | None:
        """Return the checked-out branch name, or ``None`` when HEAD is detached."""
        proc = self.run("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        return proc.stdout if proc.returncode == 0 and proc.stdout else None

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        proc = self.run("merge-base", "--is-ancestor", ancestor, descendant, check=False)
        if proc.returncode in (0, 1):
            return proc.returncode == 0
        raise GitError(["git", "merge-base", "--is-ancestor", ancestor, descendant], proc.returncode,
                       proc.stdout, proc.stderr)

    def merge_base(self, a: str, b: str) -> str | None:
        proc = self.run("merge-base", a, b, check=False)
        return proc.stdout if proc.returncode == 0 and proc.stdout else None

    def rev_list(
        self,
        spec: Sequence[str],
        *,
        first_parent: bool = False,
        reverse: bool = False,
        ancestry_path: bool = False,
        max_count: int | None = None,
    ) -> list[str]:
        args = ["rev-list"]
        if first_parent:
            args.append("--first-parent")
        if reverse:
            args.append("--reverse")
        if ancestry_path:
            args.append("--ancestry-path")
        if max_count is not None:
            args.append(f"--max-count={int(max_count)}")
        args.extend(spec)
        raw = self.out(*args)
        return [line for line in raw.splitlines() if line]

    def commits(self, revs: Iterable[str]) -> list[CommitInfo]:
        revs = list(revs)
        if not revs:
            return []
        raw = self.out("show", "-s", "--no-walk=unsorted", f"--format={_LOG_FORMAT}", *revs, strip=False)
        return _parse_log_records(raw)

    def commit(self, rev: str) -> CommitInfo:
        found = self.commits([rev])
        if not found:
            raise GitError(["git", "show", rev], 128, "", f"unknown revision {rev}")
        return found[0]

    def changed_files(self, base: str, head: str) -> list[str]:
        raw = self.out("diff", "--name-only", "--no-renames", f"{base}...{head}")
        return sorted({line for line in raw.splitlines() if line})

    def changed_files_between(self, base: str, head: str) -> list[str]:
        """Two-dot diff (tree comparison) between ``base`` and ``head``."""
        raw = self.out("diff", "--name-only", "--no-renames", base, head)
        return sorted({line for line in raw.splitlines() if line})

    def files_in_commit(self, sha: str) -> list[str]:
        raw = self.out("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "-m", sha)
        return sorted({line for line in raw.splitlines() if line})

    def ls_tree_blobs(self, rev: str, paths: Sequence[str] = ()) -> dict[str, str]:
        """Map ``path -> blob sha`` for every blob reachable at ``rev``."""
        raw = self.out("ls-tree", "-r", "-z", "--full-tree", rev, "--", *paths, strip=False)
        blobs: dict[str, str] = {}
        for entry in raw.split("\0"):
            if not entry:
                continue
            meta, _, path = entry.partition("\t")
            parts = meta.split()
            if len(parts) == 3 and parts[1] == "blob":
                blobs[path] = parts[2]
        return blobs

    def ls_files(self, paths: Sequence[str] = ()) -> list[str]:
        raw = self.out("ls-files", "-z", "--", *paths, strip=False)
        return [p for p in raw.split("\0") if p]

    def show_file(self, rev: str, path: str) -> bytes | None:
        proc = subprocess.run(
            [self.executable, "show", f"{rev}:{path}"],
            cwd=str(self.repo),
            env=self._environment(),
            capture_output=True,
            timeout=self.timeout_s,
            check=False,
        )
        return proc.stdout if proc.returncode == 0 else None

    def status_porcelain(self, *, include_untracked: bool = False) -> list[str]:
        args = ["status", "--porcelain=v1"]
        args.append("--untracked-files=normal" if include_untracked else "--untracked-files=no")
        raw = self.out(*args, strip=False)
        return [line for line in raw.splitlines() if line]

    def is_dirty(self, *, include_untracked: bool = False) -> bool:
        return bool(self.status_porcelain(include_untracked=include_untracked))

    def config_get_all(self, key: str) -> list[str]:
        proc = self.run("config", "--get-all", key, check=False)
        if proc.returncode != 0:
            return []
        return [line for line in proc.stdout.splitlines() if line]

    def remote_url(self, remote: str = "origin") -> str | None:
        values = self.config_get_all(f"remote.{remote}.url")
        return values[0] if values else None

    def patch_ids(self, spec: Sequence[str]) -> dict[str, str]:
        """Return ``commit -> stable patch-id`` for the commits in ``spec``."""
        log = self.run("log", "-p", "--no-color", "--no-merges", "--format=commit %H", *spec,
                       strip=False).stdout
        if not log.strip():
            return {}
        pid = self.run("patch-id", "--stable", input_text=log, strip=False).stdout
        result: dict[str, str] = {}
        for line in pid.splitlines():
            parts = line.split()
            if len(parts) == 2:
                result[parts[1]] = parts[0]
        return result

    def cherry(self, upstream: str, head: str) -> list[tuple[str, str]]:
        """Return ``(marker, sha)`` pairs from ``git cherry upstream head``.

        ``-`` means an equivalent change already exists upstream; ``+`` means the
        commit is still unique to ``head``.
        """
        raw = self.out("cherry", upstream, head)
        pairs: list[tuple[str, str]] = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in {"+", "-"}:
                pairs.append((parts[0], parts[1]))
        return pairs


def parse_github_slug(url: str | None) -> str | None:
    """Extract ``owner/repo`` from an https/ssh GitHub remote URL."""
    if not url:
        return None
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def valid_sha(value: object) -> bool:
    return isinstance(value, str) and bool(FULL_SHA.fullmatch(value))
