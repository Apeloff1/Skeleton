"""Fail-closed admission firewall for privileged workflow_run automation.

A GitHub `workflow_run` consumer executes trusted default-branch code with
privileged permissions, but the triggering event metadata still describes
untrusted or semi-trusted repository activity. This module converts that
metadata into an explicit admission decision before a token or GitHub client is
constructed.

The firewall distinguishes three outcomes:

* DROP -- event is a tombstone/non-actionable completion and no API work should run;
* OBSERVE -- metadata is valid enough to inspect but cannot authorize mutation;
* MUTATE -- metadata is same-repository, successful, terminal PR validation from
  the exact trusted upstream workflow.

No decision here is sufficient by itself to merge. The normal PR policy engine,
protected-branch requirement, fresh snapshot revalidation, mutation cap, queue
pressure guard, and server-side expected-head SHA remain mandatory downstream.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

_MAX_BRANCH = 255
_MAX_REPOSITORY = 201
_MAX_WORKFLOW = 256
_MAX_HINTS = 64
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BRANCH_BAD_RE = re.compile(r"(?:\.\.|//|@\{|\\|\s)")
_ALLOWED_CONCLUSIONS = frozenset(
    {
        "success",
        "failure",
        "neutral",
        "cancelled",
        "skipped",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
)
_MUTATION_SOURCE_EVENTS = frozenset({"pull_request"})


class EventFirewallError(ValueError):
    """Raised when workflow-run authority metadata is malformed."""


class AdmissionLevel(str, Enum):
    DROP = "drop"
    OBSERVE = "observe"
    MUTATE = "mutate"


@dataclass(frozen=True, slots=True)
class WorkflowRunEvent:
    repository: str
    upstream_workflow: str
    run_id: int
    run_attempt: int
    workflow_id: int
    status: str
    conclusion: str
    source_event: str
    head_repository: str
    head_branch: str
    head_sha: str
    pr_hints: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "repository",
            _repository(self.repository, field_name="repository"),
        )
        object.__setattr__(
            self,
            "upstream_workflow",
            _text(
                self.upstream_workflow,
                field_name="upstream_workflow",
                limit=_MAX_WORKFLOW,
            ),
        )
        for field_name in ("run_id", "run_attempt", "workflow_id"):
            object.__setattr__(
                self,
                field_name,
                _positive_int(getattr(self, field_name), field_name=field_name),
            )
        status = _text(self.status, field_name="status", limit=32).casefold()
        if status != "completed":
            raise EventFirewallError("workflow_run status must be completed")
        object.__setattr__(self, "status", status)

        conclusion = _text(
            self.conclusion,
            field_name="conclusion",
            limit=64,
        ).casefold()
        if conclusion not in _ALLOWED_CONCLUSIONS:
            raise EventFirewallError("workflow_run conclusion is invalid")
        object.__setattr__(self, "conclusion", conclusion)

        object.__setattr__(
            self,
            "source_event",
            _text(
                self.source_event,
                field_name="source_event",
                limit=64,
            ).casefold(),
        )
        object.__setattr__(
            self,
            "head_repository",
            _repository(
                self.head_repository,
                field_name="head_repository",
            ),
        )
        object.__setattr__(
            self,
            "head_branch",
            _branch(self.head_branch),
        )
        sha = _text(self.head_sha, field_name="head_sha", limit=40)
        if _SHA_RE.fullmatch(sha) is None:
            raise EventFirewallError(
                "workflow_run head_sha must be a full lowercase 40-character OID"
            )
        object.__setattr__(self, "head_sha", sha)

        hints = tuple(self.pr_hints)
        if len(hints) > _MAX_HINTS:
            raise EventFirewallError("too many workflow_run PR hints")
        normalized: list[int] = []
        seen: set[int] = set()
        for hint in hints:
            number = _positive_int(hint, field_name="PR hint")
            if number in seen:
                continue
            seen.add(number)
            normalized.append(number)
        object.__setattr__(self, "pr_hints", tuple(normalized))

    @property
    def fingerprint(self) -> str:
        payload = {
            "repository": self.repository,
            "upstream_workflow": self.upstream_workflow,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "conclusion": self.conclusion,
            "source_event": self.source_event,
            "head_repository": self.head_repository,
            "head_branch": self.head_branch,
            "head_sha": self.head_sha,
            "pr_hints": list(self.pr_hints),
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class EventAdmission:
    level: AdmissionLevel
    reason: str
    event_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.level, AdmissionLevel):
            object.__setattr__(self, "level", AdmissionLevel(self.level))
        object.__setattr__(
            self,
            "reason",
            _text(self.reason, field_name="admission reason", limit=256),
        )
        digest = _text(
            self.event_fingerprint,
            field_name="event_fingerprint",
            limit=64,
        ).casefold()
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise EventFirewallError("event fingerprint must be sha256 hex")
        object.__setattr__(self, "event_fingerprint", digest)

    @property
    def dropped(self) -> bool:
        return self.level is AdmissionLevel.DROP

    @property
    def mutation_authorized(self) -> bool:
        return self.level is AdmissionLevel.MUTATE

    def public_payload(self) -> dict[str, object]:
        return {
            "level": self.level.value,
            "reason": self.reason,
            "event_fingerprint": self.event_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class EventFirewallPolicy:
    trusted_upstream_workflows: frozenset[str] = frozenset({"Merge Readiness"})
    mutation_source_events: frozenset[str] = _MUTATION_SOURCE_EVENTS
    require_same_repository_for_mutation: bool = True

    def __post_init__(self) -> None:
        if not self.trusted_upstream_workflows:
            raise EventFirewallError("trusted upstream workflow set must not be empty")
        workflows = frozenset(
            _text(item, field_name="trusted workflow", limit=_MAX_WORKFLOW)
            for item in self.trusted_upstream_workflows
        )
        object.__setattr__(self, "trusted_upstream_workflows", workflows)
        events = frozenset(
            _text(item, field_name="mutation source event", limit=64).casefold()
            for item in self.mutation_source_events
        )
        if not events:
            raise EventFirewallError("mutation source event set must not be empty")
        object.__setattr__(self, "mutation_source_events", events)


def _text(
    value: object,
    *,
    field_name: str,
    limit: int,
) -> str:
    if not isinstance(value, str):
        raise EventFirewallError(f"{field_name} must be a string")
    if value != value.strip() or not value:
        raise EventFirewallError(f"{field_name} must be non-empty and canonical")
    if len(value) > limit:
        raise EventFirewallError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(value):
        raise EventFirewallError(f"{field_name} contains control characters")
    return value


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise EventFirewallError(f"{field_name} must be a positive integer")
    if isinstance(value, str):
        if not value.isdigit():
            raise EventFirewallError(f"{field_name} must be a positive integer")
        number = int(value)
    elif isinstance(value, int):
        number = value
    else:
        raise EventFirewallError(f"{field_name} must be a positive integer")
    if number < 1:
        raise EventFirewallError(f"{field_name} must be a positive integer")
    return number


def _repository(value: object, *, field_name: str) -> str:
    text = _text(value, field_name=field_name, limit=_MAX_REPOSITORY)
    if _REPOSITORY_RE.fullmatch(text) is None:
        raise EventFirewallError(f"{field_name} must be owner/name")
    return text


def _branch(value: object) -> str:
    text = _text(value, field_name="head_branch", limit=_MAX_BRANCH)
    if (
        text.startswith(("/", "."))
        or text.endswith(("/", "."))
        or _BRANCH_BAD_RE.search(text)
        or text.endswith(".lock")
    ):
        raise EventFirewallError("workflow_run head_branch is not canonical")
    return text


def parse_pr_hints(raw: object) -> tuple[int, ...]:
    if raw in (None, "", "null"):
        return ()
    if not isinstance(raw, str):
        raise EventFirewallError("workflow_run PR hints must be JSON text")
    if len(raw) > 8192:
        raise EventFirewallError("workflow_run PR hints exceed size bound")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EventFirewallError("workflow_run PR hints are invalid JSON") from exc
    if not isinstance(payload, list):
        raise EventFirewallError("workflow_run PR hints must be a JSON array")
    if len(payload) > _MAX_HINTS:
        raise EventFirewallError("too many workflow_run PR hints")
    hints: list[int] = []
    for value in payload:
        hints.append(_positive_int(value, field_name="PR hint"))
    return tuple(dict.fromkeys(hints))


def event_from_env(
    env: Mapping[str, str],
    *,
    repository: str,
    head_sha: str,
    head_branch: str,
    pr_hints_json: str,
) -> WorkflowRunEvent:
    """Build strict workflow-run authority from an environment boundary."""

    return WorkflowRunEvent(
        repository=repository,
        upstream_workflow=env.get("WORKFLOW_RUN_NAME", ""),
        run_id=env.get("WORKFLOW_RUN_ID", ""),
        run_attempt=env.get("WORKFLOW_RUN_ATTEMPT", ""),
        workflow_id=env.get("WORKFLOW_RUN_WORKFLOW_ID", ""),
        status=env.get("WORKFLOW_RUN_STATUS", ""),
        conclusion=env.get("WORKFLOW_RUN_CONCLUSION", ""),
        source_event=env.get("WORKFLOW_RUN_EVENT", ""),
        head_repository=env.get("WORKFLOW_RUN_HEAD_REPOSITORY", ""),
        head_branch=head_branch,
        head_sha=head_sha,
        pr_hints=parse_pr_hints(pr_hints_json),
    )


def admit_workflow_run(
    event: WorkflowRunEvent,
    *,
    policy: EventFirewallPolicy | None = None,
) -> EventAdmission:
    """Classify one terminal upstream run before privileged automation starts."""

    if not isinstance(event, WorkflowRunEvent):
        raise EventFirewallError("event must be WorkflowRunEvent")
    selected = policy or EventFirewallPolicy()
    fingerprint = event.fingerprint

    if event.upstream_workflow not in selected.trusted_upstream_workflows:
        return EventAdmission(
            AdmissionLevel.DROP,
            "upstream workflow is not trusted for PR automation",
            fingerprint,
        )

    if event.conclusion == "cancelled":
        return EventAdmission(
            AdmissionLevel.DROP,
            "cancelled upstream run is a superseded tombstone",
            fingerprint,
        )

    same_repository = (
        event.head_repository.casefold() == event.repository.casefold()
    )
    if selected.require_same_repository_for_mutation and not same_repository:
        return EventAdmission(
            AdmissionLevel.OBSERVE,
            "cross-repository completion is observation-only",
            fingerprint,
        )

    if event.conclusion != "success":
        return EventAdmission(
            AdmissionLevel.OBSERVE,
            "non-success upstream completion cannot authorize mutation",
            fingerprint,
        )

    if event.source_event not in selected.mutation_source_events:
        return EventAdmission(
            AdmissionLevel.OBSERVE,
            "upstream trigger class is observation-only",
            fingerprint,
        )

    return EventAdmission(
        AdmissionLevel.MUTATE,
        "terminal same-repository PR validation may proceed to downstream policy checks",
        fingerprint,
    )


__all__ = [
    "AdmissionLevel",
    "EventAdmission",
    "EventFirewallError",
    "EventFirewallPolicy",
    "WorkflowRunEvent",
    "admit_workflow_run",
    "event_from_env",
    "parse_pr_hints",
]
