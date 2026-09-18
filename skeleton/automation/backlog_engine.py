"""Deterministic durable backlog correlation for repository automation.

This plane is intentionally model-independent.  Raw repository/user text is
stored for human audit but is never emitted into model context.  Model-facing
context contains only validated machine metadata and cryptographic digests.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable, Mapping, Sequence

from .repair_policy import RepairDecision, classify_change


SCHEMA_VERSION = 1
MAX_STATE_BYTES = 8 * 1024 * 1024
MAX_ROOT_CAUSES = 2_000
MAX_EVENTS = 100_000
MAX_EVENTS_PER_ROOT = 128
MAX_EVIDENCE_PER_ROOT = 128
MAX_SUMMARY_CHARS = 4_096
MAX_MODEL_ROOTS = 100

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_.:/-]{0,191}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_ALLOWED_STATUS = {"open", "resolved", "quarantined"}


class BacklogStateError(RuntimeError):
    """Raised when durable backlog state is invalid or cannot be trusted."""


class BacklogCapacityError(BacklogStateError):
    """Raised instead of silently evicting durable correlation evidence."""


def _text(name: str, value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds maximum length")
    if _CONTROL_RE.search(value):
        raise ValueError(f"{name} contains control characters")
    return value


def _token(name: str, value: object) -> str:
    normalized = _text(name, value, maximum=192).casefold()
    if _TOKEN_RE.fullmatch(normalized) is None:
        raise ValueError(f"{name} must be a canonical machine token")
    return normalized


def _summary(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("summary must be a string")
    value = value.strip()
    if len(value) > MAX_SUMMARY_CHARS:
        raise ValueError("summary exceeds maximum length")
    return value


def _risk(value: object) -> str:
    normalized = _text("risk", value, maximum=16).casefold()
    if normalized not in _RISK_ORDER:
        raise ValueError("risk must be low, medium, high, or critical")
    return normalized


def _signature(value: object) -> str:
    raw = _text("signature", value, maximum=2_048)
    return " ".join(raw.casefold().split())


def _digest(*parts: object) -> str:
    encoded = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bounded_unique(values: Iterable[object], *, name: str, maximum: int) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _text(name, raw, maximum=512)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) > maximum:
            raise BacklogCapacityError(f"{name} exceeds bounded capacity")
    return tuple(result)


def _merge_bounded(
    current: Sequence[str],
    additions: Sequence[str],
    *,
    maximum: int,
) -> tuple[str, ...]:
    result = list(current)
    seen = set(result)
    for value in additions:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    if len(result) > maximum:
        result = result[-maximum:]
    return tuple(result)


def _max_risk(left: str, right: str) -> str:
    return left if _RISK_ORDER[left] >= _RISK_ORDER[right] else right


@dataclass(frozen=True, slots=True)
class BacklogFinding:
    event_id: str
    source: str
    category: str
    component: str
    signature: str
    observed_at: int
    summary: str = ""
    risk: str = "medium"
    security_finding: bool = False
    external_id: str | None = None
    head_sha: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _text("event_id", self.event_id, maximum=256))
        object.__setattr__(self, "source", _token("source", self.source))
        object.__setattr__(self, "category", _token("category", self.category))
        object.__setattr__(self, "component", _token("component", self.component))
        object.__setattr__(self, "signature", _signature(self.signature))
        if isinstance(self.observed_at, bool) or not isinstance(self.observed_at, int):
            raise TypeError("observed_at must be an integer")
        if self.observed_at < 0:
            raise ValueError("observed_at must be non-negative")
        object.__setattr__(self, "summary", _summary(self.summary))
        object.__setattr__(self, "risk", _risk(self.risk))
        if not isinstance(self.security_finding, bool):
            raise TypeError("security_finding must be boolean")
        if self.external_id is not None:
            object.__setattr__(
                self,
                "external_id",
                _text("external_id", self.external_id, maximum=256),
            )
        if self.head_sha is not None:
            sha = _text("head_sha", self.head_sha, maximum=40).casefold()
            if _SHA_RE.fullmatch(sha) is None:
                raise ValueError("head_sha must be a 40-character hex commit OID")
            object.__setattr__(self, "head_sha", sha)
        object.__setattr__(
            self,
            "evidence_refs",
            _bounded_unique(
                self.evidence_refs,
                name="evidence_ref",
                maximum=32,
            ),
        )

    @property
    def root_id(self) -> str:
        return _digest("root-v1", self.category, self.component, self.signature)

    @property
    def signature_digest(self) -> str:
        return _digest("signature-v1", self.signature)

    @property
    def summary_digest(self) -> str:
        return _digest("summary-v1", self.summary)

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "category": self.category,
            "component": self.component,
            "signature": self.signature,
            "observed_at": self.observed_at,
            "summary": self.summary,
            "risk": self.risk,
            "security_finding": self.security_finding,
            "external_id": self.external_id,
            "head_sha": self.head_sha,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "BacklogFinding":
        return cls(
            event_id=payload.get("event_id"),
            source=payload.get("source"),
            category=payload.get("category"),
            component=payload.get("component"),
            signature=payload.get("signature"),
            observed_at=payload.get("observed_at"),
            summary=payload.get("summary", ""),
            risk=payload.get("risk", "medium"),
            security_finding=payload.get("security_finding", False),
            external_id=payload.get("external_id"),
            head_sha=payload.get("head_sha"),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
        )


@dataclass(frozen=True, slots=True)
class RootCauseRecord:
    root_id: str
    category: str
    component: str
    signature_digest: str
    first_seen: int
    last_seen: int
    occurrences: int
    risk: str
    security_finding: bool
    status: str = "open"
    reopened_count: int = 0
    event_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    latest_summary: str = ""
    latest_summary_digest: str = ""

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.root_id):
            raise BacklogStateError("root_id must be sha256")
        object.__setattr__(self, "category", _token("category", self.category))
        object.__setattr__(self, "component", _token("component", self.component))
        if not re.fullmatch(r"[0-9a-f]{64}", self.signature_digest):
            raise BacklogStateError("signature_digest must be sha256")
        for name in ("first_seen", "last_seen", "occurrences", "reopened_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BacklogStateError(f"{name} must be a non-negative integer")
        if self.occurrences < 1:
            raise BacklogStateError("occurrences must be positive")
        if self.first_seen > self.last_seen:
            raise BacklogStateError("first_seen cannot be after last_seen")
        object.__setattr__(self, "risk", _risk(self.risk))
        if not isinstance(self.security_finding, bool):
            raise BacklogStateError("security_finding must be boolean")
        if self.status not in _ALLOWED_STATUS:
            raise BacklogStateError("invalid root-cause status")
        if len(self.event_ids) > MAX_EVENTS_PER_ROOT:
            raise BacklogStateError("event history exceeds maximum")
        if len(set(self.event_ids)) != len(self.event_ids):
            raise BacklogStateError("duplicate event id in root record")
        if len(self.evidence_refs) > MAX_EVIDENCE_PER_ROOT:
            raise BacklogStateError("evidence history exceeds maximum")
        object.__setattr__(self, "latest_summary", _summary(self.latest_summary))
        if self.latest_summary_digest and not re.fullmatch(
            r"[0-9a-f]{64}", self.latest_summary_digest
        ):
            raise BacklogStateError("latest_summary_digest must be sha256")

    @classmethod
    def from_finding(cls, finding: BacklogFinding) -> "RootCauseRecord":
        risk = "high" if finding.security_finding and _RISK_ORDER[finding.risk] < 2 else finding.risk
        return cls(
            root_id=finding.root_id,
            category=finding.category,
            component=finding.component,
            signature_digest=finding.signature_digest,
            first_seen=finding.observed_at,
            last_seen=finding.observed_at,
            occurrences=1,
            risk=risk,
            security_finding=finding.security_finding,
            event_ids=(finding.event_id,),
            evidence_refs=finding.evidence_refs,
            latest_summary=finding.summary,
            latest_summary_digest=finding.summary_digest,
        )

    def ingest(self, finding: BacklogFinding) -> "RootCauseRecord":
        if finding.root_id != self.root_id:
            raise BacklogStateError("finding does not belong to root cause")
        if finding.event_id in self.event_ids:
            return self
        reopened = self.reopened_count + (1 if self.status == "resolved" else 0)
        risk = finding.risk
        if finding.security_finding and _RISK_ORDER[risk] < 2:
            risk = "high"
        return replace(
            self,
            first_seen=min(self.first_seen, finding.observed_at),
            last_seen=max(self.last_seen, finding.observed_at),
            occurrences=self.occurrences + 1,
            risk=_max_risk(self.risk, risk),
            security_finding=self.security_finding or finding.security_finding,
            status="open" if self.status == "resolved" else self.status,
            reopened_count=reopened,
            event_ids=_merge_bounded(
                self.event_ids,
                (finding.event_id,),
                maximum=MAX_EVENTS_PER_ROOT,
            ),
            evidence_refs=_merge_bounded(
                self.evidence_refs,
                finding.evidence_refs,
                maximum=MAX_EVIDENCE_PER_ROOT,
            ),
            latest_summary=finding.summary,
            latest_summary_digest=finding.summary_digest,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "root_id": self.root_id,
            "category": self.category,
            "component": self.component,
            "signature_digest": self.signature_digest,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "occurrences": self.occurrences,
            "risk": self.risk,
            "security_finding": self.security_finding,
            "status": self.status,
            "reopened_count": self.reopened_count,
            "event_ids": list(self.event_ids),
            "evidence_refs": list(self.evidence_refs),
            "latest_summary": self.latest_summary,
            "latest_summary_digest": self.latest_summary_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "RootCauseRecord":
        return cls(
            root_id=payload.get("root_id"),
            category=payload.get("category"),
            component=payload.get("component"),
            signature_digest=payload.get("signature_digest"),
            first_seen=payload.get("first_seen"),
            last_seen=payload.get("last_seen"),
            occurrences=payload.get("occurrences"),
            risk=payload.get("risk"),
            security_finding=payload.get("security_finding"),
            status=payload.get("status", "open"),
            reopened_count=payload.get("reopened_count", 0),
            event_ids=tuple(payload.get("event_ids", ())),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
            latest_summary=payload.get("latest_summary", ""),
            latest_summary_digest=payload.get("latest_summary_digest", ""),
        )


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source: str
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    circuit_open: bool = False
    last_error_digest: str = ""

    def __post_init__(self) -> None:
        _token("source", self.source)
        for name in ("consecutive_failures", "total_failures", "total_successes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BacklogStateError(f"{name} must be non-negative")
        if not isinstance(self.circuit_open, bool):
            raise BacklogStateError("circuit_open must be boolean")
        if self.last_error_digest and not re.fullmatch(
            r"[0-9a-f]{64}", self.last_error_digest
        ):
            raise BacklogStateError("last_error_digest must be sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "circuit_open": self.circuit_open,
            "last_error_digest": self.last_error_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SourceHealth":
        return cls(
            source=payload.get("source"),
            consecutive_failures=payload.get("consecutive_failures", 0),
            total_failures=payload.get("total_failures", 0),
            total_successes=payload.get("total_successes", 0),
            circuit_open=payload.get("circuit_open", False),
            last_error_digest=payload.get("last_error_digest", ""),
        )


@dataclass(slots=True)
class BacklogState:
    sequence: int = 0
    roots: dict[str, RootCauseRecord] = field(default_factory=dict)
    events: dict[str, str] = field(default_factory=dict)
    sources: dict[str, SourceHealth] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise BacklogStateError("sequence must be a non-negative integer")
        if len(self.roots) > MAX_ROOT_CAUSES:
            raise BacklogCapacityError("root-cause capacity exceeded")
        if len(self.events) > MAX_EVENTS:
            raise BacklogCapacityError("event capacity exceeded")
        for root_id, record in self.roots.items():
            if root_id != record.root_id:
                raise BacklogStateError("root map key mismatch")
        for _event_id, root_id in self.events.items():
            if root_id not in self.roots:
                raise BacklogStateError("event references unknown root")
        # Root event_ids are an intentionally bounded recent audit sample.
        # The global event map remains the full idempotency index, so older
        # events need not remain in a hot root's bounded event_ids tuple.
        for source, health in self.sources.items():
            if source != health.source:
                raise BacklogStateError("source map key mismatch")

    def ingest(self, finding: BacklogFinding) -> tuple[RootCauseRecord, bool]:
        known_root = self.events.get(finding.event_id)
        if known_root is not None:
            if known_root != finding.root_id:
                raise BacklogStateError("event id was reused for a different root cause")
            return self.roots[known_root], False
        if len(self.events) >= MAX_EVENTS:
            raise BacklogCapacityError("event capacity exceeded")

        record = self.roots.get(finding.root_id)
        if record is None:
            if len(self.roots) >= MAX_ROOT_CAUSES:
                raise BacklogCapacityError("root-cause capacity exceeded")
            record = RootCauseRecord.from_finding(finding)
        else:
            record = record.ingest(finding)

        self.roots[record.root_id] = record
        self.events[finding.event_id] = record.root_id
        self.sequence += 1
        return record, True

    def ingest_many(self, findings: Iterable[BacklogFinding]) -> tuple[str, ...]:
        changed: list[str] = []
        for finding in sorted(tuple(findings), key=lambda item: item.event_id):
            record, created = self.ingest(finding)
            if created:
                changed.append(record.root_id)
        return tuple(changed)

    def resolve(self, root_id: str, *, evidence_ref: str) -> RootCauseRecord:
        root_id = _text("root_id", root_id, maximum=64)
        record = self.roots.get(root_id)
        if record is None:
            raise KeyError(root_id)
        evidence = _text("evidence_ref", evidence_ref, maximum=512)
        updated = replace(
            record,
            status="resolved",
            evidence_refs=_merge_bounded(
                record.evidence_refs,
                (evidence,),
                maximum=MAX_EVIDENCE_PER_ROOT,
            ),
        )
        self.roots[root_id] = updated
        self.sequence += 1
        return updated

    def quarantine(self, root_id: str, *, evidence_ref: str) -> RootCauseRecord:
        root_id = _text("root_id", root_id, maximum=64)
        record = self.roots.get(root_id)
        if record is None:
            raise KeyError(root_id)
        evidence = _text("evidence_ref", evidence_ref, maximum=512)
        updated = replace(
            record,
            status="quarantined",
            risk=_max_risk(record.risk, "high"),
            evidence_refs=_merge_bounded(
                record.evidence_refs,
                (evidence,),
                maximum=MAX_EVIDENCE_PER_ROOT,
            ),
        )
        self.roots[root_id] = updated
        self.sequence += 1
        return updated

    def record_source_failure(
        self,
        source: str,
        *,
        error_code: str,
        threshold: int = 3,
    ) -> SourceHealth:
        source = _token("source", source)
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ValueError("threshold must be a positive integer")
        code = _token("error_code", error_code)
        current = self.sources.get(source, SourceHealth(source))
        failures = current.consecutive_failures + 1
        updated = replace(
            current,
            consecutive_failures=failures,
            total_failures=current.total_failures + 1,
            circuit_open=failures >= threshold,
            last_error_digest=_digest("source-error-v1", code),
        )
        self.sources[source] = updated
        self.sequence += 1
        return updated

    def record_source_success(self, source: str) -> SourceHealth:
        source = _token("source", source)
        current = self.sources.get(source, SourceHealth(source))
        updated = replace(
            current,
            consecutive_failures=0,
            total_successes=current.total_successes + 1,
            circuit_open=False,
            last_error_digest="",
        )
        self.sources[source] = updated
        self.sequence += 1
        return updated

    def source_available(self, source: str) -> bool:
        source = _token("source", source)
        return not self.sources.get(source, SourceHealth(source)).circuit_open

    def proposal_decision(
        self,
        paths: Iterable[str],
        *,
        root_ids: Iterable[str] = (),
    ) -> RepairDecision:
        roots = []
        for root_id in root_ids:
            record = self.roots.get(str(root_id))
            if record is None:
                raise KeyError(root_id)
            roots.append(record)
        security = any(
            item.security_finding or item.risk in {"high", "critical"}
            for item in roots
        )
        return classify_change(paths, security_finding=security)

    def model_context(self, *, limit: int = 40) -> str:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_MODEL_ROOTS:
            raise ValueError(f"limit must be in [1,{MAX_MODEL_ROOTS}]")
        ordered = sorted(
            self.roots.values(),
            key=lambda item: (
                item.status != "open",
                -_RISK_ORDER[item.risk],
                -item.last_seen,
                item.root_id,
            ),
        )[:limit]
        payload = {
            "contract": {
                "raw_repository_text_included": False,
                "raw_issue_text_included": False,
                "policy_is_host_authoritative": True,
                "model_may_not_change_permissions_or_gates": True,
            },
            "sequence": self.sequence,
            "roots": [
                {
                    "root_id": item.root_id,
                    "category": item.category,
                    "component": item.component,
                    "risk": item.risk,
                    "security_finding": item.security_finding,
                    "status": item.status,
                    "occurrences": item.occurrences,
                    "reopened_count": item.reopened_count,
                    "first_seen": item.first_seen,
                    "last_seen": item.last_seen,
                    "summary_digest": item.latest_summary_digest,
                    "evidence_count": len(item.evidence_refs),
                }
                for item in ordered
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "sequence": self.sequence,
            "roots": [
                self.roots[key].to_dict()
                for key in sorted(self.roots)
            ],
            "events": {
                key: self.events[key]
                for key in sorted(self.events)
            },
            "sources": [
                self.sources[key].to_dict()
                for key in sorted(self.sources)
            ],
        }

    @property
    def fingerprint(self) -> str:
        return _digest("backlog-state-v1", _canonical_json(self.to_dict()))

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        state = self.to_dict()
        canonical = _canonical_json(state)
        envelope = {
            "checksum": _digest("backlog-state-envelope-v1", canonical),
            "state": state,
        }
        rendered = _canonical_json(envelope) + "\n"
        if len(rendered.encode("utf-8")) > MAX_STATE_BYTES:
            raise BacklogCapacityError("serialized state exceeds maximum size")

        fd, raw_tmp = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            text=True,
        )
        tmp = Path(raw_tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, destination)
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            finally:
                raise

    @classmethod
    def load(cls, path: str | Path) -> "BacklogState":
        source = Path(path)
        with source.open("rb") as handle:
            raw = handle.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            raise BacklogCapacityError("state file exceeds maximum size")
        try:
            envelope = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError, BacklogStateError) as exc:
            raise BacklogStateError("state file is malformed") from exc
        if not isinstance(envelope, Mapping):
            raise BacklogStateError("state envelope must be an object")
        state = envelope.get("state")
        checksum = envelope.get("checksum")
        if not isinstance(state, Mapping) or not isinstance(checksum, str):
            raise BacklogStateError("state envelope is incomplete")
        canonical = _canonical_json(state)
        expected = _digest("backlog-state-envelope-v1", canonical)
        if not hmac.compare_digest(checksum, expected):
            raise BacklogStateError("state checksum mismatch")
        if state.get("schema_version") != SCHEMA_VERSION:
            raise BacklogStateError("unsupported state schema")
        roots_raw = state.get("roots")
        events_raw = state.get("events")
        sources_raw = state.get("sources")
        if not isinstance(roots_raw, list) or not isinstance(events_raw, Mapping) or not isinstance(sources_raw, list):
            raise BacklogStateError("state collections are malformed")
        roots = {}
        for item in roots_raw:
            if not isinstance(item, Mapping):
                raise BacklogStateError("root record is malformed")
            record = RootCauseRecord.from_dict(item)
            if record.root_id in roots:
                raise BacklogStateError("duplicate root record")
            roots[record.root_id] = record
        events: dict[str, str] = {}
        for event_id, root_id in events_raw.items():
            event = _text("event_id", event_id, maximum=256)
            root = _text("root_id", root_id, maximum=64)
            if event in events:
                raise BacklogStateError("duplicate event record")
            events[event] = root
        sources = {}
        for item in sources_raw:
            if not isinstance(item, Mapping):
                raise BacklogStateError("source health record is malformed")
            health = SourceHealth.from_dict(item)
            if health.source in sources:
                raise BacklogStateError("duplicate source health record")
            sources[health.source] = health
        return cls(
            sequence=state.get("sequence", 0),
            roots=roots,
            events=events,
            sources=sources,
        )

    @classmethod
    def load_or_empty(cls, path: str | Path) -> "BacklogState":
        try:
            return cls.load(path)
        except FileNotFoundError:
            return cls()


def workflow_failure_finding(
    *,
    workflow: str,
    head_sha: str,
    run_id: int,
    failed_jobs: Iterable[str],
    observed_at: int,
    summary: str = "",
    risk: str = "medium",
) -> BacklogFinding:
    workflow_name = _text("workflow", workflow, maximum=192)
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise ValueError("run_id must be a positive integer")
    sha = _text("head_sha", head_sha, maximum=40).casefold()
    if _SHA_RE.fullmatch(sha) is None:
        raise ValueError("head_sha must be a 40-character hex commit OID")
    jobs = sorted(
        {
            _text("failed_job", item, maximum=192).casefold()
            for item in failed_jobs
        }
    )
    if not jobs:
        jobs = ["workflow-failure"]
    component_slug = re.sub(r"[^a-z0-9_.-]+", "-", workflow_name.casefold()).strip("-")
    if not component_slug:
        component_slug = "unknown"
    component = f"workflow:{component_slug[:150]}"
    signature = _digest("workflow-failure-v1", workflow_name.casefold(), *jobs)
    return BacklogFinding(
        event_id=f"workflow:{run_id}:{sha}",
        source="github.actions",
        category="workflow.failure",
        component=component,
        signature=signature,
        observed_at=observed_at,
        summary=summary,
        risk=risk,
        external_id=str(run_id),
        head_sha=sha,
        evidence_refs=(f"workflow-run:{run_id}",),
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _no_duplicates(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BacklogStateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
