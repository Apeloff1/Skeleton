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
    validate_branch,
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
MAX_PROPOSAL_RECEIPT_BYTES = 12_000
MAX_RECEIPT_PATH_BYTES = 320

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


def _builder_path(value: object) -> str:
    path = _bounded_text(
        value,
        label="builder proposal path",
        byte_limit=MAX_RECEIPT_PATH_BYTES,
    )
    if (
        "\\" in path
        or path.startswith("/")
        or "//" in path
    ):
        raise BuilderPlaneError("invalid builder proposal path")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BuilderPlaneError("invalid builder proposal path")
    return path


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


@dataclass(frozen=True, slots=True)
class BuilderProposalReceipt:
    """Canonical attestation for one bounded feature-builder proposal."""

    version: int
    repository: str
    issue_number: int
    manifest_digest: str
    task_digest: str
    snapshot_fingerprint: str
    execution_fingerprint: str
    base_sha: str
    branch: str
    proposal_digest: str
    paths: tuple[str, ...]
    changed_lines: int
    total_bytes: int
    test_count: int
    tests_digest: str

    def __post_init__(self) -> None:
        if self.version != 1:
            raise BuilderPlaneError(
                "unsupported builder proposal receipt version"
            )
        _repository(self.repository)
        _positive_int(
            self.issue_number,
            label="builder receipt issue number",
            maximum=2_147_483_647,
        )
        for value, label in (
            (self.manifest_digest, "builder receipt manifest digest"),
            (self.task_digest, "builder receipt task digest"),
            (
                self.snapshot_fingerprint,
                "builder receipt snapshot fingerprint",
            ),
            (
                self.execution_fingerprint,
                "builder receipt execution fingerprint",
            ),
            (self.proposal_digest, "builder receipt proposal digest"),
            (self.tests_digest, "builder receipt tests digest"),
        ):
            _fingerprint(value, label=label)
        _sha(self.base_sha)
        try:
            validate_branch(
                self.branch,
                label="builder receipt branch",
            )
        except SupervisorRuntimeError as exc:
            raise BuilderPlaneError(
                "invalid builder receipt branch"
            ) from exc

        raw_paths = _strict_sequence(
            self.paths,
            label="builder receipt paths",
            maximum=MAX_BUDGET_FILES,
        )
        if not raw_paths:
            raise BuilderPlaneError(
                "builder proposal receipt requires changed paths"
            )
        normalized_paths = tuple(
            sorted(_builder_path(item) for item in raw_paths)
        )
        if len(normalized_paths) != len(set(normalized_paths)):
            raise BuilderPlaneError(
                "duplicate builder proposal receipt path"
            )
        if self.paths != normalized_paths:
            raise BuilderPlaneError(
                "builder proposal receipt paths are not canonical"
            )

        _positive_int(
            self.changed_lines,
            label="builder receipt changed lines",
            maximum=MAX_BUDGET_CHANGED_LINES,
        )
        _positive_int(
            self.total_bytes,
            label="builder receipt total bytes",
            maximum=MAX_BUDGET_TOTAL_BYTES,
        )
        _positive_int(
            self.test_count,
            label="builder receipt test count",
            maximum=MAX_BUDGET_TEST_DESCRIPTIONS,
            minimum=0,
        )

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "repository": self.repository,
            "issue_number": self.issue_number,
            "manifest_digest": self.manifest_digest,
            "task_digest": self.task_digest,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "execution_fingerprint": self.execution_fingerprint,
            "base_sha": self.base_sha,
            "branch": self.branch,
            "proposal_digest": self.proposal_digest,
            "paths": list(self.paths),
            "changed_lines": self.changed_lines,
            "total_bytes": self.total_bytes,
            "test_count": self.test_count,
            "tests_digest": self.tests_digest,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.unsigned_payload())

    def as_dict(self) -> dict[str, object]:
        payload = {
            **self.unsigned_payload(),
            "receipt_digest": self.receipt_digest,
        }
        if len(canonical_json(payload)) > MAX_PROPOSAL_RECEIPT_BYTES:
            raise BuilderPlaneError(
                "builder proposal receipt exceeds byte budget"
            )
        return payload

    @classmethod
    def from_payload(
        cls,
        value: object,
    ) -> "BuilderProposalReceipt":
        if not isinstance(value, dict):
            raise BuilderPlaneError(
                "builder proposal receipt must be an object"
            )
        expected = {
            "version",
            "repository",
            "issue_number",
            "manifest_digest",
            "task_digest",
            "snapshot_fingerprint",
            "execution_fingerprint",
            "base_sha",
            "branch",
            "proposal_digest",
            "paths",
            "changed_lines",
            "total_bytes",
            "test_count",
            "tests_digest",
            "receipt_digest",
        }
        if set(value) != expected:
            raise BuilderPlaneError(
                "builder proposal receipt shape mismatch"
            )
        raw_paths = value["paths"]
        receipt = cls(
            version=value["version"],
            repository=value["repository"],
            issue_number=value["issue_number"],
            manifest_digest=value["manifest_digest"],
            task_digest=value["task_digest"],
            snapshot_fingerprint=value["snapshot_fingerprint"],
            execution_fingerprint=value["execution_fingerprint"],
            base_sha=value["base_sha"],
            branch=value["branch"],
            proposal_digest=value["proposal_digest"],
            paths=(
                tuple(raw_paths)
                if isinstance(raw_paths, list)
                else raw_paths
            ),
            changed_lines=value["changed_lines"],
            total_bytes=value["total_bytes"],
            test_count=value["test_count"],
            tests_digest=value["tests_digest"],
        )
        if value.get("receipt_digest") != receipt.receipt_digest:
            raise BuilderPlaneError(
                "builder proposal receipt digest mismatch"
            )
        if len(canonical_json(value)) > MAX_PROPOSAL_RECEIPT_BYTES:
            raise BuilderPlaneError(
                "builder proposal receipt exceeds byte budget"
            )
        return receipt


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


