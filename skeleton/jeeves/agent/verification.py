"""Deterministic verification plane for Jeeves agent execution.

Execution answers "did the handler return?" Verification answers "does the
observed state satisfy the step contract?"  The two are intentionally separate.
Model judgment may be attached as advisory evidence, but host predicates,
provenance checks, policy constraints, and observation integrity are authoritative.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .evidence import Contradiction, EvidenceLedger
from .types import (
    AgentContractError,
    PlanStep,
    RiskTier,
    ToolObservation,
    bounded_text,
    finite_number,
    json_safe,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class VerificationError(RuntimeError):
    pass


class CheckSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    check_id: str
    name: str
    passed: bool
    severity: CheckSeverity
    message: str
    evidence_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", require_id("check_id", self.check_id))
        object.__setattr__(self, "name", bounded_text("check name", self.name, maximum=256))
        if not isinstance(self.passed, bool):
            raise AgentContractError("verification check passed must be boolean")
        if not isinstance(self.severity, CheckSeverity):
            object.__setattr__(self, "severity", CheckSeverity(str(self.severity)))
        object.__setattr__(self, "message", bounded_text("check message", self.message, maximum=8192))
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(require_id("evidence_id", item) for item in self.evidence_ids),
        )
        object.__setattr__(self, "details", json_safe(dict(self.details)))


@dataclass(frozen=True, slots=True)
class VerificationReport:
    step_id: str
    passed: bool
    score: float
    checks: tuple[VerificationCheck, ...]
    evidence_ids: tuple[str, ...]
    contradictions: tuple[Contradiction, ...] = ()
    advisory_confidence: float | None = None
    advisory_reasons: tuple[str, ...] = ()
    verified_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", require_id("step_id", self.step_id))
        if not isinstance(self.passed, bool):
            raise AgentContractError("verification report passed must be boolean")
        object.__setattr__(self, "score", probability("verification score", self.score))
        checks = tuple(self.checks)
        if any(not isinstance(check, VerificationCheck) for check in checks):
            raise AgentContractError("verification checks must contain VerificationCheck values")
        object.__setattr__(self, "checks", checks)
        ids = tuple(require_id("evidence_id", item) for item in self.evidence_ids)
        object.__setattr__(self, "evidence_ids", ids)
        contradictions = tuple(self.contradictions)
        if any(not isinstance(item, Contradiction) for item in contradictions):
            raise AgentContractError("contradictions must contain Contradiction values")
        object.__setattr__(self, "contradictions", contradictions)
        if self.advisory_confidence is not None:
            object.__setattr__(
                self,
                "advisory_confidence",
                probability("advisory_confidence", self.advisory_confidence),
            )
        object.__setattr__(
            self,
            "advisory_reasons",
            tuple(bounded_text("advisory reason", item, maximum=4096) for item in self.advisory_reasons),
        )
        verified = finite_number("verified_at", self.verified_at)
        if verified < 0:
            raise AgentContractError("verified_at must be non-negative")
        object.__setattr__(self, "verified_at", verified)

    @property
    def failures(self) -> tuple[VerificationCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    @property
    def fatal(self) -> bool:
        return any(not check.passed and check.severity is CheckSeverity.FATAL for check in self.checks)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "step_id": self.step_id,
                "passed": self.passed,
                "score": self.score,
                "checks": [
                    (check.check_id, check.passed, check.severity.value, check.evidence_ids)
                    for check in self.checks
                ],
                "evidence_ids": self.evidence_ids,
                "contradictions": [item.contradiction_id for item in self.contradictions],
                "advisory_confidence": self.advisory_confidence,
            }
        )


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    minimum_score: float = 1.0
    require_observation_for_tools: bool = True
    require_evidence_for_tools: bool = True
    reject_contradictions: bool = True
    reject_failed_observations: bool = True
    require_explicit_mutation_verification: bool = True
    maximum_evidence_age_seconds: float | None = None
    model_advisory_minimum_confidence: float = 0.6

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum_score", probability("minimum_score", self.minimum_score))
        object.__setattr__(
            self,
            "model_advisory_minimum_confidence",
            probability("model_advisory_minimum_confidence", self.model_advisory_minimum_confidence),
        )
        if self.maximum_evidence_age_seconds is not None:
            age = finite_number("maximum_evidence_age_seconds", self.maximum_evidence_age_seconds)
            if age <= 0:
                raise AgentContractError("maximum_evidence_age_seconds must be positive")
            object.__setattr__(self, "maximum_evidence_age_seconds", age)


PredicateFn = Callable[[Any, Mapping[str, Any]], tuple[bool, str, Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class PredicateSpec:
    name: str
    description: str
    handler: PredicateFn

    def __post_init__(self) -> None:
        normalized = str(self.name).strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", normalized):
            raise AgentContractError("invalid verification predicate name")
        object.__setattr__(self, "name", normalized)
        object.__setattr__(self, "description", bounded_text("predicate description", self.description, maximum=2048))
        if not callable(self.handler):
            raise AgentContractError("predicate handler must be callable")


class PredicateRegistry:
    """Registry of pure host-side result predicates.

    Predicate specs are intentionally tiny and JSON-only so they can be stored
    in plan metadata without embedding executable code in model output.
    """

    def __init__(self) -> None:
        self._predicates: dict[str, PredicateSpec] = {}
        self._install_defaults()

    def register(self, spec: PredicateSpec) -> None:
        if spec.name in self._predicates:
            raise VerificationError(f"verification predicate already registered: {spec.name}")
        self._predicates[spec.name] = spec

    def evaluate(self, name: str, payload: Any, arguments: Mapping[str, Any] | None = None) -> tuple[bool, str, Mapping[str, Any]]:
        normalized = str(name).strip().lower()
        spec = self._predicates.get(normalized)
        if spec is None:
            raise VerificationError(f"unknown verification predicate: {normalized}")
        result = spec.handler(json_safe(payload), json_safe(dict(arguments or {})))
        if not isinstance(result, tuple) or len(result) != 3:
            raise VerificationError("predicate returned invalid shape")
        passed, message, details = result
        if not isinstance(passed, bool) or not isinstance(message, str) or not isinstance(details, Mapping):
            raise VerificationError("predicate returned invalid types")
        return passed, message, json_safe(dict(details))

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._predicates))

    def _install_defaults(self) -> None:
        self.register(PredicateSpec("truthy", "Payload must be truthy.", self._truthy))
        self.register(PredicateSpec("non_empty", "Payload must not be empty.", self._non_empty))
        self.register(PredicateSpec("equals", "Payload must equal expected JSON value.", self._equals))
        self.register(PredicateSpec("not_equals", "Payload must differ from forbidden JSON value.", self._not_equals))
        self.register(PredicateSpec("contains", "Container/string payload must contain a value.", self._contains))
        self.register(PredicateSpec("contains_key", "Object payload must contain a key.", self._contains_key))
        self.register(PredicateSpec("field_equals", "Object field must equal expected value.", self._field_equals))
        self.register(PredicateSpec("field_truthy", "Object field must be truthy.", self._field_truthy))
        self.register(PredicateSpec("numeric_range", "Numeric payload or field must fall in a range.", self._numeric_range))
        self.register(PredicateSpec("length_range", "Payload length must fall in a range.", self._length_range))
        self.register(PredicateSpec("all_items_truthy", "Every array item must be truthy.", self._all_items_truthy))
        self.register(PredicateSpec("status_success", "Common status fields must indicate success.", self._status_success))

    @staticmethod
    def _truthy(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        passed = bool(payload)
        return passed, "payload is truthy" if passed else "payload is falsy", {}

    @staticmethod
    def _non_empty(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        try:
            length = len(payload)
        except TypeError:
            length = 1 if payload is not None else 0
        passed = length > 0
        return passed, f"payload length={length}", {"length": length}

    @staticmethod
    def _equals(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        expected = arguments.get("expected")
        passed = stable_fingerprint(payload) == stable_fingerprint(expected)
        return passed, "payload matches expected" if passed else "payload does not match expected", {"expected": expected}

    @staticmethod
    def _not_equals(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        forbidden = arguments.get("forbidden")
        passed = stable_fingerprint(payload) != stable_fingerprint(forbidden)
        return passed, "payload differs from forbidden" if passed else "payload equals forbidden", {"forbidden": forbidden}

    @staticmethod
    def _contains(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        needle = arguments.get("value")
        try:
            passed = needle in payload
        except TypeError:
            passed = False
        return passed, "payload contains value" if passed else "payload does not contain value", {"value": needle}

    @staticmethod
    def _contains_key(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        key = arguments.get("key")
        passed = isinstance(payload, dict) and isinstance(key, str) and key in payload
        return passed, f"key {key!r} present" if passed else f"key {key!r} missing", {"key": key}

    @staticmethod
    def _field_equals(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        field = arguments.get("field")
        expected = arguments.get("expected")
        actual = payload.get(field) if isinstance(payload, dict) and isinstance(field, str) else None
        passed = isinstance(payload, dict) and isinstance(field, str) and field in payload and stable_fingerprint(actual) == stable_fingerprint(expected)
        return passed, "field matches expected" if passed else "field does not match expected", {"field": field, "actual": actual, "expected": expected}

    @staticmethod
    def _field_truthy(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        field = arguments.get("field")
        actual = payload.get(field) if isinstance(payload, dict) and isinstance(field, str) else None
        passed = bool(actual)
        return passed, "field is truthy" if passed else "field is falsy or absent", {"field": field, "actual": actual}

    @staticmethod
    def _numeric_range(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        field = arguments.get("field")
        value = payload.get(field) if field is not None and isinstance(payload, dict) else payload
        minimum = arguments.get("minimum")
        maximum = arguments.get("maximum")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, "value is not numeric", {"value": value, "field": field}
        number = float(value)
        if not (number == number and abs(number) != float("inf")):
            return False, "value is not finite", {"value": value, "field": field}
        passed = True
        if minimum is not None:
            passed = passed and number >= float(minimum)
        if maximum is not None:
            passed = passed and number <= float(maximum)
        return passed, "numeric value is within range" if passed else "numeric value is outside range", {"value": number, "minimum": minimum, "maximum": maximum, "field": field}

    @staticmethod
    def _length_range(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        minimum = int(arguments.get("minimum", 0))
        maximum = arguments.get("maximum")
        try:
            length = len(payload)
        except TypeError:
            return False, "payload has no length", {}
        passed = length >= minimum and (maximum is None or length <= int(maximum))
        return passed, "payload length is within range" if passed else "payload length is outside range", {"length": length, "minimum": minimum, "maximum": maximum}

    @staticmethod
    def _all_items_truthy(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        if not isinstance(payload, list):
            return False, "payload is not an array", {}
        passed = bool(payload) and all(bool(item) for item in payload)
        return passed, "all array items are truthy" if passed else "one or more array items are falsy", {"count": len(payload)}

    @staticmethod
    def _status_success(payload: Any, arguments: Mapping[str, Any]) -> tuple[bool, str, Mapping[str, Any]]:
        if not isinstance(payload, dict):
            return False, "payload is not an object", {}
        candidates = [payload.get("ok"), payload.get("success"), payload.get("status")]
        passed = any(value is True or (isinstance(value, str) and value.lower() in {"ok", "success", "succeeded", "complete", "completed"}) for value in candidates)
        return passed, "status indicates success" if passed else "status does not indicate success", {"candidates": candidates}


@dataclass(frozen=True, slots=True)
class PredicateRequest:
    predicate: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = str(self.predicate).strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", normalized):
            raise AgentContractError("invalid predicate request name")
        object.__setattr__(self, "predicate", normalized)
        object.__setattr__(self, "arguments", json_safe(dict(self.arguments)))


class VerificationDirectiveParser:
    """Parse machine-verifiable directives embedded in a step verification.

    Human prose remains allowed, but only directives using the ``check:`` form
    become deterministic predicates.  Examples:

    ``check:contains_key key=sha``
    ``check:field_equals field=status expected=completed``
    ``check:numeric_range field=count minimum=1 maximum=100``
    """

    _LINE_RE = re.compile(r"^\s*check:([a-z][a-z0-9_-]{0,63})(?:\s+(.*))?\s*$", re.IGNORECASE)

    def parse(self, text: str) -> tuple[PredicateRequest, ...]:
        if not text:
            return ()
        requests: list[PredicateRequest] = []
        for raw_line in text.splitlines():
            match = self._LINE_RE.match(raw_line)
            if not match:
                continue
            name = match.group(1).lower()
            raw_args = match.group(2) or ""
            arguments = self._parse_args(raw_args)
            requests.append(PredicateRequest(name, arguments))
        return tuple(requests)

    @staticmethod
    def _parse_args(raw: str) -> dict[str, Any]:
        arguments: dict[str, Any] = {}
        # Compact shell-like format without executing a shell.  Quoted strings
        # are intentionally not supported; JSON values can be supplied after '='.
        for token in raw.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key):
                raise VerificationError(f"invalid verification argument key: {key}")
            parsed: Any = value
            if value in {"true", "false"}:
                parsed = value == "true"
            elif value in {"null", "none"}:
                parsed = None
            else:
                try:
                    if "." in value:
                        parsed = float(value)
                    else:
                        parsed = int(value)
                except ValueError:
                    parsed = value
            arguments[key] = parsed
        return arguments


class StepVerifier:
    def __init__(
        self,
        ledger: EvidenceLedger,
        *,
        policy: VerificationPolicy | None = None,
        predicates: PredicateRegistry | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ledger = ledger
        self.policy = policy or VerificationPolicy()
        self.predicates = predicates or PredicateRegistry()
        self._parser = VerificationDirectiveParser()
        self._clock = clock

    def verify(
        self,
        step: PlanStep,
        *,
        observations: Sequence[ToolObservation] = (),
        advisory: Mapping[str, Any] | None = None,
    ) -> VerificationReport:
        if not isinstance(step, PlanStep):
            raise TypeError("step must be PlanStep")
        relevant = tuple(observations)
        checks: list[VerificationCheck] = []
        evidence_ids: list[str] = []

        if step.tool is not None:
            checks.extend(self._check_tool_observation(step, relevant))
            for observation in relevant:
                evidence_ids.extend(ref.evidence_id for ref in observation.evidence)
        else:
            checks.append(self._check_reasoning_step(step))

        checks.extend(self._check_evidence_integrity(evidence_ids))
        checks.extend(self._check_mutation_contract(step))
        checks.extend(self._check_predicates(step, relevant))

        contradictions = self.ledger.contradictions_for(evidence_ids)
        if contradictions:
            checks.append(
                self._check(
                    "contradictions",
                    not self.policy.reject_contradictions,
                    CheckSeverity.ERROR,
                    "referenced evidence contains contradictions",
                    evidence_ids=evidence_ids,
                    details={"contradiction_ids": [item.contradiction_id for item in contradictions]},
                )
            )

        advisory_confidence: float | None = None
        advisory_reasons: tuple[str, ...] = ()
        if advisory is not None:
            advisory_confidence, advisory_reasons, advisory_check = self._check_advisory(advisory, evidence_ids)
            checks.append(advisory_check)

        passed_checks = sum(1 for check in checks if check.passed)
        score = passed_checks / len(checks) if checks else 1.0
        hard_failure = any(
            not check.passed and check.severity in {CheckSeverity.ERROR, CheckSeverity.FATAL}
            for check in checks
        )
        passed = not hard_failure and score >= self.policy.minimum_score
        return VerificationReport(
            step_id=step.step_id,
            passed=passed,
            score=score,
            checks=tuple(checks),
            evidence_ids=tuple(dict.fromkeys(evidence_ids)),
            contradictions=contradictions,
            advisory_confidence=advisory_confidence,
            advisory_reasons=advisory_reasons,
            verified_at=self._clock(),
        )

    def _check_tool_observation(self, step: PlanStep, observations: Sequence[ToolObservation]) -> list[VerificationCheck]:
        matching = [item for item in observations if item.tool_name == step.tool]
        checks: list[VerificationCheck] = []
        checks.append(
            self._check(
                "tool-observation-present",
                bool(matching) or not self.policy.require_observation_for_tools,
                CheckSeverity.FATAL,
                "matching tool observation exists" if matching else "no matching tool observation exists",
            )
        )
        if not matching:
            return checks
        latest = matching[-1]
        checks.append(
            self._check(
                "tool-observation-success",
                latest.ok or not self.policy.reject_failed_observations,
                CheckSeverity.FATAL,
                "tool observation succeeded" if latest.ok else f"tool observation failed: {latest.error or 'unknown error'}",
                evidence_ids=tuple(ref.evidence_id for ref in latest.evidence),
            )
        )
        checks.append(
            self._check(
                "tool-evidence-present",
                bool(latest.evidence) or not self.policy.require_evidence_for_tools,
                CheckSeverity.ERROR,
                "tool produced evidence" if latest.evidence else "tool produced no evidence",
            )
        )
        return checks

    def _check_reasoning_step(self, step: PlanStep) -> VerificationCheck:
        # Reasoning-only steps cannot prove external world state.  They pass this
        # structural check and are later constrained by final grounding.
        return self._check(
            "reasoning-only",
            True,
            CheckSeverity.INFO,
            "reasoning-only step has no external side effect to verify",
        )

    def _check_evidence_integrity(self, evidence_ids: Sequence[str]) -> list[VerificationCheck]:
        checks: list[VerificationCheck] = []
        now = self._clock()
        for evidence_id in dict.fromkeys(evidence_ids):
            artifact = self.ledger.get(evidence_id)
            if artifact is None:
                checks.append(
                    self._check(
                        f"evidence-exists-{evidence_id}",
                        False,
                        CheckSeverity.FATAL,
                        f"evidence {evidence_id} is missing from ledger",
                    )
                )
                continue
            checks.append(
                self._check(
                    f"evidence-fingerprint-{evidence_id}",
                    artifact.fingerprint == stable_fingerprint(artifact.payload),
                    CheckSeverity.FATAL,
                    f"evidence {evidence_id} fingerprint is internally consistent",
                    evidence_ids=(evidence_id,),
                )
            )
            if self.policy.maximum_evidence_age_seconds is not None:
                age = now - artifact.observed_at
                fresh = 0 <= age <= self.policy.maximum_evidence_age_seconds
                checks.append(
                    self._check(
                        f"evidence-fresh-{evidence_id}",
                        fresh,
                        CheckSeverity.ERROR,
                        f"evidence age={age:.3f}s",
                        evidence_ids=(evidence_id,),
                        details={"age_seconds": age},
                    )
                )
        return checks

    def _check_mutation_contract(self, step: PlanStep) -> list[VerificationCheck]:
        if step.risk not in {RiskTier.MUTATING, RiskTier.EXTERNAL, RiskTier.HIGH_IMPACT}:
            return []
        explicit = bool(step.verification.strip())
        return [
            self._check(
                "mutation-verification-contract",
                explicit or not self.policy.require_explicit_mutation_verification,
                CheckSeverity.FATAL,
                "mutating step has explicit verification" if explicit else "mutating step lacks explicit verification",
            )
        ]

    def _check_predicates(self, step: PlanStep, observations: Sequence[ToolObservation]) -> list[VerificationCheck]:
        directives = self._parser.parse(step.verification)
        if not directives:
            return []
        if not observations:
            return [
                self._check(
                    "predicate-observation",
                    False,
                    CheckSeverity.ERROR,
                    "verification predicates require an observation",
                )
            ]
        payload = observations[-1].payload
        evidence_ids = tuple(ref.evidence_id for ref in observations[-1].evidence)
        checks: list[VerificationCheck] = []
        for index, directive in enumerate(directives, start=1):
            try:
                passed, message, details = self.predicates.evaluate(
                    directive.predicate,
                    payload,
                    directive.arguments,
                )
            except Exception as exc:
                passed = False
                message = f"predicate raised {type(exc).__name__}: {str(exc)[:512]}"
                details = {"predicate": directive.predicate}
            checks.append(
                self._check(
                    f"predicate-{index}-{directive.predicate}",
                    passed,
                    CheckSeverity.ERROR,
                    message,
                    evidence_ids=evidence_ids,
                    details=details,
                )
            )
        return checks

    def _check_advisory(
        self,
        advisory: Mapping[str, Any],
        host_evidence_ids: Sequence[str],
    ) -> tuple[float, tuple[str, ...], VerificationCheck]:
        payload = json_safe(dict(advisory))
        passed_value = payload.get("passed")
        confidence_value = payload.get("confidence", 0.0)
        reasons_value = payload.get("reasons", [])
        ids_value = payload.get("evidence_ids", [])
        confidence = probability("advisory confidence", confidence_value)
        reasons = tuple(str(item)[:4096] for item in reasons_value) if isinstance(reasons_value, list) else ()
        ids = tuple(str(item) for item in ids_value) if isinstance(ids_value, list) else ()
        evidence_subset = set(ids).issubset(set(host_evidence_ids))
        structurally_valid = isinstance(passed_value, bool) and evidence_subset
        # Advisory disagreement does not override deterministic checks.  It is
        # a warning unless the model claims confidence without host evidence.
        accepted = structurally_valid and confidence >= self.policy.model_advisory_minimum_confidence
        severity = CheckSeverity.WARNING if structurally_valid else CheckSeverity.ERROR
        message = (
            f"model advisory accepted (passed={passed_value}, confidence={confidence:.3f})"
            if accepted
            else "model advisory is low-confidence or structurally invalid"
        )
        return confidence, reasons, self._check(
            "model-advisory",
            structurally_valid,
            severity,
            message,
            evidence_ids=ids if evidence_subset else (),
            details={"model_passed": passed_value, "confidence": confidence, "evidence_subset": evidence_subset},
        )

    @staticmethod
    def _check(
        name: str,
        passed: bool,
        severity: CheckSeverity,
        message: str,
        *,
        evidence_ids: Sequence[str] = (),
        details: Mapping[str, Any] | None = None,
    ) -> VerificationCheck:
        check_id = stable_id(
            "check",
            {
                "name": name,
                "passed": passed,
                "severity": severity.value,
                "message": message,
                "evidence_ids": list(evidence_ids),
                "details": dict(details or {}),
            },
        )
        return VerificationCheck(
            check_id=check_id,
            name=name,
            passed=passed,
            severity=severity,
            message=message,
            evidence_ids=tuple(evidence_ids),
            details=dict(details or {}),
        )


def parse_advisory_json(content: str) -> Mapping[str, Any]:
    """Strictly parse a verifier-model JSON response into JSON-only data."""
    import json

    if not isinstance(content, str) or not content.strip():
        raise VerificationError("verification advisory is empty")
    text = content.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[len("```json") : -3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VerificationError("verification advisory is not valid JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError("verification advisory must be an object")
    return json_safe(value)
