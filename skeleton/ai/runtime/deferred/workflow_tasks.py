"""Workflow language/versioning and task semantics VOL-307..312."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import sha256_json


@dataclass(frozen=True, slots=True)
class DSLVersion:
    major: int
    minor: int


@dataclass(frozen=True, slots=True)
class WorkflowSource:
    source_id: str
    version: DSLVersion
    text: str
    declared_authority: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DSLDiagnostic:
    code: str
    message: str
    position: int | None


def validate_source(
    source: WorkflowSource,
    allowed_authority: tuple[str, ...],
) -> tuple[DSLDiagnostic, ...]:
    diagnostics: list[DSLDiagnostic] = []
    if not source.source_id or not source.text:
        diagnostics.append(
            DSLDiagnostic(
                "DSL_IDENTITY",
                "source identity/text required",
                None,
            )
        )
    if source.version.major != 1 or source.version.minor < 0:
        diagnostics.append(
            DSLDiagnostic("DSL_VERSION", "unsupported DSL major", None)
        )
    extra = set(source.declared_authority) - set(allowed_authority)
    if extra:
        diagnostics.append(
            DSLDiagnostic(
                "DSL_AUTHORITY",
                "undeclared privilege: " + ",".join(sorted(extra)),
                None,
            )
        )
    if "\x00" in source.text:
        diagnostics.append(
            DSLDiagnostic(
                "DSL_SYNTAX",
                "NUL is not valid source",
                source.text.index("\x00"),
            )
        )
    return tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class WorkflowLink:
    node_id: str
    capability: str
    compensation: str | None


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    source_id: str
    source_digest: str
    version: DSLVersion
    links: tuple[WorkflowLink, ...]

    @property
    def identity(self) -> str:
        return sha256_json(
            {
                "source": self.source_digest,
                "version": (self.version.major, self.version.minor),
                "links": [
                    (link.node_id, link.capability, link.compensation)
                    for link in self.links
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class CompileResult:
    workflow: CompiledWorkflow | None
    diagnostics: tuple[DSLDiagnostic, ...]


def compile_workflow(
    source: WorkflowSource,
    links: tuple[WorkflowLink, ...],
    available_capabilities: tuple[str, ...],
    edges: tuple[tuple[str, str], ...],
) -> CompileResult:
    diagnostics = list(validate_source(source, source.declared_authority))
    if (
        len({link.node_id for link in links}) != len(links)
        or any(not link.node_id or not link.capability for link in links)
    ):
        diagnostics.append(
            DSLDiagnostic(
                "LINK_IDENTITY",
                "unique link identity required",
                None,
            )
        )

    nodes = {link.node_id for link in links}
    for link in links:
        if link.capability not in available_capabilities:
            diagnostics.append(
                DSLDiagnostic(
                    "MISSING_CAPABILITY",
                    link.capability,
                    None,
                )
            )
        if link.compensation and link.compensation not in nodes:
            diagnostics.append(
                DSLDiagnostic(
                    "INVALID_COMPENSATION",
                    link.node_id,
                    None,
                )
            )

    graph = {node: [] for node in nodes}
    if len(set(edges)) != len(edges):
        diagnostics.append(
            DSLDiagnostic(
                "DUPLICATE_EDGE",
                "duplicate workflow edge",
                None,
            )
        )
    for source_node, target_node in edges:
        if (
            not source_node
            or not target_node
            or source_node == target_node
            or source_node not in graph
            or target_node not in graph
        ):
            diagnostics.append(
                DSLDiagnostic(
                    "INVALID_EDGE",
                    f"{source_node}->{target_node}",
                    None,
                )
            )
        else:
            graph[source_node].append(target_node)

    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in done:
            return False
        visiting.add(node)
        if any(visit(target) for target in graph.get(node, ())):
            return True
        visiting.remove(node)
        done.add(node)
        return False

    if any(visit(node) for node in nodes):
        diagnostics.append(
            DSLDiagnostic("CYCLE", "workflow contains cycle", None)
        )
    if diagnostics:
        return CompileResult(None, tuple(diagnostics))

    source_digest = sha256_json(
        {
            "text": source.text,
            "version": (source.version.major, source.version.minor),
        }
    )
    return CompileResult(
        CompiledWorkflow(
            source.source_id,
            source_digest,
            source.version,
            tuple(sorted(links, key=lambda link: link.node_id)),
        ),
        (),
    )


@dataclass(frozen=True, slots=True)
class WorkflowVersion:
    workflow_id: str
    version: int
    ir_digest: str


@dataclass(frozen=True, slots=True)
class WorkflowCompatibility:
    source_version: int
    target_version: int
    compatible: bool


@dataclass(frozen=True, slots=True)
class WorkflowBinding:
    run_id: str
    workflow: WorkflowVersion


def rebind(
    binding: WorkflowBinding,
    target: WorkflowVersion,
    compatibility: WorkflowCompatibility,
    *,
    explicit_migration: bool,
) -> WorkflowBinding:
    if (
        not all(
            (
                binding.run_id,
                binding.workflow.workflow_id,
                binding.workflow.ir_digest,
                target.workflow_id,
                target.ir_digest,
            )
        )
        or binding.workflow.workflow_id != target.workflow_id
    ):
        raise ValueError("workflow identity mismatch")
    if target.version < 0 or binding.workflow.version < 0:
        raise ValueError("invalid workflow version")
    if not explicit_migration:
        return binding
    if (
        binding.workflow.version != compatibility.source_version
        or target.version != compatibility.target_version
        or not compatibility.compatible
    ):
        raise ValueError("incompatible workflow migration")
    return WorkflowBinding(binding.run_id, target)


@dataclass(frozen=True, slots=True)
class StateMapping:
    source_key: str
    target_key: str
    irreversible: bool = False


@dataclass(frozen=True, slots=True)
class WorkflowMigration:
    migration_id: str
    source_version: int
    target_version: int
    mappings: tuple[StateMapping, ...]
    rollback_declared: bool


@dataclass(frozen=True, slots=True)
class WorkflowMigrationReceipt:
    migration_id: str
    migrated: bool
    pinned: bool
    restarted: bool


def migrate(
    migration: WorkflowMigration,
    *,
    compatible: bool,
    terminate_and_restart: bool = False,
) -> WorkflowMigrationReceipt:
    if (
        not migration.migration_id
        or migration.source_version < 0
        or migration.target_version < 0
        or migration.source_version == migration.target_version
    ):
        raise ValueError("valid migration identity required")
    if (
        len({item.source_key for item in migration.mappings})
        != len(migration.mappings)
        or len({item.target_key for item in migration.mappings})
        != len(migration.mappings)
        or any(
            not item.source_key or not item.target_key
            for item in migration.mappings
        )
    ):
        raise ValueError("unique state mappings required")
    irreversible = any(item.irreversible for item in migration.mappings)
    if irreversible and migration.rollback_declared:
        raise ValueError("irreversible migration cannot claim rollback")
    if compatible:
        return WorkflowMigrationReceipt(
            migration.migration_id,
            True,
            False,
            False,
        )
    return WorkflowMigrationReceipt(
        migration.migration_id,
        False,
        not terminate_and_restart,
        terminate_and_restart,
    )


class TaskType(str, Enum):
    GENERIC = "generic"
    RESEARCH = "research"
    CODE = "code"
    OPERATIONS = "operations"


@dataclass(frozen=True, slots=True)
class TaskProfile:
    task_type: TaskType
    default_budget: int
    default_tests: tuple[str, ...]
    authority: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskClassification:
    task_type: TaskType
    confidence: float
    profile: TaskProfile


def classify(
    label: str,
    profiles: dict[TaskType, TaskProfile],
) -> TaskClassification:
    if (
        set(profiles) != set(TaskType)
        or any(
            profile.default_budget < 0
            or any(not test for test in profile.default_tests)
            or any(not authority for authority in profile.authority)
            for profile in profiles.values()
        )
    ):
        raise ValueError("complete task profiles required")
    try:
        task_type = TaskType(label.lower())
    except ValueError:
        task_type = TaskType.GENERIC
    return TaskClassification(
        task_type,
        1.0 if task_type is not TaskType.GENERIC else 0.0,
        profiles[task_type],
    )


@dataclass(frozen=True, slots=True)
class ComplexityFeature:
    name: str
    value: float


@dataclass(frozen=True, slots=True)
class ComplexityEstimate:
    score: float
    uncertainty: float
    calibration_id: str
    features: tuple[ComplexityFeature, ...]


@dataclass(frozen=True, slots=True)
class EstimateRevision:
    previous: ComplexityEstimate
    revised: ComplexityEstimate
    runtime_evidence: str


def revise(
    estimate: ComplexityEstimate,
    new_score: float,
    new_uncertainty: float,
    evidence: str,
) -> EstimateRevision:
    if (
        not estimate.calibration_id
        or not evidence
        or new_score < 0
        or not 0 <= new_uncertainty <= 1
        or len({feature.name for feature in estimate.features})
        != len(estimate.features)
        or any(not feature.name for feature in estimate.features)
    ):
        raise ValueError("valid complexity evidence required")
    return EstimateRevision(
        estimate,
        ComplexityEstimate(
            new_score,
            new_uncertainty,
            estimate.calibration_id,
            estimate.features,
        ),
        evidence,
    )
