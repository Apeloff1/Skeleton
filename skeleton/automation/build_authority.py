"""Structured maintainer authority for autonomous feature builds.

A model may help interpret an approved work item, but it may never invent build
authority.  Authority comes only from repository issue state observed by the
read-only Supervisor and is converted here into a small canonical object that
can cross the Supervisor -> Secretary -> Worker boundary.

The object is intentionally data-only.  It contains no executable, command,
module name, permission, token, ref, or arbitrary routing instruction.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .free_model import redact_secrets
from .supervisor_runtime import (
    SupervisorRuntimeError,
    canonical_json,
    validate_repository,
)

APPROVED_BUILD_LABELS = frozenset(
    {
        "automation-approved",
        "supervisor-approved",
        "build-approved",
    }
)
MAX_BUILD_TITLE_BYTES = 500
MAX_BUILD_BODY_BYTES = 6_000
MAX_BUILD_LABELS = 32
MAX_BUILD_LABEL_BYTES = 96
MAX_UPDATED_AT_BYTES = 64
MAX_ISSUE_NUMBER = 2_147_483_647


class BuildAuthorityError(ValueError):
    """A repository item did not prove bounded maintainer build authority."""


def _bounded_text(
    value: object,
    *,
    label: str,
    byte_limit: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise BuildAuthorityError(f"{label} must be text")
    clean = redact_secrets(value).strip()
    if not clean and not allow_empty:
        raise BuildAuthorityError(f"{label} must not be empty")
    if len(clean.encode("utf-8")) > byte_limit:
        raise BuildAuthorityError(f"{label} exceeds byte budget")
    if "\x00" in clean:
        raise BuildAuthorityError(f"{label} contains NUL")
    return clean


def _issue_number(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > MAX_ISSUE_NUMBER
    ):
        raise BuildAuthorityError("invalid build issue number")
    return value


def _labels(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise BuildAuthorityError("build labels must be a sequence")
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("name")
        if not isinstance(item, str):
            raise BuildAuthorityError("invalid build label")
        name = item.strip().casefold()
        if not name:
            raise BuildAuthorityError("empty build label")
        if len(name.encode("utf-8")) > MAX_BUILD_LABEL_BYTES:
            raise BuildAuthorityError("build label exceeds byte budget")
        names.append(name)
    unique = tuple(sorted(set(names)))
    if len(unique) > MAX_BUILD_LABELS:
        raise BuildAuthorityError("too many build labels")
    return unique


def _updated_at(value: object) -> str:
    return _bounded_text(
        value,
        label="build updated_at",
        byte_limit=MAX_UPDATED_AT_BYTES,
        allow_empty=True,
    )


def _digest_payload(
    *,
    repository: str,
    issue_number: int,
    title: str,
    body: str,
    labels: tuple[str, ...],
    updated_at: str,
) -> dict[str, object]:
    return {
        "repository": repository,
        "issue_number": issue_number,
        "title": title,
        "body": body,
        "labels": labels,
        "updated_at": updated_at,
    }


@dataclass(frozen=True, slots=True)
class BuildAuthorization:
    """One exact, maintainer-approved issue delegated for autonomous building."""

    version: int
    repository: str
    issue_number: int
    title: str
    body: str
    labels: tuple[str, ...]
    updated_at: str
    issue_digest: str

    def __post_init__(self) -> None:
        if self.version != 1:
            raise BuildAuthorityError(
                "unsupported build authorization version"
            )
        try:
            validate_repository(self.repository)
        except SupervisorRuntimeError as exc:
            raise BuildAuthorityError(
                "invalid build authorization repository"
            ) from exc
        number = _issue_number(self.issue_number)
        title = _bounded_text(
            self.title,
            label="build title",
            byte_limit=MAX_BUILD_TITLE_BYTES,
        )
        body = _bounded_text(
            self.body,
            label="build body",
            byte_limit=MAX_BUILD_BODY_BYTES,
        )
        labels = _labels(self.labels)
        updated_at = _updated_at(self.updated_at)
        if not APPROVED_BUILD_LABELS.intersection(labels):
            raise BuildAuthorityError(
                "build authorization lacks an approved label"
            )
        expected = hashlib.sha256(
            canonical_json(
                _digest_payload(
                    repository=self.repository,
                    issue_number=number,
                    title=title,
                    body=body,
                    labels=labels,
                    updated_at=updated_at,
                )
            )
        ).hexdigest()
        if self.issue_digest != expected:
            raise BuildAuthorityError(
                "build authorization digest mismatch"
            )
        if self.issue_number != number:
            raise BuildAuthorityError(
                "build authorization issue number is not normalized"
            )
        if self.title != title or self.body != body:
            raise BuildAuthorityError(
                "build authorization text is not normalized"
            )
        if self.labels != labels:
            raise BuildAuthorityError(
                "build authorization labels are not normalized"
            )
        if self.updated_at != updated_at:
            raise BuildAuthorityError(
                "build authorization timestamp is not normalized"
            )

    @property
    def task_digest(self) -> str:
        """Stable task identity used for custody, evidence, and deduplication."""
        return hashlib.sha256(
            canonical_json(
                {
                    "version": self.version,
                    "repository": self.repository,
                    "issue_number": self.issue_number,
                    "issue_digest": self.issue_digest,
                }
            )
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "repository": self.repository,
            "issue_number": self.issue_number,
            "title": self.title,
            "body": self.body,
            "labels": list(self.labels),
            "updated_at": self.updated_at,
            "issue_digest": self.issue_digest,
            "task_digest": self.task_digest,
        }

    @classmethod
    def from_issue(
        cls,
        repository: str,
        issue: Mapping[str, Any],
    ) -> "BuildAuthorization":
        try:
            validate_repository(repository)
        except SupervisorRuntimeError as exc:
            raise BuildAuthorityError(
                "invalid build repository"
            ) from exc
        if issue.get("automation_authorized") is not True:
            raise BuildAuthorityError(
                "issue is not explicitly authorized for automation"
            )
        number = _issue_number(issue.get("number"))
        title = _bounded_text(
            issue.get("title"),
            label="build title",
            byte_limit=MAX_BUILD_TITLE_BYTES,
        )
        body = _bounded_text(
            issue.get("body"),
            label="build body",
            byte_limit=MAX_BUILD_BODY_BYTES,
        )
        labels = _labels(issue.get("labels", ()))
        updated_at = _updated_at(issue.get("updatedAt", ""))
        if not APPROVED_BUILD_LABELS.intersection(labels):
            raise BuildAuthorityError(
                "approved issue is missing an approved build label"
            )
        digest = hashlib.sha256(
            canonical_json(
                _digest_payload(
                    repository=repository,
                    issue_number=number,
                    title=title,
                    body=body,
                    labels=labels,
                    updated_at=updated_at,
                )
            )
        ).hexdigest()
        return cls(
            version=1,
            repository=repository,
            issue_number=number,
            title=title,
            body=body,
            labels=labels,
            updated_at=updated_at,
            issue_digest=digest,
        )

    @classmethod
    def from_payload(
        cls,
        value: object,
    ) -> "BuildAuthorization":
        if not isinstance(value, dict):
            raise BuildAuthorityError(
                "build authorization payload must be an object"
            )
        expected = {
            "version",
            "repository",
            "issue_number",
            "title",
            "body",
            "labels",
            "updated_at",
            "issue_digest",
            "task_digest",
        }
        if set(value) != expected:
            raise BuildAuthorityError(
                "build authorization payload shape mismatch"
            )
        authorization = cls(
            version=value["version"],
            repository=value["repository"],
            issue_number=value["issue_number"],
            title=value["title"],
            body=value["body"],
            labels=tuple(value["labels"])
            if isinstance(value["labels"], list)
            else value["labels"],
            updated_at=value["updated_at"],
            issue_digest=value["issue_digest"],
        )
        if value.get("task_digest") != authorization.task_digest:
            raise BuildAuthorityError(
                "build task digest mismatch"
            )
        return authorization


def authorized_builds(
    repository: str,
    issues: Iterable[Mapping[str, Any]],
) -> tuple[BuildAuthorization, ...]:
    """Return every valid explicit build authorization in deterministic order."""
    result: list[BuildAuthorization] = []
    for issue in issues:
        if issue.get("automation_authorized") is not True:
            continue
        result.append(
            BuildAuthorization.from_issue(
                repository,
                issue,
            )
        )
    result.sort(
        key=lambda item: (
            item.issue_number,
            item.issue_digest,
        )
    )
    return tuple(result)


def _github_issue_payload(
    repository: str,
    issue_number: int,
    *,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetch one issue with enough state to revalidate build authority."""
    try:
        raw = subprocess.check_output(
            [
                "gh",
                "issue",
                "view",
                str(_issue_number(issue_number)),
                "--repo",
                validate_repository(repository),
                "--json",
                "number,title,body,labels,updatedAt,state",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        value = json.loads(raw)
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        SupervisorRuntimeError,
    ) as exc:
        raise BuildAuthorityError(
            "unable to revalidate live build issue"
        ) from exc
    if not isinstance(value, dict):
        raise BuildAuthorityError(
            "live build issue returned invalid shape"
        )
    return value


def revalidate_live_build_authorization(
    authorization: BuildAuthorization,
    *,
    timeout: int = 30,
) -> BuildAuthorization:
    """Require the approved issue to remain open, unchanged, and approved.

    This closes the issue-state TOCTOU window between read-only planning and
    mutation. Removing an approval label, editing the task, or closing the issue
    immediately revokes autonomous build authority.
    """
    value = _github_issue_payload(
        authorization.repository,
        authorization.issue_number,
        timeout=timeout,
    )
    state = value.get("state")
    if not isinstance(state, str) or state.upper() != "OPEN":
        raise BuildAuthorityError(
            "authorized build issue is no longer open"
        )

    labels = _labels(value.get("labels", ()))
    candidate = {
        "number": value.get("number"),
        "title": value.get("title"),
        "body": value.get("body"),
        "labels": labels,
        "updatedAt": value.get("updatedAt", ""),
        "automation_authorized": bool(
            APPROVED_BUILD_LABELS.intersection(labels)
        ),
    }
    current = BuildAuthorization.from_issue(
        authorization.repository,
        candidate,
    )
    if current != authorization:
        raise BuildAuthorityError(
            "authorized build issue changed after Supervisor observation"
        )
    return current


def select_build_authorization(
    repository: str,
    issues: Iterable[Mapping[str, Any]],
) -> BuildAuthorization | None:
    """Select exactly one approved issue per Supervisor run.

    Lower issue number wins.  This is intentionally boring and deterministic:
    the model does not choose which maintainer-approved task receives authority.
    """
    builds = authorized_builds(repository, issues)
    return builds[0] if builds else None


__all__ = [
    "APPROVED_BUILD_LABELS",
    "BuildAuthorization",
    "BuildAuthorityError",
    "MAX_BUILD_BODY_BYTES",
    "MAX_BUILD_TITLE_BYTES",
    "authorized_builds",
    "revalidate_live_build_authorization",
    "select_build_authorization",
]
