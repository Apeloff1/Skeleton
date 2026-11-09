"""P3 plan analysis, failure simulation and trusted tool composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Iterable, Mapping, Sequence

from .workflow import CompiledWorkflow, simulate_schedule


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ToolCompositionError(RuntimeError):
    pass


def _id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not _ID.fullmatch(text):
        raise ValueError(f"{field} must be canonical bounded identifier")
    return text


def _sha(value: object, field: str) -> str:
    text = _id(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


def _refs(values: Iterable[str], field: str, *, required: bool = False) -> tuple[str, ...]:
    normalized = tuple(sorted({_id(item, field) for item in values}))
    if required and not normalized:
        raise ValueError(f"{field} requires at least one item")
    if len(normalized) > 128:
        raise ValueError(f"{field} exceeds bound")
    return normalized


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class PlanDiagnostic:
    rule_id: str
    severity: str
    task_id: str
    message: str
    remediation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _id(self.rule_id, "rule_id"))
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("unsupported diagnostic severity")
        object.__setattr__(self, "task_id", _id(self.task_id, "task_id"))
        if not self.message.strip() or not self.remediation.strip():
            raise ValueError("diagnostic message/remediation required")

    def as_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "task_id": self.task_id,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass(frozen=True, slots=True)
class PlanAnalysis:
    workflow_id: str
    ir_digest: str
    diagnostics: tuple[PlanDiagnostic, ...]
    analysis_digest: str

    @property
    def errors(self) -> tuple[PlanDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "error")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.plan_analysis.v1",
            "workflow_id": self.workflow_id,
            "ir_digest": self.ir_digest,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "analysis_digest": self.analysis_digest,
        }


def _descendants(workflow: CompiledWorkflow) -> dict[str, set[str]]:
    children = {task.task_id: set() for task in workflow.tasks}
    for task in workflow.tasks:
        for dep in task.depends_on:
            children[dep].add(task.task_id)
    result: dict[str, set[str]] = {}
    for task_id in children:
        seen: set[str] = set()
        stack = list(children[task_id])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(children[current])
        result[task_id] = seen
    return result


def analyze_plan(workflow: CompiledWorkflow) -> PlanAnalysis:
    """Deterministically lint effect safety and verification topology."""

    descendants = _descendants(workflow)
    by = workflow.task_map
    diagnostics: list[PlanDiagnostic] = []
    for task in workflow.tasks:
        effectful = task.effect_class in {"write", "external"}
        if effectful and not task.conflict_keys:
            diagnostics.append(
                PlanDiagnostic(
                    "effect-conflict-key",
                    "error",
                    task.task_id,
                    "Effectful task has no declared conflict key.",
                    "Declare the repository/resource conflict domain before execution.",
                )
            )
        if effectful and not task.required_capabilities:
            diagnostics.append(
                PlanDiagnostic(
                    "effect-capability",
                    "error",
                    task.task_id,
                    "Effectful task has no required capability.",
                    "Declare the narrow capability required for the effect.",
                )
            )
        if effectful:
            verifier = any(
                by[item].kind == "verify"
                for item in descendants[task.task_id]
            )
            if not verifier:
                diagnostics.append(
                    PlanDiagnostic(
                        "post-effect-verifier",
                        "error",
                        task.task_id,
                        "No downstream independent verification task is present.",
                        "Add a verify task downstream of the effectful task.",
                    )
                )
        if task.effect_class == "external" and task.max_attempts > 1:
            diagnostics.append(
                PlanDiagnostic(
                    "external-retry",
                    "warning",
                    task.task_id,
                    "External effect permits multiple attempts.",
                    "Use an idempotency fence or reduce max_attempts to one.",
                )
            )
    diagnostics.sort(
        key=lambda item: (
            {"error": 0, "warning": 1, "info": 2}[item.severity],
            item.task_id,
            item.rule_id,
        )
    )
    material = {
        "workflow_id": workflow.workflow_id,
        "ir_digest": workflow.ir_digest,
        "diagnostics": [item.as_dict() for item in diagnostics],
    }
    return PlanAnalysis(
        workflow_id=workflow.workflow_id,
        ir_digest=workflow.ir_digest,
        diagnostics=tuple(diagnostics),
        analysis_digest=_digest(material),
    )


@dataclass(frozen=True, slots=True)
class PlanSimulationReceipt:
    workflow_id: str
    ir_digest: str
    schedule_digest: str
    failure_scenarios: tuple[Mapping[str, str], ...]
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.production_authority is not False:
            raise ValueError("plan simulation can never grant production authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.plan_simulation.v1",
            "workflow_id": self.workflow_id,
            "ir_digest": self.ir_digest,
            "schedule_digest": self.schedule_digest,
            "failure_scenarios": [dict(item) for item in self.failure_scenarios],
            "production_authority": False,
        }


def simulate_plan_failures(workflow: CompiledWorkflow) -> PlanSimulationReceipt:
    schedule = simulate_schedule(workflow)
    schedule_digest = _digest(schedule.as_dict())
    scenarios: list[dict[str, str]] = []
    for task in workflow.tasks:
        scenarios.append(
            {
                "task_id": task.task_id,
                "scenario": "timeout",
                "expected_control": "bounded-attempt-stop",
            }
        )
        if task.required_capabilities:
            scenarios.append(
                {
                    "task_id": task.task_id,
                    "scenario": "capability-unavailable",
                    "expected_control": "fail-closed-no-effect",
                }
            )
        if task.effect_class in {"write", "external"}:
            scenarios.extend(
                [
                    {
                        "task_id": task.task_id,
                        "scenario": "resource-exhaustion",
                        "expected_control": "budget-deny-or-compensate",
                    },
                    {
                        "task_id": task.task_id,
                        "scenario": "post-effect-verification-failure",
                        "expected_control": "compensate-before-terminal",
                    },
                ]
            )
    scenarios.sort(key=lambda item: (item["task_id"], item["scenario"]))
    return PlanSimulationReceipt(
        workflow_id=workflow.workflow_id,
        ir_digest=workflow.ir_digest,
        schedule_digest=schedule_digest,
        failure_scenarios=tuple(scenarios),
        production_authority=False,
    )


@dataclass(frozen=True, slots=True)
class ToolManifest:
    tool_id: str
    version: str
    capabilities: tuple[str, ...]
    authority_scopes: tuple[str, ...]
    input_schema_digest: str
    output_schema_digest: str
    risk_level: str
    source_attestation_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_id", _id(self.tool_id, "tool_id"))
        object.__setattr__(self, "version", _id(self.version, "version"))
        object.__setattr__(
            self,
            "capabilities",
            _refs(self.capabilities, "capability", required=True),
        )
        object.__setattr__(
            self,
            "authority_scopes",
            _refs(self.authority_scopes, "authority_scope"),
        )
        object.__setattr__(
            self,
            "input_schema_digest",
            _sha(self.input_schema_digest, "input_schema_digest"),
        )
        object.__setattr__(
            self,
            "output_schema_digest",
            _sha(self.output_schema_digest, "output_schema_digest"),
        )
        if self.risk_level not in {"low", "medium", "high"}:
            raise ValueError("risk_level must be low/medium/high")
        object.__setattr__(
            self,
            "source_attestation_ref",
            _id(self.source_attestation_ref, "source_attestation_ref"),
        )


@dataclass(frozen=True, slots=True)
class ToolHealth:
    tool_id: str
    version: str
    checked_at: datetime
    expires_at: datetime
    transport_ok: bool
    semantic_ok: bool
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_id", _id(self.tool_id, "tool_id"))
        object.__setattr__(self, "version", _id(self.version, "version"))
        checked = _utc(self.checked_at, "checked_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= checked:
            raise ValueError("health expiry must follow check time")
        object.__setattr__(self, "checked_at", checked)
        object.__setattr__(self, "expires_at", expires)
        if not isinstance(self.transport_ok, bool) or not isinstance(self.semantic_ok, bool):
            raise TypeError("health flags must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "health_evidence_ref", required=True),
        )


@dataclass(frozen=True, slots=True)
class ToolBinding:
    binding_id: str
    tool_id: str
    capability: str
    authority_scopes: tuple[str, ...]
    independent_result_validation: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", _id(self.binding_id, "binding_id"))
        object.__setattr__(self, "tool_id", _id(self.tool_id, "tool_id"))
        object.__setattr__(self, "capability", _id(self.capability, "capability"))
        object.__setattr__(
            self,
            "authority_scopes",
            _refs(self.authority_scopes, "binding_authority_scope"),
        )
        if not isinstance(self.independent_result_validation, bool):
            raise TypeError("independent_result_validation must be boolean")


@dataclass(frozen=True, slots=True)
class ToolComposition:
    composition_id: str
    bindings: tuple[ToolBinding, ...]
    dependencies: tuple[tuple[str, str], ...]
    allowed_authority_scopes: tuple[str, ...]
    composition_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.tool_composition.v1",
            "composition_id": self.composition_id,
            "bindings": [
                {
                    "binding_id": item.binding_id,
                    "tool_id": item.tool_id,
                    "capability": item.capability,
                    "authority_scopes": list(item.authority_scopes),
                    "independent_result_validation": item.independent_result_validation,
                }
                for item in self.bindings
            ],
            "dependencies": [list(item) for item in self.dependencies],
            "allowed_authority_scopes": list(self.allowed_authority_scopes),
            "composition_digest": self.composition_digest,
        }


class CompositionCompiler:
    def compile(
        self,
        *,
        composition_id: str,
        bindings: Sequence[ToolBinding],
        manifests: Sequence[ToolManifest],
        health: Sequence[ToolHealth],
        dependencies: Sequence[tuple[str, str]] = (),
        allowed_authority_scopes: Iterable[str] = (),
        now: datetime,
    ) -> ToolComposition:
        cid = _id(composition_id, "composition_id")
        instant = _utc(now, "now")
        if not bindings:
            raise ToolCompositionError("composition requires bindings")
        by_manifest = {item.tool_id: item for item in manifests}
        by_health = {(item.tool_id, item.version): item for item in health}
        allowed = set(_refs(allowed_authority_scopes, "allowed_authority_scope"))
        binding_ids = [item.binding_id for item in bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ToolCompositionError("binding ids must be unique")
        by_binding = {item.binding_id: item for item in bindings}

        for binding in bindings:
            manifest = by_manifest.get(binding.tool_id)
            if manifest is None:
                raise ToolCompositionError(f"missing trusted manifest for {binding.tool_id}")
            if binding.capability not in manifest.capabilities:
                raise ToolCompositionError(
                    f"{binding.binding_id} capability not declared by manifest"
                )
            if not set(binding.authority_scopes) <= set(manifest.authority_scopes):
                raise ToolCompositionError(
                    f"{binding.binding_id} requests authority not declared by tool"
                )
            if not set(binding.authority_scopes) <= allowed:
                raise ToolCompositionError(
                    f"{binding.binding_id} would amplify granted authority"
                )
            state = by_health.get((manifest.tool_id, manifest.version))
            if state is None:
                raise ToolCompositionError(f"missing health for {manifest.tool_id}")
            if instant >= state.expires_at:
                raise ToolCompositionError(f"stale health for {manifest.tool_id}")
            if not state.transport_ok or not state.semantic_ok:
                raise ToolCompositionError(f"unhealthy tool {manifest.tool_id}")
            if manifest.risk_level == "high" and not binding.independent_result_validation:
                raise ToolCompositionError(
                    f"high-risk tool {manifest.tool_id} requires independent result validation"
                )

        deps: list[tuple[str, str]] = []
        for source, target in dependencies:
            left = _id(source, "dependency_source")
            right = _id(target, "dependency_target")
            if left not in by_binding or right not in by_binding:
                raise ToolCompositionError("dependency references unknown binding")
            if left == right:
                raise ToolCompositionError("tool binding cannot depend on itself")
            src = by_manifest[by_binding[left].tool_id]
            dst = by_manifest[by_binding[right].tool_id]
            if src.output_schema_digest != dst.input_schema_digest:
                raise ToolCompositionError(
                    f"schema mismatch across dependency {left}->{right}"
                )
            deps.append((left, right))
        deps = sorted(set(deps))

        children = {key: set() for key in by_binding}
        indegree = {key: 0 for key in by_binding}
        for left, right in deps:
            children[left].add(right)
            indegree[right] += 1
        ready = sorted(key for key, value in indegree.items() if value == 0)
        visited: list[str] = []
        while ready:
            current = ready.pop(0)
            visited.append(current)
            for child in sorted(children[current]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()
        if len(visited) != len(by_binding):
            raise ToolCompositionError("tool dependency cycle")

        normalized_bindings = tuple(sorted(bindings, key=lambda item: item.binding_id))
        material = {
            "composition_id": cid,
            "bindings": [
                {
                    "binding_id": item.binding_id,
                    "tool_id": item.tool_id,
                    "capability": item.capability,
                    "authority_scopes": list(item.authority_scopes),
                    "independent_result_validation": item.independent_result_validation,
                }
                for item in normalized_bindings
            ],
            "dependencies": [list(item) for item in deps],
            "allowed_authority_scopes": sorted(allowed),
            "manifest_identities": {
                item.tool_id: {
                    "version": item.version,
                    "attestation": item.source_attestation_ref,
                    "input": item.input_schema_digest,
                    "output": item.output_schema_digest,
                }
                for item in sorted(manifests, key=lambda item: item.tool_id)
                if item.tool_id in {binding.tool_id for binding in bindings}
            },
        }
        return ToolComposition(
            composition_id=cid,
            bindings=normalized_bindings,
            dependencies=tuple(deps),
            allowed_authority_scopes=tuple(sorted(allowed)),
            composition_digest=_digest(material),
        )


@dataclass(frozen=True, slots=True)
class ToolResultTrust:
    tool_id: str
    result_digest: str
    trust_level: str
    treated_as_data: bool
    independently_validated: bool
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.trust_level not in {"untrusted", "validated", "high-assurance"}:
            raise ValueError("unsupported trust_level")
        if self.treated_as_data is not True:
            raise ValueError("tool results must remain data, never authority/instructions")
        if self.trust_level == "high-assurance" and not self.independently_validated:
            raise ValueError("high-assurance result requires independent validation")


def validate_tool_result(
    *,
    manifest: ToolManifest,
    raw_result: bytes,
    evidence_refs: Iterable[str],
    independently_validated: bool,
) -> ToolResultTrust:
    if not isinstance(raw_result, (bytes, bytearray)):
        raise TypeError("raw_result must be bytes")
    refs = _refs(evidence_refs, "result_evidence_ref", required=True)
    high = manifest.risk_level == "high"
    trust = (
        "high-assurance"
        if high and independently_validated
        else "validated"
        if independently_validated
        else "untrusted"
    )
    if high and not independently_validated:
        trust = "untrusted"
    return ToolResultTrust(
        tool_id=manifest.tool_id,
        result_digest=hashlib.sha256(bytes(raw_result)).hexdigest(),
        trust_level=trust,
        treated_as_data=True,
        independently_validated=independently_validated,
        evidence_refs=refs,
    )


__all__ = [
    "CompositionCompiler",
    "PlanAnalysis",
    "PlanDiagnostic",
    "PlanSimulationReceipt",
    "ToolBinding",
    "ToolComposition",
    "ToolCompositionError",
    "ToolHealth",
    "ToolManifest",
    "ToolResultTrust",
    "analyze_plan",
    "simulate_plan_failures",
    "validate_tool_result",
]
