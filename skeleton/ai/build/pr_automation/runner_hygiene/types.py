"""Typed immutable primitives for the Pack E runner-hygiene control plane.

Side-effect free. Every value that can influence an admission or gate
decision is immutable, serializable, bounded, and fingerprintable.
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
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")
_CONTEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")
_LABEL_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,100}$")
_DELIVERY_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,240}$")
_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._+/-]{1,512}$")


def canonical_json(value: Any) -> str:
    """Encode a JSON-compatible value deterministically."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def fingerprint(value: Any) -> str:
    """Return a SHA-256 fingerprint of canonical JSON."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def valid_sha(value: str) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def valid_repository(value: str) -> bool:
    return isinstance(value, str) and _REPOSITORY_RE.fullmatch(value) is not None


def valid_ref(value: str) -> bool:
    if not isinstance(value, str) or _REF_RE.fullmatch(value) is None:
        return False
    if value.startswith("/") or value.endswith("/") or value.endswith("."):
        return False
    if ".." in value or "@{" in value:
        return False
    parts = value.split("/")
    if any(part in {"", ".", ".."} or part.endswith(".lock") for part in parts):
        return False
    return True


def valid_context(value: str) -> bool:
    return isinstance(value, str) and _CONTEXT_RE.fullmatch(value) is not None


def valid_label(value: str) -> bool:
    return isinstance(value, str) and _LABEL_RE.fullmatch(value) is not None


def valid_delivery_id(value: str) -> bool:
    return isinstance(value, str) and _DELIVERY_RE.fullmatch(value) is not None


def valid_posix_path(value: str) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return False
    return _PATH_RE.fullmatch(value) is not None


def _tuple_text(values: Iterable[str], *, lower: bool = False, limit: int = 512) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise TypeError("expected string value")
        value = raw.strip()
        if lower:
            value = value.casefold()
        if not value:
            raise ValueError("empty string is not allowed")
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) > limit:
            raise ValueError(f"tuple exceeds bound of {limit}")
    return tuple(out)


class HygieneMode(StrEnum):
    OBSERVE = "observe"
    ADMIT_ONLY = "admit_only"
    REPORT = "report"


class HygieneVerdict(StrEnum):
    ALLOW = "allow"
    HOLD = "hold"
    DENY = "deny"
    OBSERVE = "observe"
    INCOMPLETE = "incomplete"


class GateState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    MISSING = "missing"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class TrustSurface(StrEnum):
    CODE = "code"
    WORKFLOW = "workflow"
    SECURITY = "security"
    DEPENDENCY = "dependency"
    DOCS = "docs"
    RELEASE = "release"
    UNKNOWN = "unknown"


class PaginationStatus(StrEnum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"
    ERROR = "error"


class SweepTrigger(StrEnum):
    SCHEDULE = "schedule"
    WORKFLOW_DISPATCH = "workflow_dispatch"
    WORKFLOW_RUN = "workflow_run"
    PUSH = "push"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    full_name: str

    def __post_init__(self) -> None:
        if not valid_repository(self.full_name):
            raise ValueError("invalid repository full_name")

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.full_name.split("/", 1)[1]

    def fingerprint(self) -> str:
        return fingerprint({"full_name": self.full_name})


@dataclass(frozen=True, slots=True)
class HeadBinding:
    """Exact-head identity used at every mutation/admission boundary."""

    repository: str
    pr_number: int
    head_sha: str
    head_ref: str
    head_repository: str
    base_ref: str
    base_sha: str

    def __post_init__(self) -> None:
        if not valid_repository(self.repository):
            raise ValueError("invalid repository")
        if self.pr_number <= 0:
            raise ValueError("pr_number must be positive")
        if not valid_sha(self.head_sha):
            raise ValueError("head_sha must be canonical lowercase SHA-1")
        if not valid_ref(self.head_ref):
            raise ValueError("invalid head_ref")
        if not valid_repository(self.head_repository):
            raise ValueError("invalid head_repository")
        if not valid_ref(self.base_ref):
            raise ValueError("invalid base_ref")
        if not valid_sha(self.base_sha):
            raise ValueError("base_sha must be canonical lowercase SHA-1")

    @property
    def same_repository_head(self) -> bool:
        return self.repository.casefold() == self.head_repository.casefold()

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))

    def binding_key(self) -> str:
        return f"{self.repository}#{self.pr_number}@{self.head_sha}"


@dataclass(frozen=True, slots=True)
class CheckObservation:
    context: str
    state: GateState
    head_sha: str
    provider: str
    updated_at: str | None = None
    target_url: str | None = None

    def __post_init__(self) -> None:
        if not valid_context(self.context):
            raise ValueError("invalid check context")
        if not valid_sha(self.head_sha):
            raise ValueError("check head_sha must be canonical")
        if not self.provider or not valid_context(self.provider):
            raise ValueError("invalid check provider")

    def matches_head(self, expected: str) -> bool:
        return valid_sha(expected) and self.head_sha == expected


@dataclass(frozen=True, slots=True)
class ReviewObservation:
    login: str
    state: str
    commit_id: str | None
    submitted_at: str | None = None

    def __post_init__(self) -> None:
        if not self.login or not valid_label(self.login):
            raise ValueError("invalid review login")
        if not self.state:
            raise ValueError("review state required")
        if self.commit_id is not None and not valid_sha(self.commit_id):
            raise ValueError("review commit_id must be canonical SHA when present")

    def matches_head(self, expected: str) -> bool:
        return self.commit_id is not None and self.commit_id == expected


@dataclass(frozen=True, slots=True)
class PathObservation:
    path: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0

    def __post_init__(self) -> None:
        if not valid_posix_path(self.path):
            raise ValueError(f"invalid path: {self.path!r}")
        if self.additions < 0 or self.deletions < 0:
            raise ValueError("negative diff counts are not allowed")
        if self.status not in {"added", "modified", "removed", "renamed", "copied", "changed", "unchanged"}:
            raise ValueError(f"unknown path status: {self.status}")


@dataclass(frozen=True, slots=True)
class PaginationCursor:
    """Fail-closed pagination evidence.

    Incomplete or unknown pagination must never authorize a positive admission.
    """

    status: PaginationStatus
    pages_fetched: int
    per_page: int
    max_pages: int
    items_seen: int
    truncated: bool = False
    error: str | None = None

    def __post_init__(self) -> None:
        if self.pages_fetched < 0 or self.per_page <= 0 or self.max_pages <= 0:
            raise ValueError("invalid pagination bounds")
        if self.items_seen < 0:
            raise ValueError("items_seen must be non-negative")
        if self.pages_fetched > self.max_pages:
            raise ValueError("pages_fetched exceeds max_pages")

    @property
    def is_complete(self) -> bool:
        return self.status is PaginationStatus.COMPLETE and not self.truncated and self.error is None

    def deny_reason(self) -> str | None:
        if self.status is PaginationStatus.COMPLETE and not self.truncated and self.error is None:
            return None
        if self.status is PaginationStatus.TRUNCATED or self.truncated:
            return "pagination_truncated"
        if self.status is PaginationStatus.ERROR or self.error:
            return "pagination_error"
        return "pagination_incomplete"


@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    remaining: int | None
    limit: int | None
    reset_at: str | None = None
    resource: str = "core"

    def __post_init__(self) -> None:
        if self.remaining is not None and self.remaining < 0:
            raise ValueError("remaining cannot be negative")
        if self.limit is not None and self.limit < 0:
            raise ValueError("limit cannot be negative")
        if not self.resource:
            raise ValueError("resource required")

    @property
    def known(self) -> bool:
        return self.remaining is not None and self.limit is not None

    def below(self, threshold: int) -> bool:
        if not self.known:
            return True  # fail closed: unknown quota is treated as depleted
        assert self.remaining is not None
        return self.remaining < threshold


@dataclass(frozen=True, slots=True)
class HygienePolicy:
    """Fail-closed defaults for Pack E hygiene evaluation."""

    mode: HygieneMode = HygieneMode.OBSERVE
    allowed_bases: tuple[str, ...] = ("main",)
    protected_base_required: bool = True
    require_same_repository_head: bool = True
    require_exact_head_checks: bool = True
    require_exact_head_reviews: bool = True
    fail_closed_pagination: bool = True
    observe_only_on_schedule: bool = True
    min_rate_limit_remaining: int = 50
    max_changed_files: int = 250
    max_line_delta: int = 20_000
    max_pages: int = 20
    per_page: int = 100
    required_check_contexts: tuple[str, ...] = (
        "CI/CD",
        "Merge Readiness",
        "Secret scanning",
        "Malware Gate",
        "Repository Hygiene Gate",
    )
    privileged_path_prefixes: tuple[str, ...] = (
        ".github/workflows/",
        ".github/actions/",
        "skeleton/pr_automation/",
        "skeleton/security/",
        "scripts/check_",
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_bases", _tuple_text(self.allowed_bases))
        object.__setattr__(
            self,
            "required_check_contexts",
            _tuple_text(self.required_check_contexts),
        )
        object.__setattr__(
            self,
            "privileged_path_prefixes",
            _tuple_text(self.privileged_path_prefixes),
        )
        if self.min_rate_limit_remaining < 0:
            raise ValueError("min_rate_limit_remaining must be non-negative")
        if self.max_changed_files <= 0 or self.max_line_delta <= 0:
            raise ValueError("size bounds must be positive")
        if self.max_pages <= 0 or self.per_page <= 0:
            raise ValueError("pagination bounds must be positive")
        # Security non-weaken: these may not be turned off via constructor tricks
        # that leave booleans as non-bool; coerce unknown to True (fail closed).
        for name in (
            "protected_base_required",
            "require_same_repository_head",
            "require_exact_head_checks",
            "require_exact_head_reviews",
            "fail_closed_pagination",
            "observe_only_on_schedule",
        ):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be bool")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))

    def with_mode(self, mode: HygieneMode) -> "HygienePolicy":
        return HygienePolicy(
            mode=mode,
            allowed_bases=self.allowed_bases,
            protected_base_required=self.protected_base_required,
            require_same_repository_head=self.require_same_repository_head,
            require_exact_head_checks=self.require_exact_head_checks,
            require_exact_head_reviews=self.require_exact_head_reviews,
            fail_closed_pagination=self.fail_closed_pagination,
            observe_only_on_schedule=self.observe_only_on_schedule,
            min_rate_limit_remaining=self.min_rate_limit_remaining,
            max_changed_files=self.max_changed_files,
            max_line_delta=self.max_line_delta,
            max_pages=self.max_pages,
            per_page=self.per_page,
            required_check_contexts=self.required_check_contexts,
            privileged_path_prefixes=self.privileged_path_prefixes,
        )


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    message: str
    subject: str = ""

    def __post_init__(self) -> None:
        if not self.code or not self.severity or not self.message:
            raise ValueError("finding requires code, severity, and message")
        if self.severity not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError(f"unknown severity: {self.severity}")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "subject": self.subject,
        }


@dataclass(frozen=True, slots=True)
class HygieneReport:
    verdict: HygieneVerdict
    reasons: tuple[str, ...]
    findings: tuple[Finding, ...] = ()
    binding_fingerprint: str = ""
    policy_fingerprint: str = ""
    mode: HygieneMode = HygieneMode.OBSERVE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "findings": [f.to_dict() for f in self.findings],
            "binding_fingerprint": self.binding_fingerprint,
            "policy_fingerprint": self.policy_fingerprint,
            "mode": self.mode.value,
            "metadata": dict(self.metadata),
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


__all__ = [
    "CheckObservation",
    "Finding",
    "GateState",
    "HeadBinding",
    "HygieneMode",
    "HygienePolicy",
    "HygieneReport",
    "HygieneVerdict",
    "PaginationCursor",
    "PaginationStatus",
    "PathObservation",
    "RateLimitSnapshot",
    "RepositoryRef",
    "ReviewObservation",
    "SweepTrigger",
    "TrustSurface",
    "canonical_json",
    "fingerprint",
    "parse_timestamp",
    "utc_now",
    "valid_context",
    "valid_delivery_id",
    "valid_label",
    "valid_posix_path",
    "valid_ref",
    "valid_repository",
    "valid_sha",
]
