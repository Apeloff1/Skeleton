"""Verified bounded result receipts, no raw private prompts or outputs."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import hex64, identity, integer
from .errors import deny


@dataclass(frozen=True, slots=True)
class StepResult:
    step: int
    session_id: str
    request_id: str
    revision: int
    model_digest: str
    tokenizer_digest: str
    output_sha256: str
    runtime_output_digest: str
    output_chars: int
    prompt_tokens: int
    generated_tokens: int
    latency_ms: int
    checks_passed: int
    checks_total: int
    failed_checks: tuple[str, ...]
    audit_status: str
    replayed: bool

    def __post_init__(self) -> None:
        for x in ("step", "revision", "output_chars", "prompt_tokens",
                  "generated_tokens", "latency_ms", "checks_passed", "checks_total"):
            integer(getattr(self, x), x, 0, 2**31 - 1)
        for x in ("session_id", "request_id", "audit_status"):
            identity(getattr(self, x), x)
        for x in ("model_digest", "tokenizer_digest", "output_sha256", "runtime_output_digest"):
            hex64(getattr(self, x), x)
        if self.checks_passed > self.checks_total:
            deny("step-check-overflow")
        if type(self.failed_checks) is not tuple:
            deny("step-failure-array")
        for x in self.failed_checks:
            identity(x, "failed-check")
        if len(self.failed_checks) != self.checks_total - self.checks_passed:
            deny("step-check-incoherent")
        if type(self.replayed) is not bool:
            deny("step-replay-type")

    @property
    def passed(self) -> bool:
        return self.checks_total == self.checks_passed and not self.replayed

    def record(self) -> dict:
        from .canonical import sha256
        return {
            **{key: getattr(self, key) for key in self.__dataclass_fields__
               if key not in ("failed_checks", "session_id", "request_id")},
            "session_sha256": sha256(self.session_id.encode("utf-8")),
            "request_sha256": sha256(self.request_id.encode("utf-8")),
            "failed_checks": list(self.failed_checks),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    domain: str
    severity: str
    source_sha256: str
    steps: tuple[StepResult, ...]
    error_code: str | None

    def __post_init__(self) -> None:
        identity(self.case_id, "case")
        identity(self.domain, "domain")
        hex64(self.source_sha256, "source")
        if self.severity not in ("critical", "high", "medium"):
            deny("severity")
        if type(self.steps) is not tuple or len(self.steps) > 4:
            deny("steps")
        for x in self.steps:
            if type(x) is not StepResult:
                deny("step-type")
        if self.error_code is not None:
            identity(self.error_code, "error")

    @property
    def passed(self) -> bool:
        return self.error_code is None and bool(self.steps) and all(x.passed for x in self.steps)

    def record(self) -> dict:
        return {
            "case_id": self.case_id, "domain": self.domain,
            "severity": self.severity, "source_sha256": self.source_sha256,
            "steps": [x.record() for x in self.steps],
            "passed": self.passed,
            "error_code": self.error_code,
        }