def builder_worker_branch(manifest: BuilderManifest) -> str:
    """Derive a feature-builder branch from immutable base and build task.

    Generic specialists converge on worker + base SHA. Feature work has one
    additional identity dimension: the maintainer-approved task. Including the
    task digest prevents two approved issues on the same base commit from
    aliasing one autonomous feature PR.
    """
    if not isinstance(manifest, BuilderManifest):
        raise BuilderPlaneError("invalid builder manifest type")
    suffix = _canonical_digest(
        {
            "base_sha": manifest.base_sha,
            "task_digest": manifest.task_digest,
        }
    )[:16]
    try:
        return validate_branch(
            f"bot/specialist-feature-builder-{suffix}",
            label="builder worker branch",
        )
    except SupervisorRuntimeError as exc:
        raise BuilderPlaneError("invalid builder worker branch") from exc



def compile_builder_proposal_receipt(
    manifest: BuilderManifest,
    *,
    proposal_digest: str,
    branch: str,
    files: Iterable[Mapping[str, Any]],
    tests: Iterable[str],
    changed_lines: int,
) -> BuilderProposalReceipt:
    """Seal exact path/test/budget evidence for a proposed feature mutation."""
    if not isinstance(manifest, BuilderManifest):
        raise BuilderPlaneError("invalid builder manifest type")

    expected_branch = builder_worker_branch(manifest)
    if branch != expected_branch:
        raise BuilderPlaneError(
            "builder proposal receipt branch mismatch"
        )
    proposal = _fingerprint(
        proposal_digest,
        label="builder proposal digest",
    )

    try:
        file_items = tuple(files)
    except TypeError as exc:
        raise BuilderPlaneError(
            "builder proposal files must be iterable"
        ) from exc
    if (
        not file_items
        or len(file_items) > manifest.budget.max_files
    ):
        raise BuilderPlaneError(
            "builder proposal exceeds manifest file budget"
        )

    paths: list[str] = []
    total_bytes = 0
    for item in file_items:
        if not isinstance(item, Mapping):
            raise BuilderPlaneError(
                "builder proposal file must be a mapping"
            )
        if set(item) != {"path", "content"}:
            raise BuilderPlaneError(
                "builder proposal file shape mismatch"
            )
        path = _builder_path(item.get("path"))
        content = item.get("content")
        if not isinstance(content, str):
            raise BuilderPlaneError(
                "builder proposal content must be text"
            )
        paths.append(path)
        total_bytes += len(path.encode("utf-8"))
        total_bytes += len(content.encode("utf-8"))

    canonical_paths = tuple(sorted(paths))
    if len(canonical_paths) != len(set(canonical_paths)):
        raise BuilderPlaneError(
            "duplicate builder proposal path"
        )
    if total_bytes > manifest.budget.max_total_bytes:
        raise BuilderPlaneError(
            "builder proposal exceeds manifest byte budget"
        )

    changed = _positive_int(
        changed_lines,
        label="builder proposal changed lines",
        maximum=manifest.budget.max_changed_lines,
    )

    try:
        raw_tests = tuple(tests)
    except TypeError as exc:
        raise BuilderPlaneError(
            "builder proposal tests must be iterable"
        ) from exc
    if len(raw_tests) > manifest.budget.max_test_descriptions:
        raise BuilderPlaneError(
            "builder proposal exceeds manifest test budget"
        )
    normalized_tests = tuple(
        _bounded_text(
            item,
            label="builder proposal test description",
            byte_limit=MAX_ACCEPTANCE_TEXT_BYTES,
        )
        for item in raw_tests
    )

    return BuilderProposalReceipt(
        version=1,
        repository=manifest.repository,
        issue_number=manifest.issue_number,
        manifest_digest=manifest.manifest_digest,
        task_digest=manifest.task_digest,
        snapshot_fingerprint=manifest.snapshot_fingerprint,
        execution_fingerprint=manifest.execution_fingerprint,
        base_sha=manifest.base_sha,
        branch=expected_branch,
        proposal_digest=proposal,
        paths=canonical_paths,
        changed_lines=changed,
        total_bytes=total_bytes,
        test_count=len(normalized_tests),
        tests_digest=_canonical_digest(list(normalized_tests)),
    )


