"""Failure classification for retry, reporting, and operator diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.runner import ShellResult


class FailureKind(str, Enum):
    NONE = "none"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    EXIT_CODE = "exit_code"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureClassification:
    kind: FailureKind
    retryable_hint: bool
    returncode: int | None
    detail: str

    @property
    def failed(self) -> bool:
        return self.kind is not FailureKind.NONE

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "retryable_hint": self.retryable_hint,
            "returncode": self.returncode,
            "detail": self.detail,
        }


def classify_result(
    result: ShellResult,
    *,
    transient_returncodes: frozenset[int] = frozenset({69, 70, 71, 72, 73, 74, 75}),
) -> FailureClassification:
    if result.ok:
        return FailureClassification(FailureKind.NONE, False, result.returncode, "execution succeeded")
    if result.timed_out:
        return FailureClassification(FailureKind.TIMEOUT, True, result.returncode, "execution exceeded its time budget")
    if result.output_limited:
        return FailureClassification(
            FailureKind.OUTPUT_LIMIT,
            False,
            result.returncode,
            "execution exceeded its output budget",
        )
    if result.returncode is None:
        return FailureClassification(FailureKind.UNKNOWN, False, None, "execution ended without a return code")
    if result.returncode < 0:
        return FailureClassification(
            FailureKind.TERMINATED,
            False,
            result.returncode,
            "execution was terminated by a signal or host mechanism",
        )
    return FailureClassification(
        FailureKind.EXIT_CODE,
        result.returncode in transient_returncodes,
        result.returncode,
        "execution returned a non-accepted exit code",
    )
