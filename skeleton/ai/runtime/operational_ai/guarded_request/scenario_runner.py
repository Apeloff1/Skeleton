"""Discover and execute every versioned adversarial capacity/control fixture.

A fixture is accepted only when its declared result matches a live gate result.
The suite fails closed on missing, duplicated, malformed and unknown domains.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Iterator

from .contracts import MAX_TEXT_CHARS, parse_json
from .errors import GateDenied
from .policy_oracle import evaluate

DOMAINS = (
    "identity", "quota", "model_pin", "evidence", "grant", "pressure",
    "stream", "transport", "nonce", "queue", "effects", "context",
    "envelope", "memory", "tokens", "workspace",
)
EXPECTED_PER_DOMAIN = 24
TOTAL_SCENARIOS = len(DOMAINS) * EXPECTED_PER_DOMAIN



def _read_fixture(data: bytes, *, domain: str, filename: str) -> dict:
    """Preserve one deliberate oversized negative vector without weakening ingress."""
    try:
        return parse_json(data)
    except GateDenied as error:
        if (domain, filename, error.code) != ("tokens", "tokens-24.json", "json-text"):
            raise

    def pairs(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise AssertionError("duplicate scenario key")
            result[key] = value
        return result

    def constant(_value: str) -> None:
        raise AssertionError("nonfinite scenario constant")

    try:
        record = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise AssertionError("malformed oversized scenario") from exc
    if (type(record) is not dict or record.get("id") != "tokens-24"
            or record.get("control") != "tokens"
            or record.get("expected_allow") is not False
            or type(record.get("input")) is not dict
            or record["input"].get("prompt") != "x" * (MAX_TEXT_CHARS + 1)):
        raise AssertionError("unauthorized oversized scenario")
    bounded = {**record, "input": {**record["input"], "prompt": "x"}}
    parse_json(json.dumps(bounded, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8"))
    return record


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
            record = _read_fixture(item.read_bytes(), domain=domain, filename=item.name)
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
