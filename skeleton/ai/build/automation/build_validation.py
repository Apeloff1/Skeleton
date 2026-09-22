"""Dependency-free deterministic validation for autonomous build candidates.

No candidate code is imported or executed here.  Validation is intentionally
structural: exact planned-path coverage, content budgets, parsers that operate
as data, secret/conflict-marker screening, and deterministic diagnostics.  The
normal pull-request CI remains the execution boundary for generated code.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
import tomllib
from typing import Iterable, Sequence

from .build_contracts import (
    ArchitecturePlan,
    BuildBudget,
    CandidateFile,
)
from .supervisor_runtime import canonical_json


SEVERITIES = frozenset({"blocker", "error", "warning", "info"})
BLOCKING_SEVERITIES = frozenset({"blocker", "error"})
MAX_DIAGNOSTICS = 128
MAX_LINE_BYTES = 32_000

_SECRET_PATTERNS = (
    (
        "private-key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
            re.IGNORECASE,
        ),
    ),
    (
        "github-token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "github-pat",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "openai-key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "aws-access-key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
)
_CONFLICT_MARKERS = (
    "<<<<<<< ",
    "=======",
    ">>>>>>> ",
)
_TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".json",
        ".toml",
        ".md",
        ".mdx",
        ".txt",
        ".yaml",
        ".yml",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".java",
        ".kt",
        ".kts",
        ".go",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
        ".css",
        ".scss",
        ".html",
        ".sql",
        ".graphql",
        ".sh",
    }
)


class BuildValidationError(RuntimeError):
    """Candidate failed a deterministic publishability invariant."""


def _unique_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


@dataclass(frozen=True, slots=True)
class ValidationDiagnostic:
    severity: str
    code: str
    path: str
    message: str
    line: int = 0

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError("invalid validation severity")
        if not self.code or len(self.code) > 80:
            raise ValueError("invalid validation code")
        if not isinstance(self.path, str):
            raise ValueError("invalid validation path")
        if not self.message or len(self.message.encode("utf-8")) > 2_000:
            raise ValueError("invalid validation message")
        if (
            isinstance(self.line, bool)
            or not isinstance(self.line, int)
            or self.line < 0
        ):
            raise ValueError("invalid validation line")

    @property
    def blocking(self) -> bool:
        return self.severity in BLOCKING_SEVERITIES

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "line": self.line,
        }


@dataclass(frozen=True, slots=True)
class FileValidation:
    path: str
    digest: str
    bytes: int
    lines: int
    diagnostics: tuple[ValidationDiagnostic, ...]

    @property
    def blocking(self) -> bool:
        return any(item.blocking for item in self.diagnostics)

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "digest": self.digest,
            "bytes": self.bytes,
            "lines": self.lines,
            "diagnostics": [
                item.as_dict()
                for item in self.diagnostics
            ],
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    files: tuple[FileValidation, ...]
    global_diagnostics: tuple[ValidationDiagnostic, ...]
    planned_paths: tuple[str, ...]
    candidate_paths: tuple[str, ...]
    total_bytes: int
    total_lines: int

    @property
    def diagnostics(self) -> tuple[ValidationDiagnostic, ...]:
        values = list(self.global_diagnostics)
        for item in self.files:
            values.extend(item.diagnostics)
        return tuple(values)

    @property
    def blocking_diagnostics(
        self,
    ) -> tuple[ValidationDiagnostic, ...]:
        return tuple(
            item
            for item in self.diagnostics
            if item.blocking
        )

    @property
    def publishable(self) -> bool:
        return not self.blocking_diagnostics

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(self.as_dict())
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "files": [item.as_dict() for item in self.files],
            "global_diagnostics": [
                item.as_dict()
                for item in self.global_diagnostics
            ],
            "planned_paths": list(self.planned_paths),
            "candidate_paths": list(self.candidate_paths),
            "total_bytes": self.total_bytes,
            "total_lines": self.total_lines,
        }

    def require_publishable(self) -> None:
        if self.publishable:
            return
        first = self.blocking_diagnostics[0]
        location = (
            f"{first.path}:{first.line}"
            if first.path and first.line
            else first.path or "candidate"
        )
        raise BuildValidationError(
            f"{first.code} at {location}: {first.message}"
        )


def _diagnostic(
    *,
    severity: str,
    code: str,
    path: str,
    message: str,
    line: int = 0,
) -> ValidationDiagnostic:
    return ValidationDiagnostic(
        severity=severity,
        code=code,
        path=path,
        message=message,
        line=line,
    )


def _text_lines(
    content: str,
) -> list[str]:
    return content.splitlines()


def _basic_text_checks(
    file: CandidateFile,
) -> list[ValidationDiagnostic]:
    path = file.path
    content = file.content
    result: list[ValidationDiagnostic] = []

    if "\x00" in content:
        result.append(
            _diagnostic(
                severity="blocker",
                code="nul-byte",
                path=path,
                message="text candidate contains a NUL byte",
            )
        )

    for number, line in enumerate(
        _text_lines(content),
        start=1,
    ):
        if any(line.startswith(marker) for marker in _CONFLICT_MARKERS):
            result.append(
                _diagnostic(
                    severity="blocker",
                    code="merge-conflict-marker",
                    path=path,
                    line=number,
                    message="unresolved merge conflict marker",
                )
            )
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            result.append(
                _diagnostic(
                    severity="error",
                    code="oversized-line",
                    path=path,
                    line=number,
                    message=(
                        "single text line exceeds deterministic "
                        "validation budget"
                    ),
                )
            )
        if len(result) >= MAX_DIAGNOSTICS:
            break

    for code, pattern in _SECRET_PATTERNS:
        match = pattern.search(content)
        if match is None:
            continue
        line = content.count("\n", 0, match.start()) + 1
        result.append(
            _diagnostic(
                severity="blocker",
                code=f"secret-{code}",
                path=path,
                line=line,
                message="candidate resembles embedded credential material",
            )
        )
        if len(result) >= MAX_DIAGNOSTICS:
            break

    if content and not content.endswith("\n"):
        result.append(
            _diagnostic(
                severity="warning",
                code="missing-final-newline",
                path=path,
                message="text candidate does not end with a newline",
            )
        )

    if not content:
        result.append(
            _diagnostic(
                severity="warning",
                code="empty-file",
                path=path,
                message="candidate file is empty",
            )
        )
    return result[:MAX_DIAGNOSTICS]


def _python_checks(
    file: CandidateFile,
) -> list[ValidationDiagnostic]:
    result: list[ValidationDiagnostic] = []
    try:
        tree = ast.parse(
            file.content,
            filename=file.path,
            type_comments=True,
        )
    except SyntaxError as exc:
        return [
            _diagnostic(
                severity="blocker",
                code="python-syntax",
                path=file.path,
                line=exc.lineno or 0,
                message="generated Python does not parse",
            )
        ]

    dynamic_calls = {
        "eval": "dynamic-eval",
        "exec": "dynamic-exec",
        "__import__": "dynamic-import",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            code = dynamic_calls.get(node.func.id)
            if code:
                result.append(
                    _diagnostic(
                        severity="warning",
                        code=code,
                        path=file.path,
                        line=getattr(node, "lineno", 0),
                        message=(
                            "candidate uses a dynamic execution primitive"
                        ),
                    )
                )
        if len(result) >= MAX_DIAGNOSTICS:
            break
    return result


def _json_checks(
    file: CandidateFile,
) -> list[ValidationDiagnostic]:
    try:
        json.loads(
            file.content,
            object_pairs_hook=_unique_json_object,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        line = (
            exc.lineno
            if isinstance(exc, json.JSONDecodeError)
            else 0
        )
        return [
            _diagnostic(
                severity="blocker",
                code="json-parse",
                path=file.path,
                line=line,
                message="generated JSON is invalid or ambiguous",
            )
        ]
    return []


def _toml_checks(
    file: CandidateFile,
) -> list[ValidationDiagnostic]:
    try:
        tomllib.loads(file.content)
    except tomllib.TOMLDecodeError:
        return [
            _diagnostic(
                severity="blocker",
                code="toml-parse",
                path=file.path,
                message="generated TOML is invalid",
            )
        ]
    return []


def _markdown_checks(
    file: CandidateFile,
) -> list[ValidationDiagnostic]:
    fence = chr(96) * 3
    count = sum(
        1
        for line in file.content.splitlines()
        if line.lstrip().startswith(fence)
    )
    if count % 2:
        return [
            _diagnostic(
                severity="warning",
                code="markdown-fence-balance",
                path=file.path,
                message="Markdown contains an unmatched fenced block",
            )
        ]
    return []


def validate_file(
    file: CandidateFile,
    *,
    budget: BuildBudget,
) -> FileValidation:
    raw = file.content.encode("utf-8")
    diagnostics = _basic_text_checks(file)
    if len(raw) > budget.max_file_bytes:
        diagnostics.append(
            _diagnostic(
                severity="blocker",
                code="file-byte-budget",
                path=file.path,
                message="candidate file exceeds configured byte budget",
            )
        )

    suffix = PurePosixPath(file.path).suffix.casefold()
    if suffix in {".py", ".pyi"}:
        diagnostics.extend(_python_checks(file))
    elif suffix == ".json":
        diagnostics.extend(_json_checks(file))
    elif suffix == ".toml":
        diagnostics.extend(_toml_checks(file))
    elif suffix in {".md", ".mdx"}:
        diagnostics.extend(_markdown_checks(file))
    elif suffix and suffix not in _TEXT_SUFFIXES:
        diagnostics.append(
            _diagnostic(
                severity="warning",
                code="unknown-text-suffix",
                path=file.path,
                message=(
                    "candidate suffix has no specialized parser; "
                    "generic text checks only"
                ),
            )
        )

    diagnostics = diagnostics[:MAX_DIAGNOSTICS]
    return FileValidation(
        path=file.path,
        digest=file.digest,
        bytes=len(raw),
        lines=len(file.content.splitlines()),
        diagnostics=tuple(diagnostics),
    )


def _coverage_diagnostics(
    *,
    architecture: ArchitecturePlan,
    files: Sequence[CandidateFile],
) -> list[ValidationDiagnostic]:
    planned = {item.path for item in architecture.files}
    candidate = {item.path for item in files}
    diagnostics: list[ValidationDiagnostic] = []

    for path in sorted(planned - candidate):
        diagnostics.append(
            _diagnostic(
                severity="blocker",
                code="planned-file-missing",
                path=path,
                message="planned implementation path is absent from candidate",
            )
        )
    for path in sorted(candidate - planned):
        diagnostics.append(
            _diagnostic(
                severity="blocker",
                code="unplanned-file",
                path=path,
                message="candidate contains a path not admitted by architecture",
            )
        )
    return diagnostics


def validate_candidate(
    files: Sequence[CandidateFile],
    *,
    architecture: ArchitecturePlan,
    budget: BuildBudget,
) -> ValidationReport:
    """Validate exact coverage, budgets, parsers, and data-level safety."""
    if not isinstance(files, Sequence):
        raise BuildValidationError("candidate files must be a sequence")

    paths = [item.path for item in files]
    if len(paths) != len(set(paths)):
        raise BuildValidationError(
            "candidate contains duplicate repository paths"
        )

    global_diagnostics = _coverage_diagnostics(
        architecture=architecture,
        files=files,
    )
    if len(files) > budget.max_files:
        global_diagnostics.append(
            _diagnostic(
                severity="blocker",
                code="file-count-budget",
                path="",
                message="candidate exceeds configured file-count budget",
            )
        )

    file_reports = tuple(
        validate_file(item, budget=budget)
        for item in sorted(files, key=lambda value: value.path)
    )
    total_bytes = sum(item.bytes for item in file_reports)
    total_lines = sum(item.lines for item in file_reports)

    if total_bytes > budget.max_total_bytes:
        global_diagnostics.append(
            _diagnostic(
                severity="blocker",
                code="total-byte-budget",
                path="",
                message="candidate exceeds configured total byte budget",
            )
        )

    return ValidationReport(
        files=file_reports,
        global_diagnostics=tuple(
            global_diagnostics[:MAX_DIAGNOSTICS]
        ),
        planned_paths=tuple(
            sorted(item.path for item in architecture.files)
        ),
        candidate_paths=tuple(sorted(paths)),
        total_bytes=total_bytes,
        total_lines=total_lines,
    )


def compact_diagnostics(
    report: ValidationReport,
    *,
    limit: int = 24,
) -> tuple[dict[str, object], ...]:
    """Return bounded machine-readable diagnostics for evidence/review."""
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
        or limit > MAX_DIAGNOSTICS
    ):
        raise ValueError("invalid diagnostic limit")
    return tuple(
        item.as_dict()
        for item in report.diagnostics[:limit]
    )
