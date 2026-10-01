"""Fail-closed repository maintenance and deletion decisions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


class MaintenancePolicyError(RuntimeError):
    pass


_NON_WAIVABLE_PROTECTED_PATHS = (
    ".github/workflows",
    "docs/adr",
    "machine",
)


def _text(value: str, field: str, *, max_len: int = 2048) -> str:
    text = str(value).strip()
    if not text or len(text) > max_len:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _path(value: str) -> str:
    text = _text(value, "path")
    if "\x00" in text or "\\" in text:
        raise ValueError("path must be canonical POSIX text")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("path must be repository-relative and traversal-free")
    if pure.as_posix() != text:
        raise ValueError("path is not canonical POSIX text")
    return text


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


@dataclass(frozen=True, slots=True)
class DeletionAssessment:
    path: str
    owner_resolved: bool
    trace_reachable: bool
    retention_hold: bool
    migration_safe: bool
    regeneration_authority: str
    rollback_ref: str
    owner_evidence_ref: str
    trace_evidence_ref: str
    retention_evidence_ref: str
    migration_evidence_ref: str
    protected_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(
            self,
            "regeneration_authority",
            _text(self.regeneration_authority, "regeneration_authority", max_len=512),
        )
        object.__setattr__(self, "rollback_ref", _text(self.rollback_ref, "rollback_ref"))
        for field in (
            "owner_evidence_ref",
            "trace_evidence_ref",
            "retention_evidence_ref",
            "migration_evidence_ref",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field, max_len=2048),
            )
        protected = tuple(
            sorted(
                {
                    *(_path(item) for item in self.protected_paths),
                    *_NON_WAIVABLE_PROTECTED_PATHS,
                }
            )
        )
        object.__setattr__(self, "protected_paths", protected)
        for field in (
            "owner_resolved",
            "trace_reachable",
            "retention_hold",
            "migration_safe",
        ):
            if not isinstance(getattr(self, field), bool):
                raise TypeError(f"{field} must be boolean")


@dataclass(frozen=True, slots=True)
class MaintenanceDecision:
    path: str
    allowed: bool
    blockers: tuple[str, ...]
    checks: tuple[str, ...]
    evidence_refs: tuple[str, ...]


_REQUIRED_CHECKS = (
    "canonical owner resolved",
    "trace reachability checked",
    "retention/evidence hold clear",
    "migration/cutover safe",
    "regeneration authority known",
    "rollback/recovery recorded",
)


def evaluate_deletion(assessment: DeletionAssessment) -> MaintenanceDecision:
    blockers: list[str] = []
    if any(_under(assessment.path, prefix) for prefix in assessment.protected_paths):
        blockers.append("protected path")
    if not assessment.owner_resolved:
        blockers.append("canonical owner unresolved")
    if assessment.trace_reachable:
        blockers.append("live trace reachability")
    if assessment.retention_hold:
        blockers.append("retention/evidence hold")
    if not assessment.migration_safe:
        blockers.append("migration/cutover unsafe")
    # Constructor validation makes regeneration authority and rollback mandatory.
    return MaintenanceDecision(
        path=assessment.path,
        allowed=not blockers,
        blockers=tuple(blockers),
        checks=_REQUIRED_CHECKS,
        evidence_refs=(
            assessment.owner_evidence_ref,
            assessment.trace_evidence_ref,
            assessment.retention_evidence_ref,
            assessment.migration_evidence_ref,
            assessment.rollback_ref,
        ),
    )


def evaluate_batch(
    assessments: Iterable[DeletionAssessment],
) -> tuple[MaintenanceDecision, ...]:
    decisions = tuple(evaluate_deletion(item) for item in assessments)
    if len({item.path for item in decisions}) != len(decisions):
        raise MaintenancePolicyError("duplicate deletion candidate")
    ordered = tuple(sorted(decisions, key=lambda item: item.path))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if _under(left.path, right.path) or _under(right.path, left.path):
                raise MaintenancePolicyError(
                    f"overlapping deletion candidates: {left.path} and {right.path}"
                )
    return ordered


__all__ = [
    "DeletionAssessment",
    "MaintenanceDecision",
    "MaintenancePolicyError",
    "evaluate_batch",
    "evaluate_deletion",
]
