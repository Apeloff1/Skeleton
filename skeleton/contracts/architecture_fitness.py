"""Canonical executable architecture-fitness contracts for VOL-116.

Architecture fitness rules turn architecture decisions into deterministic,
bounded repository checks. Violations are exact evidence objects. Waivers never
disable a rule globally: they bind one exact violation digest, one rule revision,
one path, an owner, an independent approver, and a finite validity window.

This module owns policy. :mod:`skeleton.automation.architecture_fitness` is a
compatibility-only surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatchcase
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping

FITNESS_SCHEMA = "skeleton.contracts.architecture_fitness.v1"
_MAX_RULES = 10_000
_MAX_WAIVERS = 50_000
_MAX_FILES = 100_000
_MAX_TEXT_BYTES = 5_000_000
_MAX_PATTERN = 1_024
_MAX_GLOBS = 128
_MAX_MATCHES_PER_FILE = 10_000
_MAX_REASON = 2_048
_MAX_TICK = 2_147_483_647

_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FitnessError(ValueError):
    """Architecture-fitness state is malformed, ambiguous, or unsafe."""


class FitnessSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class FitnessStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


def _stable_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FitnessError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise FitnessError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FitnessError(f"{field} must be integer")
    if not 1 <= value <= maximum:
        raise FitnessError(f"{field} must be within [1, {maximum}]")
    return value


def _nonnegative_int(value: object, field: str, maximum: int = _MAX_TICK) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FitnessError(f"{field} must be integer")
    if not 0 <= value <= maximum:
        raise FitnessError(f"{field} must be within [0, {maximum}]")
    return value


def _canonical_text(
    value: object,
    field: str,
    *,
    maximum: int = _MAX_REASON,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise FitnessError(f"{field} must be bounded canonical text")
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise FitnessError(f"{field} contains control characters")
    return value


def _path(value: object, field: str = "path") -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or value.startswith("/")
        or len(value) > 1_024
    ):
        raise FitnessError(f"{field} must be canonical repository-relative path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise FitnessError(f"{field} must be canonical repository-relative path")
    if any(ord(char) < 32 for char in value):
        raise FitnessError(f"{field} contains control characters")
    return value


def _glob(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or value.startswith("/")
        or len(value) > 512
    ):
        raise FitnessError(f"{field} must be canonical relative glob")
    if ".." in value.split("/"):
        raise FitnessError(f"{field} cannot traverse parents")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FitnessError("fitness state must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


def _content_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FitnessFunction:
    """One executable architecture decision constraint."""

    rule_id: str
    decision_ref: str
    pattern: str
    severity: FitnessSeverity = FitnessSeverity.ERROR
    include_paths: tuple[str, ...] = ("*",)
    exclude_paths: tuple[str, ...] = ()
    max_matches_per_file: int = 1_000

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _stable_id(self.rule_id, "rule_id"))
        object.__setattr__(
            self,
            "decision_ref",
            _stable_id(self.decision_ref, "decision_ref"),
        )
        if (
            not isinstance(self.pattern, str)
            or not self.pattern
            or len(self.pattern) > _MAX_PATTERN
            or "\x00" in self.pattern
        ):
            raise FitnessError("rule pattern must be bounded non-empty regex")
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise FitnessError("invalid rule pattern") from exc
        if not isinstance(self.severity, FitnessSeverity):
            raise FitnessError("severity must be FitnessSeverity")
        if (
            not isinstance(self.include_paths, tuple)
            or not self.include_paths
            or len(self.include_paths) > _MAX_GLOBS
        ):
            raise FitnessError("include_paths must be bounded non-empty tuple")
        if (
            not isinstance(self.exclude_paths, tuple)
            or len(self.exclude_paths) > _MAX_GLOBS
        ):
            raise FitnessError("exclude_paths must be bounded tuple")
        includes = tuple(
            _glob(item, "include_path") for item in self.include_paths
        )
        excludes = tuple(
            _glob(item, "exclude_path") for item in self.exclude_paths
        )
        if len(includes) != len(set(includes)):
            raise FitnessError("duplicate include path glob")
        if len(excludes) != len(set(excludes)):
            raise FitnessError("duplicate exclude path glob")
        object.__setattr__(self, "include_paths", tuple(sorted(includes)))
        object.__setattr__(self, "exclude_paths", tuple(sorted(excludes)))
        object.__setattr__(
            self,
            "max_matches_per_file",
            _positive_int(
                self.max_matches_per_file,
                "max_matches_per_file",
                _MAX_MATCHES_PER_FILE,
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                FITNESS_SCHEMA,
                self.rule_id,
                self.decision_ref,
                self.pattern,
                self.severity.value,
                list(self.include_paths),
                list(self.exclude_paths),
                self.max_matches_per_file,
            ]
        )

    def applies_to(self, path: str) -> bool:
        path = _path(path)
        included = any(
            fnmatchcase(path, glob) for glob in self.include_paths
        )
        excluded = any(
            fnmatchcase(path, glob) for glob in self.exclude_paths
        )
        return included and not excluded


@dataclass(frozen=True, slots=True)
class FitnessViolation:
    """Exact violation produced by one exact rule revision."""

    rule_id: str
    path: str
    line: int
    column: int = 1
    rule_digest: str | None = None
    decision_ref: str | None = None
    content_digest: str | None = None
    match_digest: str | None = None
    severity: FitnessSeverity = FitnessSeverity.ERROR

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _stable_id(self.rule_id, "rule_id"))
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(
            self,
            "line",
            _positive_int(self.line, "line", _MAX_TICK),
        )
        object.__setattr__(
            self,
            "column",
            _positive_int(self.column, "column", _MAX_TICK),
        )
        if self.rule_digest is not None:
            object.__setattr__(
                self,
                "rule_digest",
                _sha(self.rule_digest, "rule_digest"),
            )
        if self.decision_ref is not None:
            object.__setattr__(
                self,
                "decision_ref",
                _stable_id(self.decision_ref, "decision_ref"),
            )
        if self.content_digest is not None:
            object.__setattr__(
                self,
                "content_digest",
                _sha(self.content_digest, "content_digest"),
            )
        if self.match_digest is not None:
            object.__setattr__(
                self,
                "match_digest",
                _sha(self.match_digest, "match_digest"),
            )
        if not isinstance(self.severity, FitnessSeverity):
            raise FitnessError("severity must be FitnessSeverity")

    @property
    def exact(self) -> bool:
        return all(
            item is not None
            for item in (
                self.rule_digest,
                self.decision_ref,
                self.content_digest,
                self.match_digest,
            )
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                FITNESS_SCHEMA,
                self.rule_id,
                self.path,
                self.line,
                self.column,
                self.rule_digest,
                self.decision_ref,
                self.content_digest,
                self.match_digest,
                self.severity.value,
            ]
        )


@dataclass(frozen=True, slots=True)
class FitnessWaiver:
    """Narrow, expiring waiver for one exact violation."""

    rule_id: str
    path: str
    owner_id: str
    reason: str
    expires_tick: int
    violation_digest: str | None = None
    rule_digest: str | None = None
    approver_id: str | None = None
    issued_tick: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _stable_id(self.rule_id, "rule_id"))
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(self, "owner_id", _stable_id(self.owner_id, "owner_id"))
        object.__setattr__(self, "reason", _canonical_text(self.reason, "reason"))
        object.__setattr__(
            self,
            "expires_tick",
            _positive_int(self.expires_tick, "expires_tick", _MAX_TICK),
        )
        object.__setattr__(
            self,
            "issued_tick",
            _nonnegative_int(self.issued_tick, "issued_tick"),
        )
        if self.issued_tick > self.expires_tick:
            raise FitnessError("waiver issued_tick cannot exceed expires_tick")
        if self.violation_digest is not None:
            object.__setattr__(
                self,
                "violation_digest",
                _sha(self.violation_digest, "violation_digest"),
            )
        if self.rule_digest is not None:
            object.__setattr__(
                self,
                "rule_digest",
                _sha(self.rule_digest, "rule_digest"),
            )
        if self.approver_id is not None:
            object.__setattr__(
                self,
                "approver_id",
                _stable_id(self.approver_id, "approver_id"),
            )

    @property
    def exact(self) -> bool:
        return (
            self.violation_digest is not None
            and self.rule_digest is not None
            and self.approver_id is not None
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                FITNESS_SCHEMA,
                self.rule_id,
                self.path,
                self.owner_id,
                self.reason,
                self.issued_tick,
                self.expires_tick,
                self.violation_digest,
                self.rule_digest,
                self.approver_id,
            ]
        )


@dataclass(frozen=True, slots=True)
class FitnessWaiverEvaluation:
    waiver_digest: str
    accepted: bool
    reason: str

    @property
    def digest(self) -> str:
        return _digest(
            [
                FITNESS_SCHEMA,
                self.waiver_digest,
                self.accepted,
                self.reason,
            ]
        )


@dataclass(frozen=True, slots=True)
class FitnessFileResult:
    path: str
    content_digest: str
    violations: tuple[FitnessViolation, ...]
    waived_violation_digests: tuple[str, ...]
    unresolved_violation_digests: tuple[str, ...]
    waiver_evaluations: tuple[FitnessWaiverEvaluation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(
            self,
            "content_digest",
            _sha(self.content_digest, "content_digest"),
        )

    @property
    def status(self) -> FitnessStatus:
        unresolved = {
            item.digest: item for item in self.violations
            if item.digest in self.unresolved_violation_digests
        }
        if any(
            item.severity in (FitnessSeverity.ERROR, FitnessSeverity.BLOCKER)
            for item in unresolved.values()
        ):
            return FitnessStatus.FAIL
        if unresolved:
            return FitnessStatus.WARN
        return FitnessStatus.PASS

    @property
    def digest(self) -> str:
        return _digest(
            [
                FITNESS_SCHEMA,
                self.path,
                self.content_digest,
                [item.digest for item in self.violations],
                list(self.waived_violation_digests),
                list(self.unresolved_violation_digests),
                [item.digest for item in self.waiver_evaluations],
                self.status.value,
            ]
        )


@dataclass(frozen=True, slots=True)
class FitnessRepositoryReport:
    registry_digest: str
    tick: int
    file_results: tuple[FitnessFileResult, ...]

    @property
    def status(self) -> FitnessStatus:
        statuses = {item.status for item in self.file_results}
        if FitnessStatus.FAIL in statuses:
            return FitnessStatus.FAIL
        if FitnessStatus.WARN in statuses:
            return FitnessStatus.WARN
        return FitnessStatus.PASS

    @property
    def unresolved_count(self) -> int:
        return sum(
            len(item.unresolved_violation_digests)
            for item in self.file_results
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                FITNESS_SCHEMA,
                self.registry_digest,
                self.tick,
                [item.digest for item in self.file_results],
                self.status.value,
            ]
        )


class FitnessRegistry:
    """Bounded deterministic architecture-fitness evaluator."""

    def __init__(self, rules: Iterable[FitnessFunction]) -> None:
        materialized = tuple(rules)
        if len(materialized) > _MAX_RULES:
            raise FitnessError("fitness rule count exceeds safety bound")
        if any(not isinstance(rule, FitnessFunction) for rule in materialized):
            raise TypeError("rules must contain FitnessFunction")
        ids = [rule.rule_id for rule in materialized]
        if len(ids) != len(set(ids)):
            raise FitnessError("duplicate fitness rule id")
        self.rules = tuple(sorted(materialized, key=lambda item: item.rule_id))
        self._compiled = {
            rule.rule_id: re.compile(rule.pattern) for rule in self.rules
        }

    @property
    def digest(self) -> str:
        return _digest(
            [FITNESS_SCHEMA, [rule.digest for rule in self.rules]]
        )

    def rule(self, rule_id: str) -> FitnessFunction:
        rule_id = _stable_id(rule_id, "rule_id")
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        raise FitnessError("unknown fitness rule")

    def evaluate(self, path: str, text: str) -> tuple[FitnessViolation, ...]:
        path = _path(path)
        if not isinstance(text, str):
            raise TypeError("text must be str")
        encoded = text.encode("utf-8")
        if len(encoded) > _MAX_TEXT_BYTES:
            raise FitnessError("file exceeds fitness scan size bound")

        content_digest = sha256(encoded).hexdigest()
        out: list[FitnessViolation] = []
        lines = text.splitlines()

        for rule in self.rules:
            if not rule.applies_to(path):
                continue
            regex = self._compiled[rule.rule_id]
            matches = 0
            for line_number, line in enumerate(lines, 1):
                for match in regex.finditer(line):
                    matches += 1
                    if matches > rule.max_matches_per_file:
                        raise FitnessError(
                            "rule match count exceeds per-file safety bound"
                        )
                    matched = match.group(0)
                    match_digest = _digest(
                        [
                            rule.digest,
                            path,
                            line_number,
                            match.start() + 1,
                            matched,
                        ]
                    )
                    out.append(
                        FitnessViolation(
                            rule_id=rule.rule_id,
                            path=path,
                            line=line_number,
                            column=match.start() + 1,
                            rule_digest=rule.digest,
                            decision_ref=rule.decision_ref,
                            content_digest=content_digest,
                            match_digest=match_digest,
                            severity=rule.severity,
                        )
                    )

        return tuple(
            sorted(
                out,
                key=lambda item: (
                    item.path,
                    item.line,
                    item.column,
                    item.rule_id,
                    item.match_digest or "",
                ),
            )
        )

    def _waiver_evaluation(
        self,
        violation: FitnessViolation,
        waiver: FitnessWaiver,
        *,
        tick: int,
    ) -> FitnessWaiverEvaluation:
        if not waiver.exact:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "waiver_not_exact",
            )
        if not violation.exact:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "violation_not_exact",
            )
        rule = self.rule(violation.rule_id)
        if waiver.rule_id != violation.rule_id:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "rule_id_mismatch",
            )
        if waiver.path != violation.path:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "path_mismatch",
            )
        if waiver.rule_digest != rule.digest:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "rule_revision_mismatch",
            )
        if waiver.violation_digest != violation.digest:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "violation_digest_mismatch",
            )
        if waiver.issued_tick > tick:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "waiver_from_future",
            )
        if waiver.expires_tick < tick:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "waiver_expired",
            )
        if waiver.approver_id == waiver.owner_id:
            return FitnessWaiverEvaluation(
                waiver.digest,
                False,
                "waiver_not_independently_approved",
            )
        return FitnessWaiverEvaluation(
            waiver.digest,
            True,
            "exact_active_waiver",
        )

    def unresolved(
        self,
        violations: Iterable[FitnessViolation],
        waivers: Iterable[FitnessWaiver],
        tick: int,
    ) -> tuple[FitnessViolation, ...]:
        tick = _nonnegative_int(tick, "tick")
        materialized_violations = tuple(violations)
        materialized_waivers = tuple(waivers)
        if any(
            not isinstance(item, FitnessViolation)
            for item in materialized_violations
        ):
            raise TypeError("violations must contain FitnessViolation")
        if any(
            not isinstance(item, FitnessWaiver)
            for item in materialized_waivers
        ):
            raise TypeError("waivers must contain FitnessWaiver")
        if len(materialized_waivers) > _MAX_WAIVERS:
            raise FitnessError("waiver count exceeds safety bound")

        unresolved: list[FitnessViolation] = []
        for violation in materialized_violations:
            accepted = any(
                self._waiver_evaluation(violation, waiver, tick=tick).accepted
                for waiver in materialized_waivers
            )
            if not accepted:
                unresolved.append(violation)
        return tuple(unresolved)

    def evaluate_file(
        self,
        path: str,
        text: str,
        *,
        waivers: Iterable[FitnessWaiver] = (),
        tick: int = 0,
    ) -> FitnessFileResult:
        tick = _nonnegative_int(tick, "tick")
        violations = self.evaluate(path, text)
        materialized_waivers = tuple(waivers)
        if len(materialized_waivers) > _MAX_WAIVERS:
            raise FitnessError("waiver count exceeds safety bound")
        if any(
            not isinstance(item, FitnessWaiver)
            for item in materialized_waivers
        ):
            raise TypeError("waivers must contain FitnessWaiver")

        evaluations: list[FitnessWaiverEvaluation] = []
        waived: set[str] = set()
        for violation in violations:
            for waiver in materialized_waivers:
                evaluation = self._waiver_evaluation(
                    violation,
                    waiver,
                    tick=tick,
                )
                evaluations.append(evaluation)
                if evaluation.accepted:
                    waived.add(violation.digest)

        unresolved = tuple(
            violation.digest
            for violation in violations
            if violation.digest not in waived
        )
        return FitnessFileResult(
            path=_path(path),
            content_digest=_content_digest(text),
            violations=violations,
            waived_violation_digests=tuple(sorted(waived)),
            unresolved_violation_digests=tuple(sorted(unresolved)),
            waiver_evaluations=tuple(
                sorted(
                    evaluations,
                    key=lambda item: (item.waiver_digest, item.reason),
                )
            ),
        )

    def evaluate_repository(
        self,
        files: Mapping[str, str],
        *,
        waivers: Iterable[FitnessWaiver] = (),
        tick: int = 0,
    ) -> FitnessRepositoryReport:
        tick = _nonnegative_int(tick, "tick")
        if not isinstance(files, Mapping):
            raise TypeError("files must be mapping")
        if len(files) > _MAX_FILES:
            raise FitnessError("repository file count exceeds safety bound")
        materialized_waivers = tuple(waivers)
        if len(materialized_waivers) > _MAX_WAIVERS:
            raise FitnessError("waiver count exceeds safety bound")
        if any(
            not isinstance(item, FitnessWaiver)
            for item in materialized_waivers
        ):
            raise TypeError("waivers must contain FitnessWaiver")

        normalized: list[tuple[str, str]] = []
        for path, text in files.items():
            path = _path(path)
            if not isinstance(text, str):
                raise TypeError("repository file contents must be str")
            normalized.append((path, text))

        paths = [path for path, _ in normalized]
        if len(paths) != len(set(paths)):
            raise FitnessError("duplicate normalized repository path")

        results = tuple(
            self.evaluate_file(
                path,
                text,
                waivers=materialized_waivers,
                tick=tick,
            )
            for path, text in sorted(normalized)
        )
        return FitnessRepositoryReport(
            registry_digest=self.digest,
            tick=tick,
            file_results=results,
        )


__all__ = [
    "FITNESS_SCHEMA",
    "FitnessError",
    "FitnessFileResult",
    "FitnessFunction",
    "FitnessRegistry",
    "FitnessRepositoryReport",
    "FitnessSeverity",
    "FitnessStatus",
    "FitnessViolation",
    "FitnessWaiver",
    "FitnessWaiverEvaluation",
]
