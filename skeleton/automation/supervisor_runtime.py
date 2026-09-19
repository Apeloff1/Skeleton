"""Immutable execution and worktree guards for autonomous repository builds.

The Supervisor control plane has three privilege tiers:

* Supervisor: observes repository state and produces a bounded plan.
* Secretary: validates custody and deterministically chooses registered workers.
* Worker: may mutate only a narrow source/test/docs surface and may publish only
  through an ordinary pull request.

This module is deliberately dependency-free and model-free. It centralizes the
trust checks shared by all three tiers so that they cannot silently drift apart.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
RUN_ATTEMPT_RE = re.compile(r"^[1-9][0-9]{0,9}$")
BRANCH_RE = re.compile(
    r"^(?!/)(?!.*//)(?!.*\.\.)(?!.*@\{)"
    r"[A-Za-z0-9._/-]{1,180}(?<![./])$"
)
_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")
MAX_CANONICAL_JSON_BYTES = 256_000
MAX_BRANCH_BYTES = 220


class SupervisorRuntimeError(RuntimeError):
    """An immutable-execution or mutation-containment invariant failed."""


def canonical_json(value: object) -> bytes:
    """Serialize stable JSON for hashing and cross-job custody."""
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SupervisorRuntimeError("value is not canonical JSON") from exc
    if len(rendered) > MAX_CANONICAL_JSON_BYTES:
        raise SupervisorRuntimeError("canonical JSON exceeds control-plane budget")
    return rendered


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _validated(
    value: object,
    *,
    label: str,
    pattern: re.Pattern[str],
) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SupervisorRuntimeError(f"invalid {label}")
    return value


def validate_repository(value: object) -> str:
    return _validated(
        value,
        label="repository identity",
        pattern=REPOSITORY_RE,
    )


def validate_sha(value: object, *, label: str = "commit SHA") -> str:
    return _validated(value, label=label, pattern=SHA_RE)


def validate_fingerprint(value: object) -> str:
    return _validated(
        value,
        label="snapshot fingerprint",
        pattern=FINGERPRINT_RE,
    )


def validate_run_id(value: object) -> str:
    return _validated(value, label="workflow run id", pattern=RUN_ID_RE)


def validate_run_attempt(value: object) -> str:
    return _validated(
        value,
        label="workflow run attempt",
        pattern=RUN_ATTEMPT_RE,
    )


def validate_branch(value: object, *, label: str = "branch") -> str:
    if not isinstance(value, str) or BRANCH_RE.fullmatch(value) is None:
        raise SupervisorRuntimeError(f"invalid {label}")
    if value.endswith(".lock"):
        raise SupervisorRuntimeError(f"invalid {label}")
    return value


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    """Identity that must stay constant from Supervisor through worker publish."""

    repository: str
    base_sha: str
    default_branch: str
    run_id: str
    run_attempt: str

    def __post_init__(self) -> None:
        validate_repository(self.repository)
        validate_sha(self.base_sha, label="base SHA")
        validate_branch(self.default_branch, label="default branch")
        validate_run_id(self.run_id)
        validate_run_attempt(self.run_attempt)

    def as_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "base_sha": self.base_sha,
            "default_branch": self.default_branch,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
        }

    @property
    def fingerprint(self) -> str:
        return sha256_json(self.as_dict())

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, str],
        *,
        allow_local_defaults: bool = False,
    ) -> "ExecutionIdentity":
        repository = source.get("GITHUB_REPOSITORY", "").strip()
        base_sha = (
            source.get("SUPERVISOR_BASE_SHA", "").strip()
            or source.get("GITHUB_SHA", "").strip()
        )
        default_branch = source.get("SUPERVISOR_DEFAULT_BRANCH", "").strip()
        run_id = (
            source.get("SUPERVISOR_RUN_ID", "").strip()
            or source.get("GITHUB_RUN_ID", "").strip()
        )
        run_attempt = (
            source.get("SUPERVISOR_RUN_ATTEMPT", "").strip()
            or source.get("GITHUB_RUN_ATTEMPT", "").strip()
        )
        if allow_local_defaults:
            default_branch = default_branch or "main"
            run_id = run_id or "1"
            run_attempt = run_attempt or "1"
        return cls(
            repository=repository,
            base_sha=base_sha,
            default_branch=default_branch,
            run_id=run_id,
            run_attempt=run_attempt,
        )

    @classmethod
    def from_env(
        cls,
        *,
        allow_local_defaults: bool = False,
    ) -> "ExecutionIdentity":
        return cls.from_mapping(
            os.environ,
            allow_local_defaults=allow_local_defaults,
        )


@dataclass(frozen=True, slots=True)
class WorkerCustody:
    """Secretary-issued custody tuple consumed by exactly one registered worker."""

    worker: str
    snapshot_fingerprint: str
    execution: ExecutionIdentity

    def __post_init__(self) -> None:
        if (
            not isinstance(self.worker, str)
            or not self.worker
            or _COMPONENT_RE.sub("-", self.worker) != self.worker
        ):
            raise SupervisorRuntimeError("invalid worker identity")
        validate_fingerprint(self.snapshot_fingerprint)

    @property
    def fingerprint(self) -> str:
        return sha256_json(
            {
                "worker": self.worker,
                "snapshot_fingerprint": self.snapshot_fingerprint,
                "execution": self.execution.as_dict(),
            }
        )


def require_exact_head(
    expected_sha: str,
    *,
    cwd: Path | str = ".",
) -> None:
    """Require the local checkout to be exactly the admitted immutable commit."""
    expected = validate_sha(expected_sha, label="expected checkout SHA")
    try:
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        ).strip()
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise SupervisorRuntimeError("unable to establish checked-out HEAD") from exc
    if actual != expected:
        raise SupervisorRuntimeError(
            "checked-out HEAD differs from admitted base SHA"
        )


def require_clean_worktree(*, cwd: Path | str = ".") -> None:
    """Refuse to build on top of unaccounted runner mutations."""
    try:
        status = subprocess.check_output(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise SupervisorRuntimeError("unable to inspect worktree cleanliness") from exc
    if status.strip():
        raise SupervisorRuntimeError(
            "worker checkout is not clean before mutation"
        )


def remote_default_head(
    execution: ExecutionIdentity,
    *,
    timeout: int = 30,
) -> str:
    """Resolve the current remote default-branch SHA with authenticated GitHub CLI."""
    endpoint = (
        f"repos/{execution.repository}/git/ref/heads/"
        f"{execution.default_branch}"
    )
    try:
        raw = subprocess.check_output(
            ["gh", "api", endpoint, "--jq", ".object.sha"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        ).strip()
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise SupervisorRuntimeError(
            "unable to resolve remote default branch"
        ) from exc
    return validate_sha(raw, label="remote default-branch SHA")


def require_remote_base_unchanged(execution: ExecutionIdentity) -> None:
    """Abort instead of publishing a proposal against stale observed state."""
    if remote_default_head(execution) != execution.base_sha:
        raise SupervisorRuntimeError(
            "default branch advanced after Supervisor observation"
        )


def _safe_component(value: str, *, fallback: str) -> str:
    cleaned = _COMPONENT_RE.sub("-", value).strip(".-")
    return cleaned[:48] or fallback


def worker_branch_prefix(worker: str) -> str:
    """Return the deterministic namespace owned by one registered specialist."""
    if not isinstance(worker, str) or not worker:
        raise SupervisorRuntimeError("invalid worker identity")
    component = _safe_component(worker, fallback="worker")
    return validate_branch(
        f"bot/specialist-{component}-",
        label="worker branch prefix",
    )


def deterministic_worker_branch(custody: WorkerCustody) -> str:
    """Derive one stable branch per worker and immutable default-branch base.

    Snapshot identity remains in custody and PR evidence, but not in the branch
    name. Repository observations can change while the default branch is still
    the same commit; converging those observations onto one worker branch avoids
    duplicate autonomous PRs for the same source base.
    """
    branch = (
        f"{worker_branch_prefix(custody.worker)}"
        f"{custody.execution.base_sha[:16]}"
    )
    if len(branch.encode("utf-8")) > MAX_BRANCH_BYTES:
        raise SupervisorRuntimeError(
            "derived worker branch exceeds byte budget"
        )
    return validate_branch(branch, label="derived worker branch")


def remote_branch_exists(
    branch: str,
    *,
    cwd: Path | str = ".",
) -> bool:
    branch = validate_branch(branch)
    try:
        raw = subprocess.check_output(
            [
                "git",
                "ls-remote",
                "--heads",
                "origin",
                f"refs/heads/{branch}",
            ],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise SupervisorRuntimeError(
            "unable to inspect remote worker branch"
        ) from exc
    return bool(raw.strip())


def _open_pull_requests(
    repository: str,
) -> list[dict[str, Any]]:
    """Return a bounded same-repository view of open pull requests.

    The REST payload includes head repository identity, unlike a branch-name-only
    lookup. This prevents a fork from suppressing an autonomous worker merely by
    choosing a colliding head branch name.
    """
    validate_repository(repository)
    try:
        raw = subprocess.check_output(
            [
                "gh",
                "api",
                "-X",
                "GET",
                f"repos/{repository}/pulls",
                "-f",
                "state=open",
                "-f",
                "per_page=100",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        value = json.loads(raw)
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ) as exc:
        raise SupervisorRuntimeError(
            "unable to inspect active pull requests"
        ) from exc

    if not isinstance(value, list):
        raise SupervisorRuntimeError(
            "active pull request query returned invalid shape"
        )
    if len(value) >= 100:
        raise SupervisorRuntimeError(
            "active pull request set exceeds bounded query"
        )

    records: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        head = item.get("head")
        base = item.get("base")
        if not isinstance(head, dict) or not isinstance(base, dict):
            continue
        head_repo = head.get("repo")
        if not isinstance(head_repo, dict):
            continue
        if head_repo.get("full_name") != repository:
            continue
        head_ref = head.get("ref")
        base_ref = base.get("ref")
        number = item.get("number")
        if (
            not isinstance(head_ref, str)
            or not isinstance(base_ref, str)
            or isinstance(number, bool)
            or not isinstance(number, int)
        ):
            continue
        records.append(
            {
                "number": number,
                "url": item.get("html_url"),
                "headRefName": head_ref,
                "baseRefName": base_ref,
                "isDraft": bool(item.get("draft", False)),
                "updatedAt": item.get("updated_at"),
            }
        )
    return records


def find_open_pr_for_head(
    repository: str,
    branch: str,
) -> dict[str, Any] | None:
    """Return the unique same-repository open PR using an exact worker branch."""
    validate_branch(branch)
    records = [
        item
        for item in _open_pull_requests(repository)
        if item["headRefName"] == branch
    ]
    if len(records) > 1:
        raise SupervisorRuntimeError(
            "multiple open pull requests share worker branch"
        )
    return records[0] if records else None


def find_open_pr_for_worker(
    repository: str,
    worker: str,
) -> dict[str, Any] | None:
    """Return the unique same-repository PR owned by a specialist namespace."""
    prefix = worker_branch_prefix(worker)
    records = [
        item
        for item in _open_pull_requests(repository)
        if item["headRefName"].startswith(prefix)
    ]
    if len(records) > 1:
        raise SupervisorRuntimeError(
            "specialist has multiple active autonomous pull requests"
        )
    return records[0] if records else None

def proposal_digest(
    *,
    worker: str,
    snapshot_fingerprint: str,
    files: Sequence[Mapping[str, str]],
) -> str:
    """Hash admitted proposal contents without evaluating them."""
    validate_fingerprint(snapshot_fingerprint)
    payload: list[dict[str, str]] = []
    for item in files:
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise SupervisorRuntimeError(
                "proposal digest received invalid file entry"
            )
        payload.append(
            {
                "path": path,
                "content_sha256": hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest(),
            }
        )
    return sha256_json(
        {
            "worker": worker,
            "snapshot_fingerprint": snapshot_fingerprint,
            "files": payload,
        }
    )


def _lexical_repo_path(path: object) -> PurePosixPath:
    if not isinstance(path, str) or not path:
        raise SupervisorRuntimeError("empty mutation path")
    if "\\" in path or "\x00" in path or path.startswith("/"):
        raise SupervisorRuntimeError("invalid mutation path encoding")
    candidate = PurePosixPath(path)
    if candidate.is_absolute():
        raise SupervisorRuntimeError("absolute mutation path rejected")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise SupervisorRuntimeError("mutation path traversal rejected")
    return candidate


def resolve_mutation_target(
    path: object,
    *,
    repo_root: Path,
    allowed_prefixes: Sequence[str],
    blocked_prefixes: Sequence[str],
) -> Path:
    """Resolve one target while rejecting symlinks and repository escape."""
    candidate = _lexical_repo_path(path)
    logical = candidate.as_posix()

    if any(logical.startswith(prefix) for prefix in blocked_prefixes):
        raise SupervisorRuntimeError(
            "mutation path targets blocked control plane"
        )
    if not any(logical.startswith(prefix) for prefix in allowed_prefixes):
        raise SupervisorRuntimeError(
            "mutation path is outside specialist authority"
        )

    root = repo_root.resolve(strict=True)
    current = root
    for part in candidate.parts[:-1]:
        current = current / part
        if current.exists() or current.is_symlink():
            try:
                mode = current.lstat().st_mode
            except OSError as exc:
                raise SupervisorRuntimeError(
                    "cannot inspect mutation parent"
                ) from exc
            if stat.S_ISLNK(mode):
                raise SupervisorRuntimeError(
                    "symlinked mutation parent rejected"
                )
            if not stat.S_ISDIR(mode):
                raise SupervisorRuntimeError(
                    "mutation parent is not a directory"
                )

    target = root.joinpath(*candidate.parts)
    if target.exists() or target.is_symlink():
        try:
            mode = target.lstat().st_mode
        except OSError as exc:
            raise SupervisorRuntimeError(
                "cannot inspect mutation target"
            ) from exc
        if stat.S_ISLNK(mode):
            raise SupervisorRuntimeError(
                "symlink mutation target rejected"
            )
        if not stat.S_ISREG(mode):
            raise SupervisorRuntimeError(
                "mutation target is not a regular file"
            )

    resolved_parent = target.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise SupervisorRuntimeError(
            "mutation target escapes repository"
        ) from exc
    return target


def validate_staged_paths(
    expected: Sequence[str],
    *,
    cwd: Path | str = ".",
) -> None:
    """Require staged paths and git object modes to equal the admitted proposal."""
    admitted = sorted(expected)
    if len(admitted) != len(set(admitted)):
        raise SupervisorRuntimeError(
            "duplicate admitted staged path"
        )
    try:
        staged = subprocess.check_output(
            [
                "git",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=ACMR",
            ],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=20,
        ).splitlines()
        raw_modes = subprocess.check_output(
            [
                "git",
                "diff",
                "--cached",
                "--raw",
                "--no-abbrev",
            ],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=20,
        ).splitlines()
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise SupervisorRuntimeError(
            "unable to verify staged proposal"
        ) from exc

    if sorted(staged) != admitted:
        raise SupervisorRuntimeError(
            "staged mutation set differs from admitted proposal"
        )

    for line in raw_modes:
        if not line.startswith(":"):
            continue
        metadata, _tab, path = line.partition("\t")
        fields = metadata.split()
        if len(fields) < 5:
            raise SupervisorRuntimeError(
                "cannot parse staged git mode"
            )
        new_mode = fields[1]
        if new_mode not in {"100644", "100755"}:
            raise SupervisorRuntimeError(
                f"staged path has forbidden git mode: {path or '<unknown>'}"
            )


def safe_write_text(target: Path, content: str) -> None:
    """Write text without following an existing destination symlink."""
    if not isinstance(content, str):
        raise SupervisorRuntimeError(
            "mutation content must be text"
        )
    target.parent.mkdir(parents=True, exist_ok=True)

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
    except OSError as exc:
        raise SupervisorRuntimeError(
            "unable to open mutation target safely"
        ) from exc

    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(target, 0o644)



WORKER_RESULT_STATUSES = frozenset({
    "existing-pr",
    "no-change",
    "pull-request-created",
})
MAX_WORKER_RESULT_BYTES = 16_384


def parse_worker_result(output: object, *, worker: str) -> dict[str, Any]:
    """Admit one bounded machine-readable worker result.

    Worker stdout is an untrusted process boundary. Only the final non-empty
    line may become evidence, and only a closed set of status/identity fields is
    retained. Raw model/provider output is never propagated to the Secretary.
    """
    if not isinstance(output, str):
        raise SupervisorRuntimeError("worker result output must be text")
    encoded = output.encode("utf-8")
    if len(encoded) > MAX_WORKER_RESULT_BYTES:
        raise SupervisorRuntimeError("worker result exceeds evidence budget")
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise SupervisorRuntimeError("worker emitted no result evidence")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise SupervisorRuntimeError("worker result is not JSON") from exc
    if not isinstance(value, dict):
        raise SupervisorRuntimeError("worker result must be an object")
    if value.get("bot") != worker:
        raise SupervisorRuntimeError("worker result identity mismatch")
    status = value.get("status")
    if status not in WORKER_RESULT_STATUSES:
        raise SupervisorRuntimeError("worker result status is not admitted")

    admitted: dict[str, Any] = {"status": status, "bot": worker}
    for key in (
        "branch",
        "parse_worker_result",
    "proposal_digest",
        "base_sha",
        "supervisor_snapshot_fingerprint",
        "execution_fingerprint",
        "build_task_digest",
    ):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or len(item) > 220:
                raise SupervisorRuntimeError(
                    f"invalid worker result field: {key}"
                )
            admitted[key] = item
    for key in ("pull_request", "changed_lines", "build_issue_number"):
        item = value.get(key)
        if item is not None:
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise SupervisorRuntimeError(
                    f"invalid worker result field: {key}"
                )
            admitted[key] = item

    # Evidence that claims a mutation must carry the immutable custody proofs
    # needed to correlate the remote proposal with this exact execution.
    if status == "pull-request-created":
        required = (
            "branch",
            "proposal_digest",
            "base_sha",
            "supervisor_snapshot_fingerprint",
            "execution_fingerprint",
            "changed_lines",
        )
        missing = [key for key in required if key not in admitted]
        if missing:
            raise SupervisorRuntimeError(
                "created-PR evidence is missing custody proof"
            )
        validate_branch(admitted["branch"], label="worker evidence branch")
        validate_fingerprint(admitted["proposal_digest"])
        validate_sha(admitted["base_sha"], label="worker evidence base SHA")
        validate_fingerprint(admitted["supervisor_snapshot_fingerprint"])
        validate_fingerprint(admitted["execution_fingerprint"])
    elif status == "existing-pr":
        if "pull_request" not in admitted:
            raise SupervisorRuntimeError(
                "existing-PR evidence is missing pull request identity"
            )
        if "branch" in admitted:
            validate_branch(admitted["branch"], label="worker evidence branch")
    return admitted


def validate_worker_evidence_custody(
    evidence: Mapping[str, Any],
    custody: WorkerCustody,
) -> None:
    """Bind admitted worker evidence back to Secretary-issued custody."""
    if evidence.get("bot") != custody.worker:
        raise SupervisorRuntimeError("worker evidence custody mismatch")
    status = evidence.get("status")
    if status == "pull-request-created":
        if evidence.get("base_sha") != custody.execution.base_sha:
            raise SupervisorRuntimeError("worker evidence base mismatch")
        if (
            evidence.get("supervisor_snapshot_fingerprint")
            != custody.snapshot_fingerprint
        ):
            raise SupervisorRuntimeError("worker evidence snapshot mismatch")
        if evidence.get("execution_fingerprint") != custody.execution.fingerprint:
            raise SupervisorRuntimeError("worker evidence execution mismatch")
        expected_branch = deterministic_worker_branch(custody)
        if evidence.get("branch") != expected_branch:
            raise SupervisorRuntimeError("worker evidence branch mismatch")


def sanitized_worker_env(
    source: Mapping[str, str],
) -> dict[str, str]:
    """Remove process-injection variables while retaining required credentials."""
    result = dict(source)
    for key in (
        "PYTHONINSPECT",
        "PYTHONSTARTUP",
        "PYTHONBREAKPOINT",
        "BASH_ENV",
        "ENV",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
    ):
        result.pop(key, None)
    return result


__all__ = [
    "ExecutionIdentity",
    "FINGERPRINT_RE",
    "REPOSITORY_RE",
    "SHA_RE",
    "SupervisorRuntimeError",
    "WorkerCustody",
    "canonical_json",
    "deterministic_worker_branch",
    "find_open_pr_for_head",
    "find_open_pr_for_worker",
    "proposal_digest",
    "remote_branch_exists",
    "remote_default_head",
    "require_clean_worktree",
    "require_exact_head",
    "require_remote_base_unchanged",
    "resolve_mutation_target",
    "safe_write_text",
    "sanitized_worker_env",
    "sha256_json",
    "validate_branch",
    "validate_fingerprint",
    "validate_repository",
    "validate_run_attempt",
    "validate_run_id",
    "validate_sha",
    "validate_staged_paths",
    "validate_worker_evidence_custody",
    "worker_branch_prefix",
]
