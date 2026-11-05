"""Discover and execute every versioned adversarial capacity/control fixture.

A fixture is accepted only when its declared result matches a live gate result.
The suite fails closed on missing, duplicated, malformed and unknown domains.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Iterator

from .contracts import parse_json
from .policy_oracle import evaluate

DOMAINS = (
    "identity", "quota", "model_pin", "evidence", "grant", "pressure",
    "stream", "transport", "nonce", "queue", "effects", "context",
    "envelope", "memory", "tokens", "workspace",
)
EXPECTED_PER_DOMAIN = 24
TOTAL_SCENARIOS = len(DOMAINS) * EXPECTED_PER_DOMAIN


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    control: str
    expected_allow: bool
    actual_allow: bool
    actual_code: str

    @property
    def passed(self) -> bool:
        return self.expected_allow is self.actual_allow


def iter_scenarios() -> Iterator[dict]:
    base = resources.files(__package__) / "scenarios"
    seen = set()
    counts = {domain: 0 for domain in DOMAINS}
    for domain in DOMAINS:
        directory = base / domain
        for item in sorted(directory.iterdir(), key=lambda item: item.name):
            if item.suffix != ".json":
                raise AssertionError("unexpected scenario artifact: " + item.name)
            record = parse_json(item.read_bytes())
            if not isinstance(record, dict):
                raise AssertionError("scenario must be a JSON mapping")
            if record.get("schema") != "skeleton.ai.guard.case.v1":
                raise AssertionError("scenario schema mismatch")
            sid = record.get("id")
            if not isinstance(sid, str) or not sid.startswith(domain + "-"):
                raise AssertionError("scenario ID not bound to domain")
            if sid in seen:
                raise AssertionError("duplicate scenario ID")
            if record.get("control") != domain or type(record.get("expected_allow")) is not bool:
                raise AssertionError("scenario contract mismatch")
            if not isinstance(record.get("input"), dict):
                raise AssertionError("scenario input must be mapping")
            if not isinstance(record.get("threat"), str) or not record["threat"]:
                raise AssertionError("scenario must document threat")
            seen.add(sid)
            counts[domain] += 1
            yield record
    if any(n != EXPECTED_PER_DOMAIN for n in counts.values()):
        raise AssertionError("incomplete threat coverage: " + repr(counts))


def run_all() -> list[ScenarioResult]:
    results = []
    for record in iter_scenarios():
        outcome = evaluate(record["control"], record["input"])
        results.append(ScenarioResult(
            record["id"], record["control"], record["expected_allow"],
            outcome["allowed"], outcome["code"],
        ))
    if len(results) != TOTAL_SCENARIOS:
        raise AssertionError("incomplete control matrix")
    return results


def verify_all() -> dict:
    results = run_all()
    failures = [result for result in results if not result.passed]
    return {
        "schema": "skeleton.ai.guard.suite.v1",
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "failure_ids": [f.scenario_id for f in failures],
        "status": "passed" if not failures else "failed",
        "real_model_tested": False,
        "release_certified": False,
    }
