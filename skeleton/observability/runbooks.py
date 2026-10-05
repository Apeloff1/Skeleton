"""Executable, evidence-bound operations runbook contracts for VOL-091.

Runbooks are immutable safety graphs. Observation, mutation, rollback,
degraded-mode operation, stop and escalation are explicit contracts rather than
free-form prose. Drill evidence validates only the exact runbook version/digest
that was exercised.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable

RUNBOOK_SCHEMA = "skeleton.observability.runbook.v1"
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_STEPS = 512
_MAX_SUCCESSORS = 32
_MAX_RUNBOOKS = 4096
_MAX_VALIDATIONS = 16384


class RunbookError(ValueError):
    """Runbook structure, authority, graph or validation evidence is unsafe."""


class StepKind(str, Enum):
    OBSERVE = "observe"
    COMMAND = "command"
    DECISION = "decision"
    ROLLBACK = "rollback"
    ESCALATE = "escalate"
    STOP = "stop"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise RunbookError(f"{field} must be a stable identifier")
    return value


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        raise RunbookError(f"{field} must be normalized bounded text")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise RunbookError(f"{field} must be lowercase sha256")
    return value


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RunbookError(f"{field} must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        raise RunbookError(f"{field} must use whole-second precision")
    return normalized


def _digest(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunbookError("runbook identity must be deterministic JSON") from exc
    return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class RunbookStep:
    step_id: str
    kind: StepKind
    instruction: str
    signal_ref: str | None = None
    command_ref: str | None = None
    authority_ref: str | None = None
    rollback_step_id: str | None = None
    condition_ref: str | None = None
    next_step_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _id(self.step_id, "step_id"))
        if not isinstance(self.kind, StepKind):
            raise RunbookError("kind must be StepKind")
        object.__setattr__(
            self,
            "instruction",
            _text(self.instruction, "instruction"),
        )
        for field in (
            "signal_ref",
            "command_ref",
            "authority_ref",
            "rollback_step_id",
            "condition_ref",
        ):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _id(value, field))

        if not isinstance(self.next_step_ids, tuple):
            raise RunbookError("next_step_ids must be a tuple")
        if len(self.next_step_ids) > _MAX_SUCCESSORS:
            raise RunbookError("successor set exceeds policy bound")
        successors = tuple(sorted(_id(item, "next_step_id") for item in self.next_step_ids))
        if len(successors) != len(set(successors)):
            raise RunbookError("duplicate successor identity")
        if self.step_id in successors:
            raise RunbookError("step cannot directly succeed itself")
        object.__setattr__(self, "next_step_ids", successors)

        if self.kind is StepKind.OBSERVE and self.signal_ref is None:
            raise RunbookError("observe step requires signal_ref")

        if self.kind is StepKind.COMMAND:
            if self.command_ref is None or self.authority_ref is None:
                raise RunbookError(
                    "command step requires command_ref and authority_ref"
                )
            if self.rollback_step_id is None:
                raise RunbookError(
                    "command step requires explicit rollback_step_id"
                )

        if self.kind is StepKind.ROLLBACK:
            if self.command_ref is None or self.authority_ref is None:
                raise RunbookError(
                    "rollback step requires command_ref and authority_ref"
                )
            if self.rollback_step_id is not None:
                raise RunbookError(
                    "rollback step cannot declare another rollback target"
                )

        if self.kind in (StepKind.ESCALATE, StepKind.STOP):
            if self.next_step_ids:
                raise RunbookError("terminal step cannot have successors")
            if self.condition_ref is None:
                raise RunbookError(
                    "stop/escalation step requires explicit condition_ref"
                )
        elif self.condition_ref is not None and self.kind is not StepKind.DECISION:
            raise RunbookError(
                "condition_ref is reserved for decision or terminal steps"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": RUNBOOK_SCHEMA,
                "step_id": self.step_id,
                "kind": self.kind.value,
                "instruction": self.instruction,
                "signal_ref": self.signal_ref,
                "command_ref": self.command_ref,
                "authority_ref": self.authority_ref,
                "rollback_step_id": self.rollback_step_id,
                "condition_ref": self.condition_ref,
                "next_step_ids": self.next_step_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class Runbook:
    runbook_id: str
    version: str
    owner: str
    degraded_mode: str
    entry_step_id: str
    steps: tuple[RunbookStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "runbook_id", _id(self.runbook_id, "runbook_id"))
        object.__setattr__(self, "version", _id(self.version, "version"))
        object.__setattr__(self, "owner", _id(self.owner, "owner"))
        object.__setattr__(
            self,
            "degraded_mode",
            _text(self.degraded_mode, "degraded_mode"),
        )
        object.__setattr__(
            self,
            "entry_step_id",
            _id(self.entry_step_id, "entry_step_id"),
        )
        if (
            not isinstance(self.steps, tuple)
            or not self.steps
            or len(self.steps) > _MAX_STEPS
        ):
            raise RunbookError("runbook step set is outside policy bounds")
        if any(not isinstance(step, RunbookStep) for step in self.steps):
            raise RunbookError("runbook contains invalid step")

        steps = tuple(sorted(self.steps, key=lambda item: item.step_id))
        ids = {step.step_id for step in steps}
        if len(ids) != len(steps):
            raise RunbookError("duplicate step identity")
        if self.entry_step_id not in ids:
            raise RunbookError("entry step is missing")

        by_id = {step.step_id: step for step in steps}
        adjacency: dict[str, set[str]] = {step_id: set() for step_id in ids}

        for step in steps:
            for successor in step.next_step_ids:
                if successor not in ids:
                    raise RunbookError("step references unknown successor")
                adjacency[step.step_id].add(successor)

            if step.rollback_step_id is not None:
                if step.rollback_step_id not in ids:
                    raise RunbookError("step references unknown rollback")
                rollback = by_id[step.rollback_step_id]
                if rollback.kind is not StepKind.ROLLBACK:
                    raise RunbookError("rollback target must be rollback step")
                adjacency[step.step_id].add(step.rollback_step_id)

        reachable: set[str] = set()
        stack = [self.entry_step_id]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(sorted(adjacency[current], reverse=True))
        if reachable != ids:
            raise RunbookError("runbook contains unreachable steps")

        terminals = {
            step.step_id
            for step in steps
            if step.kind in (StepKind.STOP, StepKind.ESCALATE)
        }
        if not terminals:
            raise RunbookError("runbook requires explicit stop or escalation")

        reverse: dict[str, set[str]] = {step_id: set() for step_id in ids}
        for source, targets in adjacency.items():
            for target in targets:
                reverse[target].add(source)

        can_terminate = set(terminals)
        stack = sorted(terminals)
        while stack:
            current = stack.pop()
            for predecessor in sorted(reverse[current]):
                if predecessor not in can_terminate:
                    can_terminate.add(predecessor)
                    stack.append(predecessor)
        if can_terminate != ids:
            raise RunbookError(
                "every reachable step must have a path to stop or escalation"
            )

        object.__setattr__(self, "steps", steps)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": RUNBOOK_SCHEMA,
                "runbook_id": self.runbook_id,
                "version": self.version,
                "owner": self.owner,
                "degraded_mode": self.degraded_mode,
                "entry_step_id": self.entry_step_id,
                "steps": [step.digest for step in self.steps],
            }
        )


@dataclass(frozen=True, slots=True)
class RunbookValidation:
    validation_id: str
    runbook_id: str
    runbook_version: str
    runbook_digest: str
    drill_id: str
    validator_id: str
    status: ValidationStatus
    evidence_digest: str
    observed_at: datetime
    incident_ref: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "validation_id",
            "runbook_id",
            "runbook_version",
            "drill_id",
            "validator_id",
        ):
            object.__setattr__(self, field, _id(getattr(self, field), field))
        object.__setattr__(
            self,
            "runbook_digest",
            _sha(self.runbook_digest, "runbook_digest"),
        )
        object.__setattr__(
            self,
            "evidence_digest",
            _sha(self.evidence_digest, "evidence_digest"),
        )
        if not isinstance(self.status, ValidationStatus):
            raise RunbookError("status must be ValidationStatus")
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        if self.incident_ref is not None:
            object.__setattr__(
                self,
                "incident_ref",
                _id(self.incident_ref, "incident_ref"),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": RUNBOOK_SCHEMA,
                "validation_id": self.validation_id,
                "runbook_id": self.runbook_id,
                "runbook_version": self.runbook_version,
                "runbook_digest": self.runbook_digest,
                "drill_id": self.drill_id,
                "validator_id": self.validator_id,
                "status": self.status.value,
                "evidence_digest": self.evidence_digest,
                "observed_at": self.observed_at.isoformat(),
                "incident_ref": self.incident_ref,
            }
        )


class RunbookRegistry:
    """Bounded immutable-version registry with exact drill-evidence binding."""

    def __init__(self) -> None:
        self._books: dict[tuple[str, str], Runbook] = {}
        self._validations: dict[str, RunbookValidation] = {}

    def register(self, book: Runbook) -> Runbook:
        if not isinstance(book, Runbook):
            raise TypeError("book must be Runbook")
        key = (book.runbook_id, book.version)
        prior = self._books.get(key)
        if prior is not None:
            if prior == book:
                return prior
            raise RunbookError("runbook version is immutable")
        if len(self._books) >= _MAX_RUNBOOKS:
            raise RunbookError("runbook registry capacity reached")
        self._books[key] = book
        return book

    def record_validation(self, item: RunbookValidation) -> RunbookValidation:
        if not isinstance(item, RunbookValidation):
            raise TypeError("item must be RunbookValidation")
        book = self._books.get((item.runbook_id, item.runbook_version))
        if book is None or book.digest != item.runbook_digest:
            raise RunbookError(
                "validation is not bound to a registered exact runbook version"
            )

        prior = self._validations.get(item.validation_id)
        if prior is not None:
            if prior == item:
                return prior
            raise RunbookError("validation identity is immutable")

        if any(
            validation.drill_id == item.drill_id
            and validation.runbook_id == item.runbook_id
            and validation.runbook_version == item.runbook_version
            and validation.runbook_digest == item.runbook_digest
            for validation in self._validations.values()
        ):
            raise RunbookError(
                "drill identity already has a receipt for exact runbook version"
            )

        if len(self._validations) >= _MAX_VALIDATIONS:
            raise RunbookError("runbook validation capacity reached")
        self._validations[item.validation_id] = item
        return item

    def validated(self, runbook_id: str, version: str) -> bool:
        runbook_id = _id(runbook_id, "runbook_id")
        version = _id(version, "version")
        book = self._books.get((runbook_id, version))
        if book is None:
            raise RunbookError("unknown runbook version")
        matching = tuple(
            item
            for item in self._validations.values()
            if item.runbook_id == runbook_id
            and item.runbook_version == version
            and item.runbook_digest == book.digest
        )
        if not matching:
            return False
        latest_at = max(item.observed_at for item in matching)
        latest = tuple(item for item in matching if item.observed_at == latest_at)
        return all(item.status is ValidationStatus.PASSED for item in latest)

    def validations_for(
        self,
        runbook_id: str,
        version: str,
    ) -> tuple[RunbookValidation, ...]:
        runbook_id = _id(runbook_id, "runbook_id")
        version = _id(version, "version")
        return tuple(
            sorted(
                (
                    item
                    for item in self._validations.values()
                    if item.runbook_id == runbook_id
                    and item.runbook_version == version
                ),
                key=lambda item: (item.observed_at, item.validation_id),
            )
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": RUNBOOK_SCHEMA,
                "runbooks": [
                    self._books[key].digest
                    for key in sorted(self._books)
                ],
                "validations": [
                    self._validations[key].digest
                    for key in sorted(self._validations)
                ],
            }
        )


__all__ = [
    "RUNBOOK_SCHEMA",
    "Runbook",
    "RunbookError",
    "RunbookRegistry",
    "RunbookStep",
    "RunbookValidation",
    "StepKind",
    "ValidationStatus",
]
