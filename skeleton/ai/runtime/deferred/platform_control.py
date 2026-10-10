"""Platform migration, control, scheduling and decision primitives."""
from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import hashlib
import math
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class MigrationStep:
    step_id: str
    from_version: int
    to_version: int
    reversible: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _text(self.step_id, "step_id"))
        for name in ("from_version", "to_version"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")
        if self.to_version <= self.from_version:
            raise ValueError("migration must advance version")
        if not isinstance(self.reversible, bool):
            raise TypeError("reversible must be boolean")


class MigrationEngine:
    def __init__(self, steps: Sequence[MigrationStep]) -> None:
        self.steps = tuple(steps)
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("migration step ids must be unique")

    def plan(self, current: int, target: int) -> tuple[MigrationStep, ...]:
        if target < current:
            raise ValueError("downgrade requires explicit rollback path")
        chosen: list[MigrationStep] = []
        version = current
        while version < target:
            candidates = sorted(
                (step for step in self.steps if step.from_version == version and step.to_version <= target),
                key=lambda step: (step.to_version, step.step_id),
            )
            if not candidates:
                raise RuntimeError(f"no migration from version {version}")
            step = candidates[-1]
            chosen.append(step)
            version = step.to_version
        return tuple(chosen)


@dataclass(frozen=True, slots=True)
class Deprecation:
    symbol: str
    replacement: str
    removal_version: int
    owner: str

    def __post_init__(self) -> None:
        for name in ("symbol", "replacement", "owner"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if isinstance(self.removal_version, bool) or not isinstance(self.removal_version, int) or self.removal_version < 1:
            raise ValueError("removal_version must be positive integer")


class DeprecationRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Deprecation] = {}

    def add(self, item: Deprecation) -> None:
        prior = self._items.get(item.symbol)
        if prior is not None and prior != item:
            raise ValueError("deprecation identity collision")
        self._items[item.symbol] = item

    def due(self, version: int) -> tuple[Deprecation, ...]:
        return tuple(sorted(
            (item for item in self._items.values() if item.removal_version <= version),
            key=lambda item: item.symbol,
        ))


@dataclass(frozen=True, slots=True)
class CodeProvenance:
    path: str
    content_digest: str
    source_ref: str
    generated_by: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _text(self.path, "path").replace("\\", "/"))
        object.__setattr__(self, "content_digest", _sha(self.content_digest, "content_digest"))
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))
        if self.generated_by is not None:
            object.__setattr__(self, "generated_by", _text(self.generated_by, "generated_by"))


class DuplicationDetector:
    @staticmethod
    def groups(records: Sequence[CodeProvenance]) -> tuple[tuple[str, ...], ...]:
        by_digest: dict[str, list[str]] = {}
        for record in records:
            by_digest.setdefault(record.content_digest, []).append(record.path)
        return tuple(
            tuple(sorted(paths))
            for _, paths in sorted(by_digest.items())
            if len(paths) > 1
        )


@dataclass(frozen=True, slots=True)
class OwnershipRule:
    pattern: str
    owners: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pattern", _text(self.pattern, "pattern"))
        owners = tuple(_text(item, "owner") for item in self.owners)
        if not owners or len(owners) != len(set(owners)):
            raise ValueError("owners must be unique and non-empty")
        object.__setattr__(self, "owners", owners)


class OwnershipMap:
    def __init__(self, rules: Sequence[OwnershipRule]) -> None:
        self.rules = tuple(rules)

    def owners_for(self, path: str) -> tuple[str, ...]:
        path = _text(path, "path").replace("\\", "/")
        matched = [rule for rule in self.rules if fnmatch.fnmatch(path, rule.pattern)]
        if not matched:
            raise KeyError(f"no owner for {path}")
        return matched[-1].owners

    def codeowners(self) -> str:
        return "\n".join(
            f"{rule.pattern} {' '.join(rule.owners)}" for rule in self.rules
        ) + "\n"


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    source_digest: str
    toolchain_digest: str
    environment_digest: str
    inputs_digest: str

    def __post_init__(self) -> None:
        for name in ("source_digest", "toolchain_digest", "environment_digest", "inputs_digest"):
            object.__setattr__(self, name, _sha(getattr(self, name), name))

    @property
    def cache_key(self) -> str:
        return sha256_json({
            "source": self.source_digest,
            "toolchain": self.toolchain_digest,
            "environment": self.environment_digest,
            "inputs": self.inputs_digest,
        })


