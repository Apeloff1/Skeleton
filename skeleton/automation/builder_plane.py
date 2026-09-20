"""Deterministic Builder Plane for authorized autonomous repository work.

The Builder Plane is deliberately *not* another privileged actor. It converts
one already-admitted :class:`BuildAuthorization` into a bounded, canonical
manifest that can be transported from Secretary to the feature-builder worker.

Authority remains one-way::

    Supervisor (observe/plan)
        -> Secretary (admit/revalidate)
        -> Builder Plane (compile inert manifest)
        -> Worker (propose bounded mutation)
        -> ordinary pull request / CI

The manifest contains no command, executable, module, token, workflow
permission, branch override, or arbitrary path. It binds an approved task to
the exact repository snapshot and immutable workflow execution, constrains the
work budget, orders the build phases, and states the evidence required before a
proposal may be considered complete.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .build_authority import BuildAuthorization
from .supervisor_runtime import (
    ExecutionIdentity,
    SupervisorRuntimeError,
    canonical_json,
    validate_fingerprint,
    validate_repository,
    validate_sha,
)


MAX_MANIFEST_BYTES = 32_000
MAX_MANIFEST_B64_BYTES = 48_000
MAX_STAGES = 8
MAX_STAGE_TEXT_BYTES = 1_200
MAX_EVIDENCE_ITEMS = 8
MAX_EVIDENCE_TEXT_BYTES = 400
MAX_SIGNAL_ITEMS = 12
MAX_SIGNAL_BYTES = 80
MAX_ACCEPTANCE_ITEMS = 12
MAX_ACCEPTANCE_TEXT_BYTES = 600
MAX_BUDGET_FILES = 16
MAX_BUDGET_CHANGED_LINES = 1_200
MAX_BUDGET_TOTAL_BYTES = 240_000
MAX_BUDGET_TEST_DESCRIPTIONS = 12

_STAGE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
_STAGE_KIND_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_SIGNAL_RE = re.compile(r"^[a-z][a-z0-9-]{0,47}$")

_SIGNAL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("api-contract", ("api", "endpoint", "schema", "openapi", "contract")),
    ("documentation", ("docs", "documentation", "readme", "guide")),
    ("integration", ("integration", "cross-subsystem", "e2e", "arm64")),
    ("performance", ("performance", "latency", "benchmark", "throughput", "slow")),
    ("regression", ("regression", "bug", "failure", "broken", "fix")),
    ("testing", ("test", "coverage", "pytest", "unit test", "integration test")),
    ("observability", ("metric", "logging", "telemetry", "trace", "observability")),
    ("resilience", ("retry", "recovery", "resilience", "fault", "fallback")),
    ("data-model", ("model", "schema", "serialization", "payload", "state")),
    ("cli", ("cli", "command line", "developer command", "terminal")),
)

_BASE_ACCEPTANCE = (
    "Requested behavior is implemented without expanding repository authority.",
    "Generated changes remain inside the feature-builder registry policy.",
    "No workflow, credential, authorization, deployment, or security-gate bypass is introduced.",
    "Regression coverage is added or updated for behavior changed by the proposal.",
    "The proposal remains directly based on the immutable admitted base commit.",
    "Worker evidence is bound to the Supervisor snapshot and execution fingerprint.",
)

_SIGNAL_ACCEPTANCE: Mapping[str, str] = {
    "api-contract": "API or schema changes preserve explicit compatibility and contract coverage.",
    "documentation": "User-facing behavior changes include synchronized documentation where relevant.",
    "integration": "Cross-subsystem behavior is covered by a focused integration contract.",
    "performance": "Performance work preserves deterministic correctness and states its measurement target.",
    "regression": "The original failure mode is represented by a focused regression test.",
    "testing": "Test changes assert behavior rather than only implementation details.",
    "observability": "New telemetry remains bounded and avoids secret-bearing payloads.",
    "resilience": "Recovery behavior is bounded, fail-closed where appropriate, and regression-tested.",
    "data-model": "Serialized or persistent shapes have deterministic validation and migration semantics.",
    "cli": "CLI behavior has stable argument validation and deterministic exit semantics.",
}


class BuilderPlaneError(ValueError):
    """A Builder Plane manifest or custody invariant was invalid."""


def _bounded_text(
    value: object,
    *,
    label: str,
    byte_limit: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise BuilderPlaneError(f"{label} must be text")
    clean = value.strip()
    if not clean and not allow_empty:
        raise BuilderPlaneError(f"{label} must not be empty")
    if "\x00" in clean:
        raise BuilderPlaneError(f"{label} contains NUL")
    if len(clean.encode("utf-8")) > byte_limit:
        raise BuilderPlaneError(f"{label} exceeds byte budget")
    return clean


def _positive_int(
    value: object,
    *,
    label: str,
    maximum: int,
    minimum: int = 1,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise BuilderPlaneError(f"invalid {label}")
    return value


def _canonical_digest(value: object) -> str:
    try:
        return hashlib.sha256(canonical_json(value)).hexdigest()
    except SupervisorRuntimeError as exc:
        raise BuilderPlaneError("builder payload is not canonical JSON") from exc


def _fingerprint(value: object, *, label: str) -> str:
    try:
        return validate_fingerprint(value)
    except SupervisorRuntimeError as exc:
        raise BuilderPlaneError(f"invalid {label}") from exc


def _repository(value: object) -> str:
    try:
        return validate_repository(value)
    except SupervisorRuntimeError as exc:
        raise BuilderPlaneError("invalid builder repository") from exc


def _sha(value: object) -> str:
    try:
        return validate_sha(value, label="builder base SHA")
    except SupervisorRuntimeError as exc:
        raise BuilderPlaneError("invalid builder base SHA") from exc


def _unique_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuilderPlaneError(
                f"duplicate builder manifest field: {key}"
            )
        result[key] = value
    return result


def _strict_sequence(
    value: object,
    *,
    label: str,
    maximum: int,
) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise BuilderPlaneError(f"{label} must be a sequence")
    if len(value) > maximum:
        raise BuilderPlaneError(f"{label} exceeds item budget")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class BuilderBudget:
    """Hard proposal budget inherited by the authorized feature builder."""

    max_files: int = 8
    max_changed_lines: int = MAX_BUDGET_CHANGED_LINES
    max_total_bytes: int = MAX_BUDGET_TOTAL_BYTES
    max_test_descriptions: int = MAX_BUDGET_TEST_DESCRIPTIONS

    def __post_init__(self) -> None:
        _positive_int(
            self.max_files,
            label="builder max files",
            maximum=MAX_BUDGET_FILES,
        )
        _positive_int(
            self.max_changed_lines,
            label="builder max changed lines",
            maximum=MAX_BUDGET_CHANGED_LINES,
        )
        _positive_int(
            self.max_total_bytes,
            label="builder max total bytes",
            maximum=MAX_BUDGET_TOTAL_BYTES,
        )
        _positive_int(
            self.max_test_descriptions,
            label="builder max test descriptions",
            maximum=MAX_BUDGET_TEST_DESCRIPTIONS,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "max_files": self.max_files,
            "max_changed_lines": self.max_changed_lines,
            "max_total_bytes": self.max_total_bytes,
            "max_test_descriptions": self.max_test_descriptions,
        }

    @classmethod
    def from_payload(cls, value: object) -> "BuilderBudget":
        if not isinstance(value, dict):
            raise BuilderPlaneError("builder budget must be an object")
        expected = {
            "max_files",
            "max_changed_lines",
            "max_total_bytes",
            "max_test_descriptions",
        }
        if set(value) != expected:
            raise BuilderPlaneError("builder budget shape mismatch")
        return cls(
            max_files=value["max_files"],
            max_changed_lines=value["max_changed_lines"],
            max_total_bytes=value["max_total_bytes"],
            max_test_descriptions=value["max_test_descriptions"],
        )


@dataclass(frozen=True, slots=True)
class BuilderStage:
    """One inert phase in the deterministic Builder Plane DAG."""

    ordinal: int
    stage_id: str
    kind: str
    objective: str
    depends_on: tuple[str, ...]
    required_evidence: tuple[str, ...]
    mutation_allowed: bool = False

    def __post_init__(self) -> None:
        _positive_int(
            self.ordinal,
            label="builder stage ordinal",
            maximum=MAX_STAGES,
        )
        stage_id = _bounded_text(
            self.stage_id,
            label="builder stage id",
            byte_limit=64,
        )
        kind = _bounded_text(
            self.kind,
            label="builder stage kind",
            byte_limit=48,
        )
        if _STAGE_ID_RE.fullmatch(stage_id) is None:
            raise BuilderPlaneError("invalid builder stage id")
        if _STAGE_KIND_RE.fullmatch(kind) is None:
            raise BuilderPlaneError("invalid builder stage kind")
        _bounded_text(
            self.objective,
            label="builder stage objective",
            byte_limit=MAX_STAGE_TEXT_BYTES,
        )
        dependencies = _strict_sequence(
            self.depends_on,
            label="builder stage dependencies",
            maximum=MAX_STAGES,
        )
        normalized_dependencies: list[str] = []
        for item in dependencies:
            dep = _bounded_text(
                item,
                label="builder stage dependency",
                byte_limit=64,
            )
            if _STAGE_ID_RE.fullmatch(dep) is None:
                raise BuilderPlaneError("invalid builder stage dependency")
            normalized_dependencies.append(dep)
        if len(normalized_dependencies) != len(set(normalized_dependencies)):
            raise BuilderPlaneError("duplicate builder stage dependency")
        evidence = _strict_sequence(
            self.required_evidence,
            label="builder stage evidence",
            maximum=MAX_EVIDENCE_ITEMS,
        )
        normalized_evidence = tuple(
            _bounded_text(
                item,
                label="builder stage evidence item",
                byte_limit=MAX_EVIDENCE_TEXT_BYTES,
            )
            for item in evidence
        )
        if self.depends_on != tuple(normalized_dependencies):
            raise BuilderPlaneError("builder stage dependencies are not normalized")
        if self.required_evidence != normalized_evidence:
            raise BuilderPlaneError("builder stage evidence is not normalized")
        if not isinstance(self.mutation_allowed, bool):
            raise BuilderPlaneError("builder stage mutation flag must be boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "stage_id": self.stage_id,
            "kind": self.kind,
            "objective": self.objective,
            "depends_on": list(self.depends_on),
            "required_evidence": list(self.required_evidence),
            "mutation_allowed": self.mutation_allowed,
        }

    @classmethod
    def from_payload(cls, value: object) -> "BuilderStage":
        if not isinstance(value, dict):
            raise BuilderPlaneError("builder stage must be an object")
        expected = {
            "ordinal",
            "stage_id",
            "kind",
            "objective",
            "depends_on",
            "required_evidence",
            "mutation_allowed",
        }
        if set(value) != expected:
            raise BuilderPlaneError("builder stage shape mismatch")
        depends_on = value["depends_on"]
        evidence = value["required_evidence"]
        return cls(
            ordinal=value["ordinal"],
            stage_id=value["stage_id"],
            kind=value["kind"],
            objective=value["objective"],
            depends_on=tuple(depends_on) if isinstance(depends_on, list) else depends_on,
            required_evidence=tuple(evidence) if isinstance(evidence, list) else evidence,
            mutation_allowed=value["mutation_allowed"],
        )


@dataclass(frozen=True, slots=True)
class BuilderManifest:
    """Canonical build graph bound to exact authority and execution custody."""

    version: int
    repository: str
    issue_number: int
    issue_digest: str
    task_digest: str
    snapshot_fingerprint: str
    execution_fingerprint: str
    base_sha: str
    budget: BuilderBudget
    stages: tuple[BuilderStage, ...]
    signals: tuple[str, ...]
    acceptance: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version != 1:
            raise BuilderPlaneError("unsupported builder manifest version")
        _repository(self.repository)
        _positive_int(
            self.issue_number,
            label="builder issue number",
            maximum=2_147_483_647,
        )
        _fingerprint(self.issue_digest, label="builder issue digest")
        _fingerprint(self.task_digest, label="builder task digest")
        _fingerprint(
            self.snapshot_fingerprint,
            label="builder snapshot fingerprint",
        )
        _fingerprint(
            self.execution_fingerprint,
            label="builder execution fingerprint",
        )
        _sha(self.base_sha)
        if not isinstance(self.budget, BuilderBudget):
            raise BuilderPlaneError("builder budget has invalid type")
        stages = _strict_sequence(
            self.stages,
            label="builder stages",
            maximum=MAX_STAGES,
        )
        if not stages:
            raise BuilderPlaneError("builder manifest requires stages")
        for stage in stages:
            if not isinstance(stage, BuilderStage):
                raise BuilderPlaneError("builder stage has invalid type")
        ordinals = [stage.ordinal for stage in stages]
        if ordinals != list(range(1, len(stages) + 1)):
            raise BuilderPlaneError("builder stage ordinals are not contiguous")
        ids = [stage.stage_id for stage in stages]
        if len(ids) != len(set(ids)):
            raise BuilderPlaneError("duplicate builder stage id")
        seen: set[str] = set()
        for stage in stages:
            if any(dep not in seen for dep in stage.depends_on):
                raise BuilderPlaneError(
                    "builder stage dependency must reference an earlier stage"
                )
            seen.add(stage.stage_id)
        mutation_stages = [stage for stage in stages if stage.mutation_allowed]
        if len(mutation_stages) != 1 or mutation_stages[0].kind != "implement":
            raise BuilderPlaneError(
                "builder manifest must contain exactly one implement mutation stage"
            )
        signals = _strict_sequence(
            self.signals,
            label="builder signals",
            maximum=MAX_SIGNAL_ITEMS,
        )
        normalized_signals: list[str] = []
        for item in signals:
            signal = _bounded_text(
                item,
                label="builder signal",
                byte_limit=MAX_SIGNAL_BYTES,
            )
            if _SIGNAL_RE.fullmatch(signal) is None:
                raise BuilderPlaneError("invalid builder signal")
            normalized_signals.append(signal)
        if tuple(sorted(set(normalized_signals))) != self.signals:
            raise BuilderPlaneError("builder signals are not canonical")
        acceptance = _strict_sequence(
            self.acceptance,
            label="builder acceptance",
            maximum=MAX_ACCEPTANCE_ITEMS,
        )
        normalized_acceptance = tuple(
            _bounded_text(
                item,
                label="builder acceptance item",
                byte_limit=MAX_ACCEPTANCE_TEXT_BYTES,
            )
            for item in acceptance
        )
        if self.acceptance != normalized_acceptance:
            raise BuilderPlaneError("builder acceptance is not normalized")
        if len(set(normalized_acceptance)) != len(normalized_acceptance):
            raise BuilderPlaneError("duplicate builder acceptance item")

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "repository": self.repository,
            "issue_number": self.issue_number,
            "issue_digest": self.issue_digest,
            "task_digest": self.task_digest,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "execution_fingerprint": self.execution_fingerprint,
            "base_sha": self.base_sha,
            "budget": self.budget.as_dict(),
            "stages": [stage.as_dict() for stage in self.stages],
            "signals": list(self.signals),
            "acceptance": list(self.acceptance),
        }

    @property
    def manifest_digest(self) -> str:
        return _canonical_digest(self.unsigned_payload())

    def as_dict(self) -> dict[str, object]:
        return {
            **self.unsigned_payload(),
            "manifest_digest": self.manifest_digest,
        }

    def to_base64(self) -> str:
        raw = canonical_json(self.as_dict())
        if len(raw) > MAX_MANIFEST_BYTES:
            raise BuilderPlaneError("builder manifest exceeds byte budget")
        encoded = base64.b64encode(raw).decode("ascii")
        if len(encoded) > MAX_MANIFEST_B64_BYTES:
            raise BuilderPlaneError("encoded builder manifest exceeds byte budget")
        return encoded

    @classmethod
    def from_payload(cls, value: object) -> "BuilderManifest":
        if not isinstance(value, dict):
            raise BuilderPlaneError("builder manifest must be an object")
        expected = {
            "version",
            "repository",
            "issue_number",
            "issue_digest",
            "task_digest",
            "snapshot_fingerprint",
            "execution_fingerprint",
            "base_sha",
            "budget",
            "stages",
            "signals",
            "acceptance",
            "manifest_digest",
        }
        if set(value) != expected:
            raise BuilderPlaneError("builder manifest shape mismatch")
        raw_stages = value["stages"]
        if not isinstance(raw_stages, list):
            raise BuilderPlaneError("builder stages must be a list")
        raw_signals = value["signals"]
        raw_acceptance = value["acceptance"]
        manifest = cls(
            version=value["version"],
            repository=value["repository"],
            issue_number=value["issue_number"],
            issue_digest=value["issue_digest"],
            task_digest=value["task_digest"],
            snapshot_fingerprint=value["snapshot_fingerprint"],
            execution_fingerprint=value["execution_fingerprint"],
            base_sha=value["base_sha"],
            budget=BuilderBudget.from_payload(value["budget"]),
            stages=tuple(BuilderStage.from_payload(item) for item in raw_stages),
            signals=tuple(raw_signals) if isinstance(raw_signals, list) else raw_signals,
            acceptance=(
                tuple(raw_acceptance)
                if isinstance(raw_acceptance, list)
                else raw_acceptance
            ),
        )
        if value.get("manifest_digest") != manifest.manifest_digest:
            raise BuilderPlaneError("builder manifest digest mismatch")
        return manifest

    @classmethod
    def from_base64(cls, encoded: str) -> "BuilderManifest":
        if (
            not isinstance(encoded, str)
            or not encoded
            or len(encoded) > MAX_MANIFEST_B64_BYTES
        ):
            raise BuilderPlaneError("invalid encoded builder manifest size")
        try:
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > MAX_MANIFEST_BYTES:
                raise BuilderPlaneError("builder manifest exceeds byte budget")
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
            )
        except (
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise BuilderPlaneError("invalid encoded builder manifest") from exc
        return cls.from_payload(value)


def _derive_signals(authorization: BuildAuthorization) -> tuple[str, ...]:
    haystack = " ".join(
        (
            authorization.title.casefold(),
            authorization.body.casefold(),
            " ".join(authorization.labels),
        )
    )
    selected: set[str] = set()
    for signal, keywords in _SIGNAL_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            selected.add(signal)
    if not selected:
        selected.add("general-feature")
    return tuple(sorted(selected))


def _derive_acceptance(signals: Iterable[str]) -> tuple[str, ...]:
    result = list(_BASE_ACCEPTANCE)
    for signal in signals:
        extra = _SIGNAL_ACCEPTANCE.get(signal)
        if extra and extra not in result:
            result.append(extra)
    return tuple(result[:MAX_ACCEPTANCE_ITEMS])


def _default_budget(signals: Iterable[str]) -> BuilderBudget:
    signal_set = set(signals)
    max_files = 8
    if "integration" in signal_set or "api-contract" in signal_set:
        max_files = 10
    if "documentation" in signal_set and len(signal_set) > 1:
        max_files = min(MAX_BUDGET_FILES, max_files + 1)
    return BuilderBudget(max_files=max_files)


def _stages(signals: tuple[str, ...]) -> tuple[BuilderStage, ...]:
    signal_summary = ", ".join(signals)
    return (
        BuilderStage(
            ordinal=1,
            stage_id="inspect",
            kind="inspect",
            objective=(
                "Establish the smallest repository surface that implements the "
                f"authorized task; planning signals: {signal_summary}."
            ),
            depends_on=(),
            required_evidence=(
                "Relevant existing source and regression surface identified.",
                "No control-plane permission expansion is required.",
            ),
            mutation_allowed=False,
        ),
        BuilderStage(
            ordinal=2,
            stage_id="design",
            kind="design",
            objective=(
                "Choose the smallest deterministic implementation compatible "
                "with existing public contracts and repository architecture."
            ),
            depends_on=("inspect",),
            required_evidence=(
                "Behavioral contract is stated before mutation.",
                "Failure and rollback semantics are explicit where applicable.",
            ),
            mutation_allowed=False,
        ),
        BuilderStage(
            ordinal=3,
            stage_id="implement",
            kind="implement",
            objective=(
                "Produce only bounded source, test, or documentation changes "
                "needed for the authorized issue."
            ),
            depends_on=("design",),
            required_evidence=(
                "All proposed paths pass the registered feature-builder policy.",
                "Mutation remains inside the manifest file/line/byte budget.",
            ),
            mutation_allowed=True,
        ),
        BuilderStage(
            ordinal=4,
            stage_id="regression",
            kind="regression",
            objective=(
                "Bind the implementation to focused behavioral regression "
                "coverage without executing model-supplied commands."
            ),
            depends_on=("implement",),
            required_evidence=(
                "Changed behavior has focused regression coverage or a stated no-test rationale.",
                "Tests do not weaken existing assertions or safety contracts.",
            ),
            mutation_allowed=False,
        ),
        BuilderStage(
            ordinal=5,
            stage_id="validate",
            kind="validate",
            objective=(
                "Validate proposal structure, custody, mutation budget, and "
                "compatibility using repository-owned validation paths."
            ),
            depends_on=("regression",),
            required_evidence=(
                "Proposal digest is deterministic.",
                "Immutable base and remote default branch remain unchanged.",
            ),
            mutation_allowed=False,
        ),
        BuilderStage(
            ordinal=6,
            stage_id="evidence",
            kind="evidence",
            objective=(
                "Emit bounded evidence for the ordinary pull request and CI "
                "without granting merge or workflow authority."
            ),
            depends_on=("validate",),
            required_evidence=(
                "Worker result is bound to execution and snapshot custody.",
                "Publication uses the deterministic worker branch namespace.",
            ),
            mutation_allowed=False,
        ),
    )


def compile_builder_manifest(
    authorization: BuildAuthorization,
    *,
    snapshot_fingerprint: str,
    execution: ExecutionIdentity,
) -> BuilderManifest:
    """Compile one authorized issue into a deterministic inert build graph."""
    if not isinstance(authorization, BuildAuthorization):
        raise BuilderPlaneError("builder requires BuildAuthorization")
    if authorization.repository != execution.repository:
        raise BuilderPlaneError("builder authorization repository mismatch")
    snapshot = _fingerprint(
        snapshot_fingerprint,
        label="builder snapshot fingerprint",
    )
    signals = _derive_signals(authorization)
    return BuilderManifest(
        version=1,
        repository=authorization.repository,
        issue_number=authorization.issue_number,
        issue_digest=authorization.issue_digest,
        task_digest=authorization.task_digest,
        snapshot_fingerprint=snapshot,
        execution_fingerprint=execution.fingerprint,
        base_sha=execution.base_sha,
        budget=_default_budget(signals),
        stages=_stages(signals),
        signals=signals,
        acceptance=_derive_acceptance(signals),
    )


def validate_builder_custody(
    manifest: BuilderManifest,
    *,
    authorization: BuildAuthorization,
    snapshot_fingerprint: str,
    execution: ExecutionIdentity,
) -> BuilderManifest:
    """Require a manifest to match exact authority, snapshot, and execution."""
    if not isinstance(manifest, BuilderManifest):
        raise BuilderPlaneError("invalid builder manifest type")
    if not isinstance(authorization, BuildAuthorization):
        raise BuilderPlaneError("invalid builder authorization type")
    expected_snapshot = _fingerprint(
        snapshot_fingerprint,
        label="builder snapshot fingerprint",
    )
    checks = (
        (manifest.repository, authorization.repository, "repository"),
        (manifest.repository, execution.repository, "execution repository"),
        (manifest.issue_number, authorization.issue_number, "issue number"),
        (manifest.issue_digest, authorization.issue_digest, "issue digest"),
        (manifest.task_digest, authorization.task_digest, "task digest"),
        (
            manifest.snapshot_fingerprint,
            expected_snapshot,
            "snapshot fingerprint",
        ),
        (
            manifest.execution_fingerprint,
            execution.fingerprint,
            "execution fingerprint",
        ),
        (manifest.base_sha, execution.base_sha, "base SHA"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise BuilderPlaneError(f"builder custody {label} mismatch")

    deterministic = compile_builder_manifest(
        authorization,
        snapshot_fingerprint=expected_snapshot,
        execution=execution,
    )
    if manifest.as_dict() != deterministic.as_dict():
        raise BuilderPlaneError("builder manifest differs from deterministic compilation")
    return manifest


def validate_builder_worker_evidence(
    evidence: Mapping[str, Any],
    manifest: BuilderManifest,
) -> None:
    """Bind a newly published feature proposal to its exact Builder manifest."""
    if not isinstance(evidence, Mapping):
        raise BuilderPlaneError("builder worker evidence must be a mapping")
    if not isinstance(manifest, BuilderManifest):
        raise BuilderPlaneError("invalid builder manifest type")
    if evidence.get("status") != "pull-request-created":
        return
    if evidence.get("bot") != "feature-builder":
        raise BuilderPlaneError(
            "builder mutation evidence came from a non-builder worker"
        )
    supplied = evidence.get("builder_manifest_digest")
    if supplied != manifest.manifest_digest:
        raise BuilderPlaneError(
            "builder worker evidence manifest digest mismatch"
        )


def manifest_prompt_fragment(manifest: BuilderManifest) -> str:
    """Render bounded inert manifest data for the feature-builder model prompt."""
    payload = {
        "manifest_digest": manifest.manifest_digest,
        "issue_number": manifest.issue_number,
        "signals": list(manifest.signals),
        "budget": manifest.budget.as_dict(),
        "stages": [
            {
                "ordinal": stage.ordinal,
                "id": stage.stage_id,
                "kind": stage.kind,
                "objective": stage.objective,
                "mutation_allowed": stage.mutation_allowed,
                "required_evidence": list(stage.required_evidence),
            }
            for stage in manifest.stages
        ],
        "acceptance": list(manifest.acceptance),
    }
    raw = canonical_json(payload)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise BuilderPlaneError("builder prompt fragment exceeds byte budget")
    return raw.decode("utf-8")


__all__ = [
    "BuilderBudget",
    "BuilderManifest",
    "BuilderPlaneError",
    "BuilderStage",
    "MAX_BUDGET_CHANGED_LINES",
    "MAX_BUDGET_FILES",
    "MAX_BUDGET_TEST_DESCRIPTIONS",
    "MAX_BUDGET_TOTAL_BYTES",
    "MAX_MANIFEST_BYTES",
    "compile_builder_manifest",
    "manifest_prompt_fragment",
    "validate_builder_custody",
    "validate_builder_worker_evidence",
]
