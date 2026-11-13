"""Post-deploy smoke-suite definitions and result evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from skeleton.build.delivery._util import DeliveryError, require_id

METHODS = frozenset({"GET", "HEAD", "OPTIONS"})  # smoke tests must be read-only


@dataclass(frozen=True)
class SmokeCase:
    case_id: str
    method: str
    path: str
    expect_status: int = 200
    expect_json_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_id(self.case_id, field="case_id")
        if self.method not in METHODS:
            raise DeliveryError(f"smoke case {self.case_id} must use a read-only method")
        if not self.path.startswith("/"):
            raise DeliveryError("smoke path must start with /")


@dataclass(frozen=True)
class SmokeOutcome:
    case_id: str
    status: int
    json_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmokeReport:
    passed: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]

    @property
    def ok(self) -> bool:
        return not self.failed


def load_suite(items: Sequence[Mapping]) -> tuple[SmokeCase, ...]:
    cases = tuple(
        SmokeCase(
            i["id"], i.get("method", "GET"), i["path"],
            int(i.get("expect_status", 200)), tuple(i.get("expect_json_keys", ())),
        )
        for i in items
    )
    ids = [c.case_id for c in cases]
    if len(ids) != len(set(ids)):
        raise DeliveryError("duplicate smoke case ids")
    return cases


def evaluate(cases: Sequence[SmokeCase], outcomes: Iterable[SmokeOutcome]) -> SmokeReport:
    by_id = {o.case_id: o for o in outcomes}
    passed: list[str] = []
    failed: list[tuple[str, str]] = []
    for case in cases:
        outcome = by_id.get(case.case_id)
        if outcome is None:
            failed.append((case.case_id, "not-run"))
        elif outcome.status != case.expect_status:
            failed.append((case.case_id, f"status:{outcome.status}"))
        elif not set(case.expect_json_keys) <= set(outcome.json_keys):
            missing = sorted(set(case.expect_json_keys) - set(outcome.json_keys))
            failed.append((case.case_id, "missing-keys:" + ",".join(missing)))
        else:
            passed.append(case.case_id)
    return SmokeReport(tuple(passed), tuple(failed))
