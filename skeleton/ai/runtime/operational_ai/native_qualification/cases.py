"""Source-versioned original task cases: bounded prompts and independently fixed checks."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .canonical import encode, identity, integer, sha256, text
from .checks import Check, MAX_CHECKS
from .errors import deny

SCHEMA = "skeleton.native-qualification.case.v1"
MAX_STEPS = 4


@dataclass(frozen=True, slots=True)
class Step:
    prompt: str
    checks: tuple[Check, ...]
    intermediate: bool = False

    def __post_init__(self) -> None:
        text(self.prompt, "step-prompt", 8192)
        if not self.prompt:
            deny("step-empty-prompt")
        if type(self.checks) is not tuple or len(self.checks) > MAX_CHECKS:
            deny("step-check-count")
        if not self.intermediate and not self.checks:
            deny("step-no-check")
        if type(self.intermediate) is not bool:
            deny("step-intermediate")
        for check in self.checks:
            if type(check) is not Check:
                deny("step-check-type")

    @classmethod
    def from_json(cls, value: Any) -> "Step":
        if type(value) is not dict or set(value) - {"prompt", "checks", "intermediate"}:
            deny("step-schema")
        checks = value.get("checks")
        if type(checks) is not list:
            deny("step-check-array")
        return cls(
            value.get("prompt"),
            tuple(Check.from_json(c) for c in checks),
            value.get("intermediate", False),
        )

    def record(self) -> dict:
        return {
            "prompt": self.prompt, "checks": [c.record() for c in self.checks],
            "intermediate": self.intermediate,
        }


@dataclass(frozen=True, slots=True)
class QualificationCase:
    case_id: str
    domain: str
    severity: str
    objective: str
    steps: tuple[Step, ...]
    seed: int = 0
    temperature: float = 0.7
    owner: str = "qualification"
    license_id: str = "original-fixture"

    def __post_init__(self) -> None:
        identity(self.case_id, "case")
        identity(self.domain, "domain")
        identity(self.owner, "owner")
        if self.severity not in ("critical", "high", "medium"):
            deny("case-severity")
        text(self.objective, "case-objective", 512)
        if not self.objective:
            deny("case-objective")
        if type(self.steps) is not tuple or not 1 <= len(self.steps) <= MAX_STEPS:
            deny("case-step-count")
        for step in self.steps:
            if type(step) is not Step:
                deny("case-step-type")
        integer(self.seed, "case-seed", 0, 2**31 - 1)
        if type(self.temperature) is not float or not 0.01 <= self.temperature <= 2.0:
            deny("case-temperature")
        identity(self.license_id, "license")

    @classmethod
    def from_json(cls, value: Any) -> "QualificationCase":
        keys = {"schema", "id", "domain", "severity", "objective", "steps",
                "seed", "temperature", "owner", "license_id"}
        if type(value) is not dict or set(value) != keys or value["schema"] != SCHEMA:
            deny("case-schema")
        if type(value["steps"]) is not list:
            deny("case-steps")
        return cls(
            case_id=value["id"], domain=value["domain"],
            severity=value["severity"], objective=value["objective"],
            steps=tuple(Step.from_json(s) for s in value["steps"]),
            seed=value["seed"], temperature=value["temperature"],
            owner=value["owner"], license_id=value["license_id"],
        )

    def record(self) -> dict:
        return {
            "schema": SCHEMA, "id": self.case_id, "domain": self.domain,
            "severity": self.severity, "objective": self.objective,
            "steps": [s.record() for s in self.steps],
            "seed": self.seed, "temperature": self.temperature,
            "owner": self.owner, "license_id": self.license_id,
        }

    @property
    def content_sha256(self) -> str:
        return sha256(encode(self.record()))