@dataclass(frozen=True, slots=True)
class BinaryProvenance:
    artifact_digest: str
    build: BuildIdentity
    builder_id: str
    attestation_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_digest", _sha(self.artifact_digest, "artifact_digest"))
        object.__setattr__(self, "builder_id", _text(self.builder_id, "builder_id"))
        object.__setattr__(self, "attestation_digest", _sha(self.attestation_digest, "attestation_digest"))


@dataclass(frozen=True, slots=True)
class InstallerManifest:
    version: str
    payload_digest: str
    signer_key_id: str
    minimum_previous_version: str

    def __post_init__(self) -> None:
        for name in ("version", "signer_key_id", "minimum_previous_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "payload_digest", _sha(self.payload_digest, "payload_digest"))


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    from_version: str
    to_version: str
    payload_digest: str
    signature_digest: str

    def __post_init__(self) -> None:
        for name in ("from_version", "to_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.from_version == self.to_version:
            raise ValueError("update must change version")
        object.__setattr__(self, "payload_digest", _sha(self.payload_digest, "payload_digest"))
        object.__setattr__(self, "signature_digest", _sha(self.signature_digest, "signature_digest"))


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    check_id: str
    passed: bool
    detail: str
    repairable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", _text(self.check_id, "check_id"))
        object.__setattr__(self, "detail", _text(self.detail, "detail"))
        if not isinstance(self.passed, bool) or not isinstance(self.repairable, bool):
            raise TypeError("diagnostic flags must be boolean")


@dataclass(frozen=True, slots=True)
class SupportBundle:
    bundle_id: str
    checks: tuple[DiagnosticCheck, ...]
    log_digests: tuple[str, ...]
    secret_free: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id", _text(self.bundle_id, "bundle_id"))
        ids = [item.check_id for item in self.checks]
        if len(ids) != len(set(ids)):
            raise ValueError("diagnostic checks must be unique")
        for item in self.log_digests:
            _sha(item, "log_digest")
        if not isinstance(self.secret_free, bool):
            raise TypeError("secret_free must be boolean")
        if not self.secret_free:
            raise ValueError("support bundle must be secret-free")


@dataclass(frozen=True, slots=True)
class RepairProposal:
    proposal_id: str
    check_id: str
    mutation_digest: str
    reversible: bool
    requires_approval: bool = True

    def __post_init__(self) -> None:
        for name in ("proposal_id", "check_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "mutation_digest", _sha(self.mutation_digest, "mutation_digest"))
        if not isinstance(self.reversible, bool) or not isinstance(self.requires_approval, bool):
            raise TypeError("repair flags must be boolean")


@dataclass(frozen=True, slots=True)
class TwinNode:
    node_id: str
    kind: str
    state_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _text(self.node_id, "node_id"))
        object.__setattr__(self, "kind", _text(self.kind, "kind"))
        object.__setattr__(self, "state_digest", _sha(self.state_digest, "state_digest"))


class DigitalTwin:
    def __init__(self, nodes: Sequence[TwinNode], edges: Iterable[tuple[str, str]]) -> None:
        self.nodes = {node.node_id: node for node in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("digital twin node ids must be unique")
        normalized = set()
        for source, target in edges:
            if source not in self.nodes or target not in self.nodes:
                raise ValueError("digital twin edge references unknown node")
            if source == target:
                raise ValueError("digital twin self-edge forbidden")
            normalized.add((source, target))
        self.edges = tuple(sorted(normalized))

    @property
    def digest(self) -> str:
        return sha256_json({
            "nodes": [
                {"id": n.node_id, "kind": n.kind, "state": n.state_digest}
                for n in sorted(self.nodes.values(), key=lambda n: n.node_id)
            ],
            "edges": [list(edge) for edge in self.edges],
        })


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    request_id: str
    tenant_id: str
    priority: int
    cpu_units: int
    memory_units: int

    def __post_init__(self) -> None:
        for name in ("request_id", "tenant_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("priority", "cpu_units", "memory_units"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")
        if self.cpu_units < 1 or self.memory_units < 1:
            raise ValueError("resource units must be positive")


class FairResourceScheduler:
    def __init__(self, *, cpu_units: int, memory_units: int) -> None:
        if cpu_units < 1 or memory_units < 1:
            raise ValueError("scheduler capacities must be positive")
        self.cpu_units = cpu_units
        self.memory_units = memory_units
        self._queue: list[tuple[int, int, ResourceRequest]] = []
        self._sequence = 0
        self._tenant_served: dict[str, int] = {}

    def submit(self, request: ResourceRequest) -> None:
        if request.cpu_units > self.cpu_units or request.memory_units > self.memory_units:
            raise ValueError("request exceeds scheduler capacity")
        if any(item[2].request_id == request.request_id for item in self._queue):
            raise ValueError("duplicate resource request id")
        self._queue.append((-request.priority, self._sequence, request))
        self._sequence += 1

    def next(self) -> ResourceRequest:
        if not self._queue:
            raise IndexError("resource queue is empty")
        ranked = sorted(
            self._queue,
            key=lambda item: (
                self._tenant_served.get(item[2].tenant_id, 0),
                item[0],
                item[1],
            ),
        )
        chosen = ranked[0]
        self._queue.remove(chosen)
        request = chosen[2]
        self._tenant_served[request.tenant_id] = self._tenant_served.get(request.tenant_id, 0) + 1
        return request


@dataclass(frozen=True, slots=True)
class Objective:
    objective_id: str
    utility: float
    priority: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective_id", _text(self.objective_id, "objective_id"))
        if isinstance(self.utility, bool) or not isinstance(self.utility, (int, float)) or not math.isfinite(float(self.utility)):
            raise ValueError("utility must be finite")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be integer")


@dataclass(frozen=True, slots=True)
class Constraint:
    constraint_id: str
    key: str
    operator: str
    value: float

    def __post_init__(self) -> None:
        for name in ("constraint_id", "key"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.operator not in {"<=", ">=", "=="}:
            raise ValueError("unsupported constraint operator")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(float(self.value)):
            raise ValueError("constraint value must be finite")

    def allows(self, observed: float) -> bool:
        if self.operator == "<=":
            return observed <= self.value
        if self.operator == ">=":
            return observed >= self.value
        return observed == self.value


@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    candidate_id: str
    objective_scores: Mapping[str, float]
    constraint_values: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        objective_scores={}
        for key,value in self.objective_scores.items():
            key=_text(key,"objective score key")
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)):
                raise ValueError("objective scores must be finite numeric values")
            objective_scores[key]=float(value)
        constraint_values={}
        for key,value in self.constraint_values.items():
            key=_text(key,"constraint value key")
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)):
                raise ValueError("constraint values must be finite numeric values")
            constraint_values[key]=float(value)
        object.__setattr__(self,"objective_scores",objective_scores)
        object.__setattr__(self,"constraint_values",constraint_values)


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: str
    candidate_id: str
    score: float
    objective_ids: tuple[str, ...]
    constraint_ids: tuple[str, ...]

    @property
    def digest(self) -> str:
        return sha256_json({
            "decision_id": self.decision_id,
            "candidate_id": self.candidate_id,
            "score": self.score,
            "objective_ids": list(self.objective_ids),
            "constraint_ids": list(self.constraint_ids),
        })