def validate_builder_proposal_receipt(
    receipt: BuilderProposalReceipt,
    manifest: BuilderManifest,
    *,
    evidence: Mapping[str, Any] | None = None,
) -> None:
    """Verify receipt custody and manifest budgets at the Secretary boundary."""
    if not isinstance(receipt, BuilderProposalReceipt):
        raise BuilderPlaneError(
            "invalid builder proposal receipt type"
        )
    if not isinstance(manifest, BuilderManifest):
        raise BuilderPlaneError("invalid builder manifest type")

    expected = {
        "repository": manifest.repository,
        "issue_number": manifest.issue_number,
        "manifest_digest": manifest.manifest_digest,
        "task_digest": manifest.task_digest,
        "snapshot_fingerprint": manifest.snapshot_fingerprint,
        "execution_fingerprint": manifest.execution_fingerprint,
        "base_sha": manifest.base_sha,
        "branch": builder_worker_branch(manifest),
    }
    for field, expected_value in expected.items():
        if getattr(receipt, field) != expected_value:
            raise BuilderPlaneError(
                f"builder proposal receipt {field} mismatch"
            )

    if len(receipt.paths) > manifest.budget.max_files:
        raise BuilderPlaneError(
            "builder proposal receipt exceeds file budget"
        )
    if receipt.changed_lines > manifest.budget.max_changed_lines:
        raise BuilderPlaneError(
            "builder proposal receipt exceeds changed-line budget"
        )
    if receipt.total_bytes > manifest.budget.max_total_bytes:
        raise BuilderPlaneError(
            "builder proposal receipt exceeds byte budget"
        )
    if receipt.test_count > manifest.budget.max_test_descriptions:
        raise BuilderPlaneError(
            "builder proposal receipt exceeds test budget"
        )

    if evidence is None:
        return
    if not isinstance(evidence, Mapping):
        raise BuilderPlaneError(
            "builder proposal evidence must be a mapping"
        )
    evidence_expected = {
        "branch": receipt.branch,
        "proposal_digest": receipt.proposal_digest,
        "changed_lines": receipt.changed_lines,
        "base_sha": receipt.base_sha,
        "supervisor_snapshot_fingerprint": (
            receipt.snapshot_fingerprint
        ),
        "execution_fingerprint": receipt.execution_fingerprint,
        "build_issue_number": receipt.issue_number,
        "build_task_digest": receipt.task_digest,
        "builder_manifest_digest": receipt.manifest_digest,
    }
    for field, expected_value in evidence_expected.items():
        if evidence.get(field) != expected_value:
            raise BuilderPlaneError(
                f"builder proposal evidence {field} mismatch"
            )


def validate_builder_worker_evidence(
    evidence: Mapping[str, Any],
    manifest: BuilderManifest,
) -> None:
    """Bind feature-builder evidence to exact task, branch, and custody."""
    if not isinstance(evidence, Mapping):
        raise BuilderPlaneError("builder worker evidence must be a mapping")
    if not isinstance(manifest, BuilderManifest):
        raise BuilderPlaneError("invalid builder manifest type")

    status = evidence.get("status")
    if status == "no-change":
        if evidence.get("bot") != "feature-builder":
            raise BuilderPlaneError(
                "builder no-change evidence came from a non-builder worker"
            )
        return
    if status not in {
        "pull-request-created",
        "pull-request-updated",
        "existing-pr",
    }:
        raise BuilderPlaneError("builder worker evidence status is not admitted")
    if evidence.get("bot") != "feature-builder":
        raise BuilderPlaneError(
            "builder mutation evidence came from a non-builder worker"
        )

    expected = {
        "branch": builder_worker_branch(manifest),
        "build_issue_number": manifest.issue_number,
        "build_task_digest": manifest.task_digest,
        "supervisor_snapshot_fingerprint": manifest.snapshot_fingerprint,
    }
    for field, expected_value in expected.items():
        if evidence.get(field) != expected_value:
            raise BuilderPlaneError(
                f"builder worker evidence {field} mismatch"
            )

    if status == "existing-pr":
        return

    created_expected = {
        "builder_manifest_digest": manifest.manifest_digest,
        "base_sha": manifest.base_sha,
        "execution_fingerprint": manifest.execution_fingerprint,
    }
    for field, expected_value in created_expected.items():
        if evidence.get(field) != expected_value:
            raise BuilderPlaneError(
                f"builder worker evidence {field} mismatch"
            )

    try:
        receipt = BuilderProposalReceipt.from_payload(
            evidence.get("builder_proposal_receipt")
        )
        validate_builder_proposal_receipt(
            receipt,
            manifest,
            evidence=evidence,
        )
    except BuilderPlaneError as exc:
        raise BuilderPlaneError(
            "builder worker proposal receipt is invalid"
        ) from exc


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
