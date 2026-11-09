"""Immutable contracts for merge-blocker diagnosis and safe recovery.

The recovery plane is intentionally separate from merge authority.  It may
observe repository state and retry a narrowly defined class of transient GitHub
Actions failures, but it never weakens a required gate, edits pull-request code,
or declares a deterministic test failure successful.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_CONTEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    moment = value or utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_seconds(value: str | None, *, now: datetime | None = None) -> int | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    delta = current.astimezone(timezone.utc) - parsed
    return max(0, int(delta.total_seconds()))


def valid_sha(value: str) -> bool:
    return bool(_SHA_RE.fullmatch(value))


def valid_repository(value: str) -> bool:
    return bool(_REPOSITORY_RE.fullmatch(value))


def valid_context(value: str) -> bool:
    return bool(_CONTEXT_RE.fullmatch(value))


def valid_ref(value: str) -> bool:
    if not _REF_RE.fullmatch(value):
        return False
    if value.startswith("/") or value.endswith("/") or value.endswith("."):
        return False
    if ".." in value or "@{" in value or value.endswith(".lock"):
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _dedupe_text(values: Iterable[str], *, lower: bool = False) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise TypeError("expected string value")
        value = raw.strip()
        if lower:
            value = value.casefold()
        if not value:
            raise ValueError("empty strings are not allowed")
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


class RecoveryMode(StrEnum):
    OBSERVE = "observe"
    REPAIR = "repair"


class SubjectKind(StrEnum):
    DEFAULT_BRANCH = "default_branch"
    PULL_REQUEST = "pull_request"


class BlockerKind(StrEnum):
    NONE = "none"
    PENDING = "pending"
    QUEUE_STARVATION = "queue_starvation"
    TRANSIENT_CANCELLED = "transient_cancelled"
    TRANSIENT_TIMEOUT = "transient_timeout"
    TRANSIENT_STARTUP = "transient_startup"
    TRANSIENT_STALE = "transient_stale"
    DETERMINISTIC_FAILURE = "deterministic_failure"
    ACTION_REQUIRED = "action_required"
    MISSING_EVIDENCE = "missing_evidence"
    UNKNOWN_RESULT = "unknown_result"
    DRAFT = "draft"
    MERGE_CONFLICT = "merge_conflict"
    BASE_BEHIND = "base_behind"
    REVIEW_BLOCK = "review_block"
    POLICY_BLOCK = "policy_block"
    HEAD_MOVED = "head_moved"
    API_INCOMPLETE = "api_incomplete"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RecoveryActionKind(StrEnum):
    NONE = "none"
    RERUN_JOB = "rerun_job"
    RERUN_FAILED_JOBS = "rerun_failed_jobs"
    RERUN_WORKFLOW = "rerun_workflow"
    HOLD = "hold"
    ESCALATE = "escalate"


class ExecutionState(StrEnum):
    PLANNED = "planned"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CheckRunEvidence:
    id: int
    name: str
    head_sha: str
    status: str
    conclusion: str | None
    details_url: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    suite_id: int | None = None

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("check run id must be positive")
        if not valid_context(self.name):
            raise ValueError("invalid check run name")
        if not valid_sha(self.head_sha):
            raise ValueError("check head SHA must be canonical lowercase SHA")
        if not self.status.strip():
            raise ValueError("check status is required")
        if self.suite_id is not None and self.suite_id <= 0:
            raise ValueError("suite id must be positive")

    @property
    def normalized_status(self) -> str:
        return self.status.casefold().strip()

    @property
    def normalized_conclusion(self) -> str:
        return (self.conclusion or "").casefold().strip()

    @property
    def pending(self) -> bool:
        return self.normalized_status != "completed"


@dataclass(frozen=True, slots=True)
class WorkflowJobEvidence:
    id: int
    run_id: int
    name: str
    status: str
    conclusion: str | None
    started_at: str | None = None
    completed_at: str | None = None

    def __post_init__(self) -> None:
        if self.id <= 0 or self.run_id <= 0:
            raise ValueError("job and run ids must be positive")
        if not valid_context(self.name):
            raise ValueError("invalid job name")
        if not self.status.strip():
            raise ValueError("job status is required")

    @property
    def pending(self) -> bool:
        return self.status.casefold().strip() != "completed"

    @property
    def normalized_conclusion(self) -> str:
        return (self.conclusion or "").casefold().strip()


@dataclass(frozen=True, slots=True)
class WorkflowRunEvidence:
    id: int
    name: str
    head_sha: str
    event: str
    status: str
    conclusion: str | None
    run_number: int
    attempt: int
    created_at: str | None = None
    updated_at: str | None = None
    html_url: str | None = None
    jobs: tuple[WorkflowJobEvidence, ...] = ()

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("workflow run id must be positive")
        if not valid_context(self.name):
            raise ValueError("invalid workflow name")
        if not valid_sha(self.head_sha):
            raise ValueError("workflow head SHA must be canonical lowercase SHA")
        if self.run_number < 0 or self.attempt <= 0:
            raise ValueError("invalid workflow run sequence")
        if not self.event.strip() or not self.status.strip():
            raise ValueError("workflow event and status are required")
        if any(job.run_id != self.id for job in self.jobs):
            raise ValueError("job run id does not match workflow run")

    @property
    def rank(self) -> tuple[int, int, str]:
        return (self.run_number, self.attempt, self.updated_at or self.created_at or "")

    @property
    def pending(self) -> bool:
        return self.status.casefold().strip() != "completed"

    @property
    def normalized_conclusion(self) -> str:
        return (self.conclusion or "").casefold().strip()


@dataclass(frozen=True, slots=True)
class PullRequestSubject:
    repository: str
    number: int
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    draft: bool
    mergeable: bool | None
    mergeable_state: str
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if not valid_repository(self.repository):
            raise ValueError("invalid repository")
        if self.number <= 0:
            raise ValueError("pull request number must be positive")
        if not valid_ref(self.base_ref) or not valid_ref(self.head_ref):
            raise ValueError("invalid pull request ref")
        if not valid_sha(self.base_sha) or not valid_sha(self.head_sha):
            raise ValueError("pull request SHAs must be canonical lowercase SHA")


@dataclass(frozen=True, slots=True)
class RecoverySubject:
    kind: SubjectKind
    repository: str
    head_sha: str
    base_ref: str
    pr: PullRequestSubject | None = None

    def __post_init__(self) -> None:
        if not valid_repository(self.repository):
            raise ValueError("invalid repository")
        if not valid_sha(self.head_sha):
            raise ValueError("subject head SHA must be canonical lowercase SHA")
        if not valid_ref(self.base_ref):
            raise ValueError("invalid subject base ref")
        if self.kind is SubjectKind.PULL_REQUEST and self.pr is None:
            raise ValueError("pull request subject requires PR metadata")
        if self.kind is SubjectKind.DEFAULT_BRANCH and self.pr is not None:
            raise ValueError("default branch subject cannot carry PR metadata")
        if self.pr is not None and self.pr.head_sha != self.head_sha:
            raise ValueError("subject and pull request head SHA differ")

    @property
    def key(self) -> str:
        if self.pr is None:
            return f"branch:{self.base_ref}:{self.head_sha}"
        return f"pr:{self.pr.number}:{self.head_sha}"


@dataclass(frozen=True, slots=True)
class BlockerObservation:
    subject_key: str
    kind: BlockerKind
    severity: Severity
    code: str
    message: str
    workflow_name: str | None = None
    workflow_run_id: int | None = None
    job_id: int | None = None
    check_run_id: int | None = None
    retryable: bool = False
    observed_at: str = field(default_factory=iso_utc)

    def __post_init__(self) -> None:
        if not self.subject_key.strip():
            raise ValueError("subject key is required")
        if not re.fullmatch(r"[a-z0-9_.:-]{2,80}", self.code):
            raise ValueError("invalid observation code")
        if not self.message.strip():
            raise ValueError("observation message is required")
        if self.workflow_name is not None and not valid_context(self.workflow_name):
            raise ValueError("invalid workflow name")
        for value in (self.workflow_run_id, self.job_id, self.check_run_id):
            if value is not None and value <= 0:
                raise ValueError("evidence ids must be positive")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    kind: RecoveryActionKind
    subject_key: str
    reason: str
    workflow_name: str | None = None
    workflow_run_id: int | None = None
    job_id: int | None = None
    expected_head_sha: str | None = None
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if not self.subject_key.strip() or not self.reason.strip():
            raise ValueError("recovery action requires subject and reason")
        if self.expected_head_sha is not None and not valid_sha(self.expected_head_sha):
            raise ValueError("expected head SHA must be canonical lowercase SHA")
        if self.workflow_name is not None and not valid_context(self.workflow_name):
            raise ValueError("invalid workflow name")
        if self.workflow_run_id is not None and self.workflow_run_id <= 0:
            raise ValueError("workflow run id must be positive")
        if self.job_id is not None and self.job_id <= 0:
            raise ValueError("job id must be positive")
        if self.kind is RecoveryActionKind.RERUN_JOB and self.job_id is None:
            raise ValueError("rerun_job requires job id")
        if self.kind in {
            RecoveryActionKind.RERUN_FAILED_JOBS,
            RecoveryActionKind.RERUN_WORKFLOW,
        } and self.workflow_run_id is None:
            raise ValueError("workflow rerun action requires run id")
        if self.idempotency_key and not re.fullmatch(r"[0-9a-f]{64}", self.idempotency_key):
            raise ValueError("invalid idempotency key")

    @classmethod
    def make(
        cls,
        *,
        kind: RecoveryActionKind,
        subject: RecoverySubject,
        reason: str,
        workflow_name: str | None = None,
        workflow_run_id: int | None = None,
        job_id: int | None = None,
    ) -> "RecoveryAction":
        payload = {
            "kind": kind.value,
            "subject": subject.key,
            "head": subject.head_sha,
            "workflow": workflow_name,
            "run": workflow_run_id,
            "job": job_id,
        }
        return cls(
            kind=kind,
            subject_key=subject.key,
            reason=reason,
            workflow_name=workflow_name,
            workflow_run_id=workflow_run_id,
            job_id=job_id,
            expected_head_sha=subject.head_sha,
            idempotency_key=fingerprint(payload),
        )


@dataclass(frozen=True, slots=True)
class RecoveryBudget:
    max_subjects: int = 100
    max_workflow_runs_per_subject: int = 100
    max_jobs_per_run: int = 100
    max_actions: int = 8
    max_actions_per_subject: int = 2
    pending_grace_seconds: int = 180
    queue_starvation_seconds: int = 900
    max_retry_attempt: int = 3

    def __post_init__(self) -> None:
        positive = (
            self.max_subjects,
            self.max_workflow_runs_per_subject,
            self.max_jobs_per_run,
            self.max_actions,
            self.max_actions_per_subject,
            self.max_retry_attempt,
        )
        if any(isinstance(value, bool) or value <= 0 for value in positive):
            raise ValueError("recovery budget positive fields must be positive integers")
        if isinstance(self.pending_grace_seconds, bool) or self.pending_grace_seconds < 0:
            raise ValueError("pending grace must be non-negative")
        if (
            isinstance(self.queue_starvation_seconds, bool)
            or self.queue_starvation_seconds <= self.pending_grace_seconds
        ):
            raise ValueError("queue starvation threshold must exceed pending grace")


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    mode: RecoveryMode = RecoveryMode.OBSERVE
    default_branch: str = "main"
    required_workflows: tuple[str, ...] = ()
    retryable_conclusions: tuple[str, ...] = (
        "cancelled",
        "timed_out",
        "startup_failure",
        "stale",
    )
    deterministic_failure_conclusions: tuple[str, ...] = (
        "failure",
        "action_required",
    )
    never_retry_workflow_prefixes: tuple[str, ...] = (
        "CodeQL",
        "Code scanning",
    )
    retryable_job_name_prefixes: tuple[str, ...] = ()
    require_exact_head: bool = True
    require_pull_request_event_for_pr: bool = True
    rerun_cancelled: bool = True
    rerun_timed_out: bool = True
    rerun_startup_failure: bool = True
    rerun_stale: bool = True
    budget: RecoveryBudget = field(default_factory=RecoveryBudget)

    def __post_init__(self) -> None:
        if not valid_ref(self.default_branch):
            raise ValueError("invalid default branch")
        object.__setattr__(
            self,
            "required_workflows",
            _dedupe_text(self.required_workflows),
        )
        object.__setattr__(
            self,
            "retryable_conclusions",
            _dedupe_text(self.retryable_conclusions, lower=True),
        )
        object.__setattr__(
            self,
            "deterministic_failure_conclusions",
            _dedupe_text(self.deterministic_failure_conclusions, lower=True),
        )
        object.__setattr__(
            self,
            "never_retry_workflow_prefixes",
            _dedupe_text(self.never_retry_workflow_prefixes),
        )
        object.__setattr__(
            self,
            "retryable_job_name_prefixes",
            _dedupe_text(self.retryable_job_name_prefixes),
        )
        overlap = set(self.retryable_conclusions).intersection(
            self.deterministic_failure_conclusions
        )
        if overlap:
            raise ValueError("conclusion cannot be both retryable and deterministic")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class ActionReceipt:
    idempotency_key: str
    action_kind: RecoveryActionKind
    subject_key: str
    execution_state: ExecutionState
    message: str
    workflow_run_id: int | None = None
    job_id: int | None = None
    recorded_at: str = field(default_factory=iso_utc)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.idempotency_key):
            raise ValueError("invalid receipt idempotency key")
        if not self.subject_key.strip() or not self.message.strip():
            raise ValueError("receipt requires subject and message")


@dataclass(frozen=True, slots=True)
class SubjectDiagnosis:
    subject: RecoverySubject
    observations: tuple[BlockerObservation, ...]
    actions: tuple[RecoveryAction, ...]
    workflow_runs: tuple[WorkflowRunEvidence, ...] = ()
    check_runs: tuple[CheckRunEvidence, ...] = ()

    def __post_init__(self) -> None:
        if any(item.subject_key != self.subject.key for item in self.observations):
            raise ValueError("observation belongs to another subject")
        if any(item.subject_key != self.subject.key for item in self.actions):
            raise ValueError("action belongs to another subject")

    @property
    def blocked(self) -> bool:
        return any(item.kind is not BlockerKind.NONE for item in self.observations)

    @property
    def retryable(self) -> bool:
        return any(item.retryable for item in self.observations)


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    repository: str
    default_branch: str
    default_head_sha: str
    policy_fingerprint: str
    diagnoses: tuple[SubjectDiagnosis, ...]
    planned_actions: tuple[RecoveryAction, ...]
    receipts: tuple[ActionReceipt, ...]
    started_at: str
    finished_at: str

    def __post_init__(self) -> None:
        if not valid_repository(self.repository):
            raise ValueError("invalid report repository")
        if not valid_ref(self.default_branch):
            raise ValueError("invalid report default branch")
        if not valid_sha(self.default_head_sha):
            raise ValueError("invalid report default head")
        if not re.fullmatch(r"[0-9a-f]{64}", self.policy_fingerprint):
            raise ValueError("invalid policy fingerprint")

    @property
    def blocker_count(self) -> int:
        return sum(len(item.observations) for item in self.diagnoses)

    @property
    def retryable_count(self) -> int:
        return sum(
            1
            for diagnosis in self.diagnoses
            for observation in diagnosis.observations
            if observation.retryable
        )

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


def latest_workflow_runs(
    runs: Sequence[WorkflowRunEvidence],
    *,
    head_sha: str,
) -> Mapping[str, WorkflowRunEvidence]:
    if not valid_sha(head_sha):
        raise ValueError("head SHA must be canonical lowercase SHA")
    selected: dict[str, WorkflowRunEvidence] = {}
    for run in runs:
        if run.head_sha != head_sha:
            continue
        current = selected.get(run.name)
        if current is None or run.rank > current.rank:
            selected[run.name] = run
    return selected


__all__ = [
    "ActionReceipt",
    "BlockerKind",
    "BlockerObservation",
    "CheckRunEvidence",
    "ExecutionState",
    "PullRequestSubject",
    "RecoveryAction",
    "RecoveryActionKind",
    "RecoveryBudget",
    "RecoveryMode",
    "RecoveryPolicy",
    "RecoveryReport",
    "RecoverySubject",
    "Severity",
    "SubjectDiagnosis",
    "SubjectKind",
    "WorkflowJobEvidence",
    "WorkflowRunEvidence",
    "age_seconds",
    "canonical_json",
    "fingerprint",
    "iso_utc",
    "latest_workflow_runs",
    "parse_timestamp",
    "utc_now",
    "valid_context",
    "valid_ref",
    "valid_repository",
    "valid_sha",
]