class DecisionEngine:
    def decide(
        self,
        objectives: Sequence[Objective],
        constraints: Sequence[Constraint],
        candidates: Sequence[DecisionCandidate],
        *,
        decision_id: str,
    ) -> DecisionRecord:
        if not objectives or not candidates:
            raise ValueError("decision requires objectives and candidates")
        valid: list[tuple[float, DecisionCandidate]] = []
        objective_by_id = {item.objective_id: item for item in objectives}
        if len(objective_by_id) != len(objectives):
            raise ValueError("objective ids must be unique")
        for candidate in candidates:
            if any(
                constraint.key not in candidate.constraint_values
                or not constraint.allows(candidate.constraint_values[constraint.key])
                for constraint in constraints
            ):
                continue
            missing = set(objective_by_id) - set(candidate.objective_scores)
            if missing:
                raise ValueError("candidate missing objective scores")
            score = sum(
                objective.utility * objective.priority * float(candidate.objective_scores[objective.objective_id])
                for objective in objectives
            )
            valid.append((score, candidate))
        if not valid:
            raise RuntimeError("no candidate satisfies constraints")
        score, winner = max(valid, key=lambda item: (item[0], item[1].candidate_id))
        return DecisionRecord(
            decision_id=_text(decision_id, "decision_id"),
            candidate_id=winner.candidate_id,
            score=score,
            objective_ids=tuple(sorted(objective_by_id)),
            constraint_ids=tuple(sorted(item.constraint_id for item in constraints)),
        )


