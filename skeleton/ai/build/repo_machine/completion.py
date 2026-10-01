"""Evidence-derived completion with non-compensable blockers and invalidation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


class CompletionPolicyError(RuntimeError):
    pass


STATES = (
    "not_started",
    "in_progress",
    "blocked",
    "evidence_pending",
    "verified_complete",
)


def _ref(value: str, field: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 2048:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _path(value: str) -> str:
    text = _ref(value, "path")
    if "\x00" in text or "\\" in text:
        raise ValueError("path must be canonical POSIX text")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("path must be repository-relative")
    if pure.as_posix() != text:
        raise ValueError("path must be canonical POSIX text")
    return text


@dataclass(frozen=True, slots=True)
class AtomicCompletion:
    implementation_signed: bool = False
    verification_signed: bool = False
    required_gates: tuple[bool, ...] = ()
    hard_dependencies_closed: bool = False
    evidence_refs: tuple[str, ...] = ()
    evidence_identity_valid: bool = False

    def __post_init__(self) -> None:
        for field in (
            "implementation_signed",
            "verification_signed",
            "hard_dependencies_closed",
            "evidence_identity_valid",
        ):
            if not isinstance(getattr(self, field), bool):
                raise TypeError(f"{field} must be boolean")
        if any(not isinstance(item, bool) for item in self.required_gates):
            raise TypeError("required_gates must be booleans")
        refs = tuple(_ref(item, "evidence_ref") for item in self.evidence_refs)
        if len(refs) != len(set(refs)):
            raise ValueError("evidence_refs must be unique")
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True, slots=True)
class CompletionResult:
    state: str
    blockers: tuple[str, ...]


def derive_atomic(completion: AtomicCompletion) -> CompletionResult:
    blockers: list[str] = []
    if not completion.hard_dependencies_closed:
        blockers.append("unresolved hard dependency")
    if completion.required_gates and not all(completion.required_gates):
        blockers.append("failed/missing required gate")
    if completion.evidence_refs and not completion.evidence_identity_valid:
        blockers.append("invalidated evidence identity")

    if blockers:
        return CompletionResult("blocked", tuple(blockers))

    if (
        completion.implementation_signed
        and completion.verification_signed
        and completion.hard_dependencies_closed
        and completion.required_gates
        and all(completion.required_gates)
        and completion.evidence_refs
        and completion.evidence_identity_valid
    ):
        return CompletionResult("verified_complete", ())

    if completion.implementation_signed or completion.evidence_refs:
        return CompletionResult("evidence_pending", ())
    if completion.verification_signed:
        return CompletionResult("evidence_pending", ())
    return CompletionResult("not_started", ())


def rollup(states: Iterable[str]) -> str:
    values = tuple(states)
    if not values:
        raise CompletionPolicyError("rollup requires at least one child")
    if any(value not in STATES for value in values):
        raise CompletionPolicyError("unknown child completion state")
    if all(value == "verified_complete" for value in values):
        return "verified_complete"
    if "blocked" in values:
        return "blocked"
    if "evidence_pending" in values:
        return "evidence_pending"
    if "in_progress" in values:
        return "in_progress"
    if "verified_complete" in values:
        return "in_progress"
    return "not_started"


def invalidated_by_change(
    changed_paths: Iterable[str],
    watched_paths: Iterable[str],
) -> tuple[str, ...]:
    changed = tuple(sorted({_path(item) for item in changed_paths}))
    watched = tuple(sorted({_path(item) for item in watched_paths}))
    invalidated: list[str] = []
    for path in changed:
        if any(path == watch or path.startswith(watch.rstrip("/") + "/") for watch in watched):
            invalidated.append(path)
    return tuple(invalidated)


__all__ = [
    "AtomicCompletion",
    "CompletionPolicyError",
    "CompletionResult",
    "STATES",
    "derive_atomic",
    "invalidated_by_change",
    "rollup",
]
