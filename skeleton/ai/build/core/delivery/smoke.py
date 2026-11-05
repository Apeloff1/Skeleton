"""Post-deploy smoke-suite definitions and result evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from skeleton.build.delivery._util import DeliveryError, require_id

METHODS = frozenset({"GET", "HEAD", "OPTIONS"})  # smoke tests must be read-only
MAX_SMOKE_CASES = 256
MAX_SMOKE_OUTCOMES = 1024
MAX_SMOKE_JSON_KEYS = 128


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
        if (type(self.path) is not str or not self.path.startswith("/")
                or self.path.startswith("//") or len(self.path) > 256
                or any(ch in self.path for ch in ("\\", "?", "#"))
                or ".." in self.path.split("/")
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in self.path)):
            raise DeliveryError("unsafe smoke path")
        if type(self.expect_status) is not int or not 100 <= self.expect_status <= 599:
            raise DeliveryError("smoke expected status must be a valid HTTP integer")
        if (not isinstance(self.expect_json_keys, tuple)
                or len(self.expect_json_keys) > MAX_SMOKE_JSON_KEYS
                or any(type(k) is not str or not 1 <= len(k) <= 128
                       or any(ord(ch) < 32 or ord(ch) == 127 for ch in k)
                       for k in self.expect_json_keys)):
            raise DeliveryError("smoke expected JSON keys invalid")


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
    if not isinstance(items, Sequence) or len(items) > MAX_SMOKE_CASES:
        raise DeliveryError("smoke suite count exceeds bound")
    cases: list[SmokeCase] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise DeliveryError("smoke case must be an object")
        keys = item.get("expect_json_keys", ())
        if not isinstance(keys, (tuple, list)) or len(keys) > MAX_SMOKE_JSON_KEYS:
            raise DeliveryError("smoke expected JSON keys invalid")
        cases.append(SmokeCase(
            item["id"], item.get("method", "GET"), item["path"],
            item.get("expect_status", 200), tuple(keys),
        ))
    ids = [c.case_id for c in cases]
    if len(ids) != len(set(ids)):
        raise DeliveryError("duplicate smoke case ids")
    return tuple(cases)


def evaluate(cases: Sequence[SmokeCase], outcomes: Iterable[SmokeOutcome]) -> SmokeReport:
    if not cases or len(cases) > MAX_SMOKE_CASES:
        raise DeliveryError("smoke case count must be bounded and nonzero")
    if any(type(case) is not SmokeCase for case in cases):
        raise DeliveryError("invalid smoke case definition")
    ids = [case.case_id for case in cases]
    if len(set(ids)) != len(ids):
        raise DeliveryError("duplicate smoke case ids")
    by_id: dict[str, SmokeOutcome] = {}
    for count, outcome in enumerate(outcomes, 1):
        if count > MAX_SMOKE_OUTCOMES:
            raise DeliveryError("smoke outcome count exceeds bound")
        if not isinstance(outcome, SmokeOutcome) or outcome.case_id not in ids:
            raise DeliveryError("unknown or malformed smoke outcome")
        if outcome.case_id in by_id:
            raise DeliveryError("duplicate smoke outcome identity")
        if (type(outcome.status) is not int or not 100 <= outcome.status <= 599
                or not isinstance(outcome.json_keys, tuple)
                or len(outcome.json_keys) > MAX_SMOKE_JSON_KEYS
                or any(type(k) is not str or not 1 <= len(k) <= 128
                       or any(ord(ch) < 32 or ord(ch) == 127 for ch in k)
                       for k in outcome.json_keys)):
            raise DeliveryError("invalid smoke outcome evidence")
        by_id[outcome.case_id] = outcome
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