@dataclass(slots=True)
class ApprovalFatigueGuard:
    window: int
    max_prompts: int
    prompts: list[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.window < 1 or self.max_prompts < 1 or self.max_prompts > self.window:
            raise ValueError("invalid approval-fatigue window")

    def request(self, high_impact: bool) -> str:
        if not isinstance(high_impact, bool):
            raise TypeError("high_impact must be boolean")
        recent=sum(self.prompts[-self.window:])
        if high_impact:
            decision="prompt"
            prompted=True
        elif recent>=self.max_prompts:
            decision="batch_or_defer"
            prompted=False
        else:
            decision="prompt"
            prompted=True
        self.prompts.append(prompted)
        self.prompts=self.prompts[-self.window:]
        return decision


@dataclass(frozen=True, slots=True)
class IntentRevision:
    intent_id: str
    revision: int
    digest: str
    supersedes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("revision must be positive integer")
        object.__setattr__(self, "digest", _sha(self.digest, "digest"))
        if self.supersedes is not None:
            object.__setattr__(self, "supersedes", _text(self.supersedes, "supersedes"))


class IntentStore:
    def __init__(self) -> None:
        self._latest: dict[str, IntentRevision] = {}

    def append(self, revision: IntentRevision) -> None:
        prior = self._latest.get(revision.intent_id)
        if prior is None:
            if revision.revision != 1 or revision.supersedes is not None:
                raise ValueError("first intent revision must start at one")
        else:
            if revision.revision != prior.revision + 1:
                raise ValueError("intent revisions must be contiguous")
            if revision.supersedes != prior.digest:
                raise ValueError("intent supersession digest mismatch")
        self._latest[revision.intent_id] = revision

    def current(self, intent_id: str) -> IntentRevision:
        return self._latest[intent_id]


@dataclass(frozen=True, slots=True)
class SDKSurface:
    sdk_id: str
    version: str
    source_schema_digest: str
    exports: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("sdk_id", "version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "source_schema_digest", _sha(self.source_schema_digest, "source_schema_digest"))
        exports = tuple(_text(item, "export") for item in self.exports)
        if not exports or len(exports) != len(set(exports)):
            raise ValueError("SDK exports must be unique and non-empty")
        object.__setattr__(self, "exports", exports)

    @property
    def digest(self) -> str:
        return sha256_json({
            "sdk_id": self.sdk_id,
            "version": self.version,
            "source_schema_digest": self.source_schema_digest,
            "exports": list(self.exports),
        })

@dataclass(frozen=True, slots=True)
class StableIdentifier:
    namespace: str
    local_id: str
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "namespace", _text(self.namespace, "namespace"))
        object.__setattr__(self, "local_id", _text(self.local_id, "local_id"))
        if ":" in self.namespace or ":" in self.local_id:
            raise ValueError("identifier components cannot contain ':'")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("identifier version must be positive integer")

    @property
    def value(self) -> str:
        return f"{self.namespace}:{self.local_id}:v{self.version}"


@dataclass(frozen=True, slots=True)
class FederatedIdentity:
    issuer: str
    subject: str
    tenant_id: str
    assurance_level: int
    claims_digest: str

    def __post_init__(self) -> None:
        for name in ("issuer", "subject", "tenant_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if isinstance(self.assurance_level, bool) or not isinstance(self.assurance_level, int) or not 1 <= self.assurance_level <= 4:
            raise ValueError("assurance_level must be in [1,4]")
        object.__setattr__(self, "claims_digest", _sha(self.claims_digest, "claims_digest"))


@dataclass(frozen=True, slots=True)
class DeploymentTarget:
    target_id: str
    region: str
    capacity_units: int
    current_load: int
    healthy: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _text(self.target_id, "target_id"))
        object.__setattr__(self, "region", _text(self.region, "region"))
        for name in ("capacity_units", "current_load"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")
        if self.capacity_units < 1 or self.current_load > self.capacity_units:
            raise ValueError("invalid deployment target capacity")
        if not isinstance(self.healthy, bool):
            raise TypeError("healthy must be boolean")


class DeploymentPlanner:
    @staticmethod
    def choose(
        targets: Sequence[DeploymentTarget],
        *,
        required_units: int,
        allowed_regions: Iterable[str],
    ) -> DeploymentTarget:
        if isinstance(required_units, bool) or not isinstance(required_units, int) or required_units < 1:
            raise ValueError("required_units must be positive integer")
        allowed = set(allowed_regions)
        candidates = [
            item
            for item in targets
            if item.healthy
            and item.region in allowed
            and item.capacity_units - item.current_load >= required_units
        ]
        if not candidates:
            raise RuntimeError("no deployment target satisfies constraints")
        return max(
            candidates,
            key=lambda item: (
                item.capacity_units - item.current_load,
                -item.current_load,
                item.target_id,
            ),
        )

