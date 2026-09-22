"""Typed contracts for the autonomous feature build plane.

Model output is inert proposal data. This module contains no GitHub mutation,
subprocess execution, or provider calls. It normalizes and bounds architecture
plans, implementation shards, reviews, and final candidate evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .free_model import redact_secrets
from .supervisor_runtime import canonical_json


DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
PATH_RE = re.compile(r"^[A-Za-z0-9._+@/-]{1,320}$")
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

DEFAULT_MAX_FILES = 36
DEFAULT_MAX_TOTAL_BYTES = 1_200_000
DEFAULT_MAX_FILE_BYTES = 180_000
HARD_MAX_FILE_BYTES = 500_000
DEFAULT_MAX_CHANGED_LINES = 9_000
DEFAULT_MAX_CONTEXT_BYTES = 240_000
DEFAULT_MAX_MODEL_CALLS = 16
DEFAULT_MAX_REVIEW_FINDINGS = 24
DEFAULT_MAX_TEST_INTENTS = 40
DEFAULT_MAX_IMPLEMENTATION_SHARDS = 8
DEFAULT_MAX_ROUNDS = 3

MAX_SUMMARY_BYTES = 8_000
MAX_REASON_BYTES = 4_000
MAX_ACCEPTANCE_BYTES = 2_000


class BuildContractError(ValueError):
    """Untrusted build data violated a deterministic contract."""


def _bounded_text(
    value: object,
    *,
    label: str,
    limit: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise BuildContractError(f"{label} must be text")
    clean = redact_secrets(value).strip()
    if not clean and not allow_empty:
        raise BuildContractError(f"{label} must not be empty")
    if "\x00" in clean:
        raise BuildContractError(f"{label} contains NUL")
    if len(clean.encode("utf-8")) > limit:
        raise BuildContractError(f"{label} exceeds byte budget")
    return clean


def _bounded_content(
    value: object,
    *,
    label: str,
    limit: int,
) -> str:
    """Validate source text without trimming, redacting, or rewriting bytes."""
    if not isinstance(value, str):
        raise BuildContractError(f"{label} must be text")
    if "\x00" in value:
        raise BuildContractError(f"{label} contains NUL")
    if len(value.encode("utf-8")) > limit:
        raise BuildContractError(f"{label} exceeds byte budget")
    return value


def _bounded_int(
    value: object,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BuildContractError(f"{label} must be an integer")
    if value < minimum or value > maximum:
        raise BuildContractError(f"{label} is outside bounds")
    return value


def _strict_object(
    value: object,
    *,
    label: str,
    required: set[str],
    optional: set[str] | None = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BuildContractError(f"{label} must be an object")
    optional = optional or set()
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise BuildContractError(
            f"{label} missing fields: {sorted(missing)!r}"
        )
    if unknown:
        raise BuildContractError(
            f"{label} has unsupported fields: {sorted(unknown)!r}"
        )
    return value


def _path(value: object) -> str:
    text = _bounded_text(value, label="path", limit=320)
    if (
        PATH_RE.fullmatch(text) is None
        or text.startswith("/")
        or "\\" in text
        or "//" in text
    ):
        raise BuildContractError("invalid repository path")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BuildContractError("invalid repository path component")
    return text


def _digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise BuildContractError(f"invalid {label}")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _bounded_text(value, label=label, limit=64)
    if IDENTIFIER_RE.fullmatch(text) is None:
        raise BuildContractError(f"invalid {label}")
    return text


def _text_tuple(
    value: object,
    *,
    label: str,
    max_items: int,
    max_item_bytes: int,
) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BuildContractError(f"{label} must be a list")
    if len(value) > max_items:
        raise BuildContractError(f"{label} exceeds item budget")
    return tuple(
        _bounded_text(
            item,
            label=f"{label} item",
            limit=max_item_bytes,
        )
        for item in value
    )


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildContractError(
                f"duplicate JSON field: {key}"
            )
        result[key] = value
    return result


def strict_json_loads(raw: str) -> Any:
    """Decode JSON while rejecting duplicate keys."""
    if not isinstance(raw, str):
        raise BuildContractError("JSON payload must be text")
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs)
    except json.JSONDecodeError as exc:
        raise BuildContractError("invalid JSON payload") from exc


def extract_json_object(raw: str) -> Mapping[str, Any]:
    """Extract exactly one JSON object from a provider response."""
    if not isinstance(raw, str):
        raise BuildContractError("model response must be text")
    text = raw.strip()
    fence = chr(96) * 3
    if text.startswith(fence + "json"):
        text = text[len(fence + "json"):].lstrip()
    elif text.startswith(fence):
        text = text[len(fence):].lstrip()

    start = text.find("{")
    if start < 0:
        raise BuildContractError("model returned no JSON object")

    decoder = json.JSONDecoder(object_pairs_hook=_unique_pairs)
    try:
        value, end = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise BuildContractError("model returned invalid JSON") from exc

    trailing = text[start + end:].strip()
    if trailing not in {"", fence}:
        raise BuildContractError(
            "model returned trailing non-JSON content"
        )
    if not isinstance(value, Mapping):
        raise BuildContractError("model response must be a JSON object")
    return value


@dataclass(frozen=True, slots=True)
class BuildBudget:
    max_files: int = DEFAULT_MAX_FILES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_changed_lines: int = DEFAULT_MAX_CHANGED_LINES
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES
    max_model_calls: int = DEFAULT_MAX_MODEL_CALLS
    max_review_findings: int = DEFAULT_MAX_REVIEW_FINDINGS
    max_test_intents: int = DEFAULT_MAX_TEST_INTENTS
    max_implementation_shards: int = DEFAULT_MAX_IMPLEMENTATION_SHARDS
    max_rounds: int = DEFAULT_MAX_ROUNDS

    def __post_init__(self) -> None:
        bounds = (
            ("max_files", self.max_files, 1, 64),
            ("max_total_bytes", self.max_total_bytes, 1_000, 4_000_000),
            ("max_file_bytes", self.max_file_bytes, 1_000, 500_000),
            ("max_changed_lines", self.max_changed_lines, 1, 20_000),
            ("max_context_bytes", self.max_context_bytes, 10_000, 1_000_000),
            ("max_model_calls", self.max_model_calls, 1, 32),
            ("max_review_findings", self.max_review_findings, 1, 64),
            ("max_test_intents", self.max_test_intents, 1, 80),
            ("max_implementation_shards", self.max_implementation_shards, 1, 16),
            ("max_rounds", self.max_rounds, 1, 5),
        )
        for label, value, minimum, maximum in bounds:
            _bounded_int(
                value,
                label=label,
                minimum=minimum,
                maximum=maximum,
            )
        if self.max_file_bytes > self.max_total_bytes:
            raise BuildContractError(
                "per-file budget exceeds total byte budget"
            )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(self.as_dict())
        ).hexdigest()

    def as_dict(self) -> dict[str, int]:
        return {
            "max_files": self.max_files,
            "max_total_bytes": self.max_total_bytes,
            "max_file_bytes": self.max_file_bytes,
            "max_changed_lines": self.max_changed_lines,
            "max_context_bytes": self.max_context_bytes,
            "max_model_calls": self.max_model_calls,
            "max_review_findings": self.max_review_findings,
            "max_test_intents": self.max_test_intents,
            "max_implementation_shards": self.max_implementation_shards,
            "max_rounds": self.max_rounds,
        }


@dataclass(frozen=True, slots=True)
class FileIntent:
    path: str
    purpose: str
    operation: str
    dependencies: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(
            self,
            "purpose",
            _bounded_text(
                self.purpose,
                label="file intent purpose",
                limit=MAX_REASON_BYTES,
            ),
        )
        if self.operation not in {"create", "replace"}:
            raise BuildContractError("unsupported file intent operation")
        object.__setattr__(
            self,
            "dependencies",
            _text_tuple(
                self.dependencies,
                label="file intent dependencies",
                max_items=24,
                max_item_bytes=320,
            ),
        )
        object.__setattr__(
            self,
            "acceptance",
            _text_tuple(
                self.acceptance,
                label="file intent acceptance",
                max_items=16,
                max_item_bytes=MAX_ACCEPTANCE_BYTES,
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "purpose": self.purpose,
            "operation": self.operation,
            "dependencies": list(self.dependencies),
            "acceptance": list(self.acceptance),
        }

    @classmethod
    def from_payload(cls, value: object) -> "FileIntent":
        item = _strict_object(
            value,
            label="file intent",
            required={"path", "purpose", "operation"},
            optional={"dependencies", "acceptance"},
        )
        return cls(
            path=item["path"],
            purpose=item["purpose"],
            operation=item["operation"],
            dependencies=tuple(item.get("dependencies", ())),
            acceptance=tuple(item.get("acceptance", ())),
        )


@dataclass(frozen=True, slots=True)
class ArchitecturePlan:
    objective: str
    rationale: str
    files: tuple[FileIntent, ...]
    test_intents: tuple[str, ...]
    acceptance: tuple[str, ...]
    risks: tuple[str, ...]
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective",
            _bounded_text(
                self.objective,
                label="architecture objective",
                limit=MAX_SUMMARY_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "rationale",
            _bounded_text(
                self.rationale,
                label="architecture rationale",
                limit=MAX_SUMMARY_BYTES,
            ),
        )
        if not isinstance(self.files, tuple) or not self.files:
            raise BuildContractError("architecture plan must contain files")
        paths = [intent.path for intent in self.files]
        if len(paths) != len(set(paths)):
            raise BuildContractError("architecture plan contains duplicate paths")
        object.__setattr__(
            self,
            "test_intents",
            _text_tuple(
                self.test_intents,
                label="test intents",
                max_items=DEFAULT_MAX_TEST_INTENTS,
                max_item_bytes=MAX_ACCEPTANCE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "acceptance",
            _text_tuple(
                self.acceptance,
                label="architecture acceptance",
                max_items=32,
                max_item_bytes=MAX_ACCEPTANCE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "risks",
            _text_tuple(
                self.risks,
                label="architecture risks",
                max_items=24,
                max_item_bytes=MAX_REASON_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "assumptions",
            _text_tuple(
                self.assumptions,
                label="architecture assumptions",
                max_items=24,
                max_item_bytes=MAX_REASON_BYTES,
            ),
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(self.as_dict())
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "rationale": self.rationale,
            "files": [item.as_dict() for item in self.files],
            "test_intents": list(self.test_intents),
            "acceptance": list(self.acceptance),
            "risks": list(self.risks),
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_payload(
        cls,
        value: object,
        *,
        budget: BuildBudget,
    ) -> "ArchitecturePlan":
        item = _strict_object(
            value,
            label="architecture plan",
            required={
                "objective",
                "rationale",
                "files",
                "test_intents",
                "acceptance",
                "risks",
                "assumptions",
            },
        )
        raw_files = item["files"]
        if not isinstance(raw_files, list):
            raise BuildContractError("architecture files must be a list")
        if not raw_files:
            raise BuildContractError("architecture plan has no files")
        if len(raw_files) > budget.max_files:
            raise BuildContractError(
                "architecture plan exceeds file budget"
            )
        return cls(
            objective=item["objective"],
            rationale=item["rationale"],
            files=tuple(FileIntent.from_payload(entry) for entry in raw_files),
            test_intents=tuple(item["test_intents"]),
            acceptance=tuple(item["acceptance"]),
            risks=tuple(item["risks"]),
            assumptions=tuple(item["assumptions"]),
        )


@dataclass(frozen=True, slots=True)
class CandidateFile:
    path: str
    content: str
    intent: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(
            self,
            "content",
            _bounded_content(
                self.content,
                label=f"candidate content {self.path}",
                limit=HARD_MAX_FILE_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "intent",
            _bounded_text(
                self.intent,
                label="candidate intent",
                limit=MAX_REASON_BYTES,
                allow_empty=True,
            ),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            self.content.encode("utf-8")
        ).hexdigest()

    def as_dict(self, *, include_content: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "path": self.path,
            "intent": self.intent,
            "digest": self.digest,
            "bytes": len(self.content.encode("utf-8")),
            "lines": len(self.content.splitlines()),
        }
        if include_content:
            value["content"] = self.content
        return value


@dataclass(frozen=True, slots=True)
class ImplementationShard:
    shard_id: str
    summary: str
    files: tuple[CandidateFile, ...]
    tests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "shard_id",
            _identifier(self.shard_id, label="shard id"),
        )
        object.__setattr__(
            self,
            "summary",
            _bounded_text(
                self.summary,
                label="shard summary",
                limit=MAX_SUMMARY_BYTES,
                allow_empty=True,
            ),
        )
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise BuildContractError("shard contains duplicate paths")
        object.__setattr__(
            self,
            "tests",
            _text_tuple(
                self.tests,
                label="shard tests",
                max_items=DEFAULT_MAX_TEST_INTENTS,
                max_item_bytes=MAX_ACCEPTANCE_BYTES,
            ),
        )

    @classmethod
    def from_payload(
        cls,
        value: object,
        *,
        shard_id: str,
        budget: BuildBudget,
    ) -> "ImplementationShard":
        item = _strict_object(
            value,
            label="implementation shard",
            required={"summary", "files", "tests"},
        )
        raw_files = item["files"]
        if not isinstance(raw_files, list):
            raise BuildContractError("implementation files must be a list")
        if len(raw_files) > budget.max_files:
            raise BuildContractError("implementation shard exceeds file budget")
        files: list[CandidateFile] = []
        total = 0
        for entry in raw_files:
            obj = _strict_object(
                entry,
                label="candidate file",
                required={"path", "content"},
                optional={"intent"},
            )
            candidate = CandidateFile(
                path=obj["path"],
                content=obj["content"],
                intent=obj.get("intent", ""),
            )
            size = len(candidate.content.encode("utf-8"))
            if size > budget.max_file_bytes:
                raise BuildContractError(
                    f"candidate file exceeds configured budget: {candidate.path}"
                )
            total += size
            if total > budget.max_total_bytes:
                raise BuildContractError(
                    "implementation shard exceeds byte budget"
                )
            files.append(candidate)
        return cls(
            shard_id=shard_id,
            summary=item["summary"],
            files=tuple(files),
            tests=tuple(item["tests"]),
        )


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    severity: str
    category: str
    path: str
    message: str
    required: bool

    def __post_init__(self) -> None:
        if self.severity not in {"blocker", "high", "medium", "low"}:
            raise BuildContractError("invalid review severity")
        object.__setattr__(
            self,
            "category",
            _identifier(self.category, label="review category"),
        )
        path = _path(self.path) if self.path else ""
        object.__setattr__(self, "path", path)
        object.__setattr__(
            self,
            "message",
            _bounded_text(
                self.message,
                label="review message",
                limit=MAX_REASON_BYTES,
            ),
        )
        if not isinstance(self.required, bool):
            raise BuildContractError("review required flag must be boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "category": self.category,
            "path": self.path,
            "message": self.message,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class BuildReview:
    verdict: str
    summary: str
    findings: tuple[ReviewFinding, ...]
    confidence: int

    def __post_init__(self) -> None:
        if self.verdict not in {"accept", "repair", "reject"}:
            raise BuildContractError("invalid review verdict")
        object.__setattr__(
            self,
            "summary",
            _bounded_text(
                self.summary,
                label="review summary",
                limit=MAX_SUMMARY_BYTES,
            ),
        )
        _bounded_int(
            self.confidence,
            label="review confidence",
            minimum=0,
            maximum=100,
        )

    @property
    def required_findings(self) -> tuple[ReviewFinding, ...]:
        return tuple(item for item in self.findings if item.required)

    @classmethod
    def from_payload(
        cls,
        value: object,
        *,
        budget: BuildBudget,
    ) -> "BuildReview":
        item = _strict_object(
            value,
            label="build review",
            required={"verdict", "summary", "findings", "confidence"},
        )
        raw = item["findings"]
        if not isinstance(raw, list):
            raise BuildContractError("review findings must be a list")
        if len(raw) > budget.max_review_findings:
            raise BuildContractError("review findings exceed budget")
        findings = []
        for entry in raw:
            obj = _strict_object(
                entry,
                label="review finding",
                required={
                    "severity",
                    "category",
                    "path",
                    "message",
                    "required",
                },
            )
            findings.append(
                ReviewFinding(
                    severity=obj["severity"],
                    category=obj["category"],
                    path=obj["path"],
                    message=obj["message"],
                    required=obj["required"],
                )
            )
        return cls(
            verdict=item["verdict"],
            summary=item["summary"],
            findings=tuple(findings),
            confidence=item["confidence"],
        )


@dataclass(frozen=True, slots=True)
class BuildCandidate:
    summary: str
    files: tuple[CandidateFile, ...]
    tests: tuple[str, ...]
    architecture_fingerprint: str
    rounds: int
    model_calls: int
    reviews: tuple[BuildReview, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "summary",
            _bounded_text(
                self.summary,
                label="candidate summary",
                limit=MAX_SUMMARY_BYTES,
                allow_empty=True,
            ),
        )
        _digest(
            self.architecture_fingerprint,
            label="architecture fingerprint",
        )
        _bounded_int(
            self.rounds,
            label="candidate rounds",
            minimum=1,
            maximum=10,
        )
        _bounded_int(
            self.model_calls,
            label="candidate model calls",
            minimum=1,
            maximum=64,
        )
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise BuildContractError("candidate contains duplicate paths")
        object.__setattr__(
            self,
            "tests",
            _text_tuple(
                self.tests,
                label="candidate tests",
                max_items=DEFAULT_MAX_TEST_INTENTS,
                max_item_bytes=MAX_ACCEPTANCE_BYTES,
            ),
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "summary": self.summary,
                    "files": [
                        item.as_dict(include_content=False)
                        for item in self.files
                    ],
                    "tests": self.tests,
                    "architecture_fingerprint": self.architecture_fingerprint,
                    "rounds": self.rounds,
                    "model_calls": self.model_calls,
                    "reviews": [
                        {
                            "verdict": review.verdict,
                            "summary": review.summary,
                            "confidence": review.confidence,
                            "findings": [
                                finding.as_dict()
                                for finding in review.findings
                            ],
                        }
                        for review in self.reviews
                    ],
                }
            )
        ).hexdigest()


def merge_shards(
    shards: Iterable[ImplementationShard],
    *,
    architecture: ArchitecturePlan,
    budget: BuildBudget,
) -> tuple[CandidateFile, ...]:
    """Merge shards deterministically; later shards may replace planned paths."""
    allowed_paths = {intent.path for intent in architecture.files}
    merged: dict[str, CandidateFile] = {}
    for shard in shards:
        for candidate in shard.files:
            if candidate.path not in allowed_paths:
                raise BuildContractError(
                    f"implementation emitted unplanned path: {candidate.path}"
                )
            merged[candidate.path] = candidate

    if len(merged) > budget.max_files:
        raise BuildContractError("merged candidate exceeds file budget")

    total_bytes = 0
    for path in sorted(merged):
        size = len(merged[path].content.encode("utf-8"))
        if size > budget.max_file_bytes:
            raise BuildContractError(
                f"candidate file exceeds budget: {path}"
            )
        total_bytes += size
        if total_bytes > budget.max_total_bytes:
            raise BuildContractError(
                "merged candidate exceeds total byte budget"
            )
    return tuple(merged[path] for path in sorted(merged))


def candidate_public_summary(
    files: Sequence[CandidateFile],
) -> list[dict[str, object]]:
    """Content-free representation suitable for reviewer prompts/evidence."""
    return [
        item.as_dict(include_content=False)
        for item in sorted(files, key=lambda entry: entry.path)
    ]
