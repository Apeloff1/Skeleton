"""Bounded lifecycle inspection for autonomous feature-build pull requests.

A feature builder may continue an existing autonomous PR only when repository
state proves that the PR belongs to the exact same approved build task. This
module is read-only: it validates PR identity, changed paths, immutable head
identity, and completed CI results, then returns bounded failure evidence.

No check output is executed. Check output is untrusted diagnostic data and is
redacted and size-bounded before it can enter a model prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import subprocess
from typing import Any, Mapping, Sequence

from .advanced_bots import (
    BLOCKED_PREFIXES,
    BUILD_SAFE_PREFIXES,
)
from .build_authority import BuildAuthorization
from .free_model import redact_secrets
from .supervisor_runtime import (
    canonical_json,
    validate_branch,
    validate_repository,
    validate_sha,
    worker_branch_prefix,
)


MAX_PR_FILES = 100
MAX_CHECK_RUNS = 100
MAX_FAILURES = 24
MAX_CHECK_NAME_BYTES = 240
MAX_CHECK_OUTPUT_BYTES = 2_000
MAX_FAILURE_EVIDENCE_BYTES = 18_000
MAX_PR_BODY_BYTES = 32_000

FAILURE_CONCLUSIONS = frozenset(
    {
        "failure",
        "timed_out",
        "cancelled",
        "action_required",
        "startup_failure",
        "stale",
    }
)
REPAIRABLE_CONCLUSIONS = frozenset(
    {
        "failure",
        "timed_out",
    }
)
BENIGN_CONCLUSIONS = frozenset(
    {
        "success",
        "neutral",
        "skipped",
    }
)
FOLLOWUP_STATES = frozenset(
    {
        "waiting",
        "pending",
        "failed",
        "healthy",
    }
)
TICK = chr(96)


class BuildFollowupError(RuntimeError):
    """An existing build PR failed lifecycle admission."""


def _bounded_text(
    value: object,
    *,
    label: str,
    limit: int,
    allow_empty: bool = True,
) -> str:
    if not isinstance(value, str):
        raise BuildFollowupError(
            f"{label} must be text"
        )
    clean = redact_secrets(value).strip()
    if not clean and not allow_empty:
        raise BuildFollowupError(
            f"{label} must not be empty"
        )
    if "\x00" in clean:
        raise BuildFollowupError(
            f"{label} contains NUL"
        )
    raw = clean.encode("utf-8")
    if len(raw) > limit:
        clean = raw[:limit].decode(
            "utf-8",
            errors="ignore",
        )
    return clean


def _gh_json(
    args: Sequence[str],
    *,
    timeout: int = 30,
) -> object:
    try:
        raw = subprocess.check_output(
            ["gh", "api", *args],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return json.loads(raw)
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ) as exc:
        raise BuildFollowupError(
            "unable to inspect existing build PR"
        ) from exc


def _safe_build_path(path: object) -> str:
    if not isinstance(path, str) or not path:
        raise BuildFollowupError(
            "build followup path must be text"
        )
    if (
        path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or "//" in path
    ):
        raise BuildFollowupError(
            "invalid build followup path"
        )
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BuildFollowupError(
            "invalid build followup path component"
        )
    if any(
        path.startswith(prefix)
        for prefix in BLOCKED_PREFIXES
    ):
        raise BuildFollowupError(
            "existing build PR touches blocked control plane"
        )
    if not path.startswith(BUILD_SAFE_PREFIXES):
        raise BuildFollowupError(
            "existing build PR path exceeds build authority"
        )
    return path


@dataclass(frozen=True, slots=True)
class FailedCheck:
    name: str
    conclusion: str
    details_url: str
    title: str
    summary: str
    text: str

    def __post_init__(self) -> None:
        if self.conclusion not in FAILURE_CONCLUSIONS:
            raise BuildFollowupError(
                "invalid failed-check conclusion"
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "conclusion": self.conclusion,
            "details_url": self.details_url,
            "title": self.title,
            "summary": self.summary,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class BuildFollowup:
    repository: str
    pr_number: int
    branch: str
    head_sha: str
    base_branch: str
    task_digest: str
    changed_paths: tuple[str, ...]
    state: str
    failed_checks: tuple[FailedCheck, ...]
    total_checks: int

    def __post_init__(self) -> None:
        validate_repository(self.repository)
        validate_branch(self.branch)
        validate_sha(
            self.head_sha,
            label="build followup head SHA",
        )
        validate_branch(
            self.base_branch,
            label="build followup base branch",
        )
        if (
            isinstance(self.pr_number, bool)
            or not isinstance(self.pr_number, int)
            or self.pr_number < 1
        ):
            raise BuildFollowupError(
                "invalid build followup PR number"
            )
        if self.state not in FOLLOWUP_STATES:
            raise BuildFollowupError(
                "invalid build followup state"
            )
        if not self.changed_paths:
            raise BuildFollowupError(
                "build followup has no changed paths"
            )
        if len(self.changed_paths) != len(
            set(self.changed_paths)
        ):
            raise BuildFollowupError(
                "build followup has duplicate changed paths"
            )

    @property
    def repairable(self) -> bool:
        return (
            self.state == "failed"
            and any(
                item.conclusion in REPAIRABLE_CONCLUSIONS
                for item in self.failed_checks
            )
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(self.as_dict())
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "pr_number": self.pr_number,
            "branch": self.branch,
            "head_sha": self.head_sha,
            "base_branch": self.base_branch,
            "task_digest": self.task_digest,
            "changed_paths": list(self.changed_paths),
            "state": self.state,
            "failed_checks": [
                item.as_dict()
                for item in self.failed_checks
            ],
            "total_checks": self.total_checks,
        }

    def failure_context(self) -> str:
        payload = {
            "pull_request": self.pr_number,
            "head_sha": self.head_sha,
            "state": self.state,
            "failed_checks": [
                item.as_dict()
                for item in self.failed_checks
            ],
        }
        text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        raw = text.encode("utf-8")
        if len(raw) > MAX_FAILURE_EVIDENCE_BYTES:
            text = raw[
                :MAX_FAILURE_EVIDENCE_BYTES
            ].decode(
                "utf-8",
                errors="ignore",
            )
        return text


def _pr_payload(
    repository: str,
    pr_number: int,
) -> Mapping[str, Any]:
    value = _gh_json(
        [
            "-X",
            "GET",
            f"repos/{repository}/pulls/{pr_number}",
        ]
    )
    if not isinstance(value, Mapping):
        raise BuildFollowupError(
            "build PR lookup returned invalid shape"
        )
    return value


def _admit_pr_identity(
    repository: str,
    active_pr: Mapping[str, Any],
    authorization: BuildAuthorization,
) -> tuple[int, str, str, str]:
    number = active_pr.get("number")
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or number < 1
    ):
        raise BuildFollowupError(
            "active build PR has invalid number"
        )

    value = _pr_payload(
        repository,
        number,
    )
    if value.get("state") != "open":
        raise BuildFollowupError(
            "active build PR is no longer open"
        )

    head = value.get("head")
    base = value.get("base")
    if not isinstance(head, Mapping) or not isinstance(base, Mapping):
        raise BuildFollowupError(
            "active build PR has invalid ref metadata"
        )
    head_repo = head.get("repo")
    if (
        not isinstance(head_repo, Mapping)
        or head_repo.get("full_name") != repository
    ):
        raise BuildFollowupError(
            "active build PR is not same-repository"
        )

    branch = validate_branch(
        head.get("ref"),
        label="active build PR branch",
    )
    prefix = worker_branch_prefix(
        "feature-builder"
    )
    if not branch.startswith(prefix):
        raise BuildFollowupError(
            "active PR is outside feature-builder namespace"
        )
    suffix = branch[len(prefix):]
    if (
        len(suffix) != 16
        or any(
            char not in "0123456789abcdef"
            for char in suffix
        )
    ):
        raise BuildFollowupError(
            "active feature-builder branch is malformed"
        )

    head_sha = validate_sha(
        head.get("sha"),
        label="active build PR head SHA",
    )
    base_branch = validate_branch(
        base.get("ref"),
        label="active build PR base branch",
    )

    body = _bounded_text(
        value.get("body") or "",
        label="active build PR body",
        limit=MAX_PR_BODY_BYTES,
    )
    expected = (
        "Build task digest: "
        + TICK
        + authorization.task_digest
        + TICK
    )
    if expected not in body:
        raise BuildFollowupError(
            "active build PR is not bound to delegated task digest"
        )
    return number, branch, head_sha, base_branch


def _changed_paths(
    repository: str,
    pr_number: int,
) -> tuple[str, ...]:
    value = _gh_json(
        [
            "-X",
            "GET",
            f"repos/{repository}/pulls/{pr_number}/files",
            "-f",
            f"per_page={MAX_PR_FILES}",
        ]
    )
    if not isinstance(value, list):
        raise BuildFollowupError(
            "build PR files lookup returned invalid shape"
        )
    if len(value) >= MAX_PR_FILES:
        raise BuildFollowupError(
            "build PR changed-file set exceeds followup bound"
        )

    result: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise BuildFollowupError(
                "build PR file entry has invalid shape"
            )
        status = item.get("status")
        if status == "removed":
            raise BuildFollowupError(
                "build followup does not admit deleted files"
            )
        result.append(
            _safe_build_path(
                item.get("filename")
            )
        )
    if not result:
        raise BuildFollowupError(
            "build PR has no repairable changed paths"
        )
    if len(result) != len(set(result)):
        raise BuildFollowupError(
            "build PR files contain duplicates"
        )
    return tuple(sorted(result))


def _check_output(
    value: object,
) -> tuple[str, str, str]:
    if not isinstance(value, Mapping):
        return "", "", ""
    return (
        _bounded_text(
            value.get("title") or "",
            label="check output title",
            limit=MAX_CHECK_OUTPUT_BYTES,
        ),
        _bounded_text(
            value.get("summary") or "",
            label="check output summary",
            limit=MAX_CHECK_OUTPUT_BYTES,
        ),
        _bounded_text(
            value.get("text") or "",
            label="check output text",
            limit=MAX_CHECK_OUTPUT_BYTES,
        ),
    )


def _checks(
    repository: str,
    head_sha: str,
) -> tuple[str, tuple[FailedCheck, ...], int]:
    value = _gh_json(
        [
            "-X",
            "GET",
            f"repos/{repository}/commits/{head_sha}/check-runs",
            "-f",
            f"per_page={MAX_CHECK_RUNS}",
        ],
        timeout=45,
    )
    if not isinstance(value, Mapping):
        raise BuildFollowupError(
            "check-run lookup returned invalid shape"
        )
    total = value.get("total_count")
    runs = value.get("check_runs")
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
        or not isinstance(runs, list)
    ):
        raise BuildFollowupError(
            "check-run lookup returned invalid fields"
        )
    if total >= MAX_CHECK_RUNS or len(runs) >= MAX_CHECK_RUNS:
        raise BuildFollowupError(
            "check-run set exceeds followup bound"
        )
    if not runs:
        return "waiting", (), 0

    pending = False
    failed: list[FailedCheck] = []
    for item in runs:
        if not isinstance(item, Mapping):
            raise BuildFollowupError(
                "check-run entry has invalid shape"
            )
        status = item.get("status")
        conclusion = item.get("conclusion")
        if status != "completed":
            pending = True
            continue
        if conclusion in BENIGN_CONCLUSIONS:
            continue
        if conclusion not in FAILURE_CONCLUSIONS:
            raise BuildFollowupError(
                "check-run has unsupported terminal conclusion"
            )
        if len(failed) >= MAX_FAILURES:
            raise BuildFollowupError(
                "failed check set exceeds followup bound"
            )
        title, summary, output_text = _check_output(
            item.get("output")
        )
        failed.append(
            FailedCheck(
                name=_bounded_text(
                    item.get("name") or "",
                    label="check name",
                    limit=MAX_CHECK_NAME_BYTES,
                    allow_empty=False,
                ),
                conclusion=conclusion,
                details_url=_bounded_text(
                    item.get("details_url") or "",
                    label="check details URL",
                    limit=1_000,
                ),
                title=title,
                summary=summary,
                text=output_text,
            )
        )

    if pending:
        return "pending", tuple(failed), total
    if failed:
        return "failed", tuple(failed), total
    return "healthy", (), total


def inspect_build_followup(
    repository: str,
    active_pr: Mapping[str, Any],
    authorization: BuildAuthorization,
) -> BuildFollowup:
    """Admit one exact existing feature-builder PR and its completed CI state."""
    repository = validate_repository(
        repository
    )
    if authorization.repository != repository:
        raise BuildFollowupError(
            "build followup authorization repository mismatch"
        )

    (
        pr_number,
        branch,
        head_sha,
        base_branch,
    ) = _admit_pr_identity(
        repository,
        active_pr,
        authorization,
    )
    paths = _changed_paths(
        repository,
        pr_number,
    )
    state, failed, total = _checks(
        repository,
        head_sha,
    )
    return BuildFollowup(
        repository=repository,
        pr_number=pr_number,
        branch=branch,
        head_sha=head_sha,
        base_branch=base_branch,
        task_digest=authorization.task_digest,
        changed_paths=paths,
        state=state,
        failed_checks=failed,
        total_checks=total,
    )
