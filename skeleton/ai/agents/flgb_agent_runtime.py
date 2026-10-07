"""FLGB-04 deterministic tools, agents, authority, and long-run recovery contracts.

This module models authorization and orchestration receipts only. Tool or sandbox
execution remains behind external executors that must honor these contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS = 256
MAX_TOOLS = 4096
MAX_CAPABILITIES = 1024
MAX_SCHEMA_BYTES = 1_000_000
MAX_PLAN_NODES = 100_000
MAX_PLAN_EDGES = 500_000
MAX_LEASE_SEQUENCE = 2**63 - 1
MAX_CHECKPOINTS = 1_000_000
MAX_RESOURCE_UNITS = 10**12
MAX_SCORE_PPM = 1_000_000


class AgentContractError(ValueError):
    """Fail-closed FLGB-04 contract error."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_id(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_ID_CHARS
        or any(ord(ch) < 32 for ch in value)
    ):
        raise AgentContractError(f"invalid {name}")
    return value


def require_digest(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise AgentContractError(f"invalid {name}")
    return value


def canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AgentContractError("value is not canonical-json encodable") from exc
    if len(raw) > MAX_SCHEMA_BYTES:
        raise AgentContractError("canonical payload exceeds byte budget")
    return raw


def digest_json(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def canonical_capabilities(values: Sequence[str]) -> tuple[str, ...]:
    caps = tuple(sorted(values))
    if len(caps) > MAX_CAPABILITIES or len(set(caps)) != len(caps):
        raise AgentContractError("capability set out of bounds or duplicated")
    for cap in caps:
        require_id(cap, "capability")
    return caps


@dataclass(frozen=True)
class ToolSchema:
    tool_name: str
    version: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_id(self.tool_name, "tool_name")
        require_id(self.version, "version")
        for name in ("input_schema", "output_schema"):
            schema = dict(getattr(self, name))
            if schema.get("type") != "object":
                raise AgentContractError(f"{name} must be an object schema")
            canonical_bytes(schema)
            object.__setattr__(self, name, MappingProxyType(schema))

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "tool_name": self.tool_name,
                "version": self.version,
                "input_schema": dict(self.input_schema),
                "output_schema": dict(self.output_schema),
            }
        )


@dataclass(frozen=True)
class ToolDescriptor:
    tool_name: str
    version: str
    schema_digest: str
    required_capabilities: tuple[str, ...]
    side_effect: str
    idempotent: bool
    compensation_supported: bool

    def __post_init__(self) -> None:
        require_id(self.tool_name, "tool_name")
        require_id(self.version, "version")
        require_digest(self.schema_digest, "schema_digest")
        object.__setattr__(
            self,
            "required_capabilities",
            canonical_capabilities(self.required_capabilities),
        )
        if self.side_effect not in {"none", "read", "write", "external-write"}:
            raise AgentContractError("invalid tool side_effect")
        if not isinstance(self.idempotent, bool) or not isinstance(self.compensation_supported, bool):
            raise AgentContractError("tool behavior flags must be boolean")
        if self.side_effect in {"write", "external-write"} and not (
            self.idempotent or self.compensation_supported
        ):
            raise AgentContractError("side-effecting tool requires idempotency or compensation")

    @property
    def identity(self) -> tuple[str, str]:
        return (self.tool_name, self.version)


class ToolRegistry:
    def __init__(self, tools: Sequence[ToolDescriptor] = ()) -> None:
        if len(tools) > MAX_TOOLS:
            raise AgentContractError("tool registry budget exceeded")
        entries: dict[tuple[str, str], ToolDescriptor] = {}
        for tool in tools:
            if not isinstance(tool, ToolDescriptor):
                raise AgentContractError("ToolDescriptor required")
            if tool.identity in entries:
                raise AgentContractError("duplicate tool identity")
            entries[tool.identity] = tool
        self._entries = MappingProxyType(entries)

    def register(self, tool: ToolDescriptor) -> "ToolRegistry":
        if not isinstance(tool, ToolDescriptor):
            raise AgentContractError("ToolDescriptor required")
        prior = self._entries.get(tool.identity)
        if prior is not None:
            if prior != tool:
                raise AgentContractError("tool identity is immutable")
            return self
        if len(self._entries) >= MAX_TOOLS:
            raise AgentContractError("tool registry budget exceeded")
        return ToolRegistry(tuple(self._entries.values()) + (tool,))

    def resolve(self, tool_name: str, version: str) -> ToolDescriptor:
        key = (require_id(tool_name, "tool_name"), require_id(version, "version"))
        try:
            return self._entries[key]
        except KeyError as exc:
            raise AgentContractError("unknown tool identity") from exc

    @property
    def digest(self) -> str:
        return digest_json(
            [
                {
                    **tool.__dict__,
                    "required_capabilities": list(tool.required_capabilities),
                }
                for tool in sorted(self._entries.values(), key=lambda item: item.identity)
            ]
        )


@dataclass(frozen=True)
class AuthorityGrant:
    subject_id: str
    capabilities: tuple[str, ...]
    parent_digest: str | None = None
    generation: int = 0

    def __post_init__(self) -> None:
        require_id(self.subject_id, "subject_id")
        object.__setattr__(self, "capabilities", canonical_capabilities(self.capabilities))
        if self.parent_digest is not None:
            require_digest(self.parent_digest, "parent_digest")
        if not _is_int(self.generation) or self.generation < 0:
            raise AgentContractError("invalid authority generation")
        if self.generation == 0 and self.parent_digest is not None:
            raise AgentContractError("root authority cannot have parent")
        if self.generation > 0 and self.parent_digest is None:
            raise AgentContractError("delegated authority requires parent")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "subject_id": self.subject_id,
                "capabilities": list(self.capabilities),
                "parent_digest": self.parent_digest,
                "generation": self.generation,
            }
        )

    def delegate(self, subject_id: str, capabilities: Sequence[str]) -> "AuthorityGrant":
        child_caps = canonical_capabilities(capabilities)
        if not set(child_caps).issubset(self.capabilities):
            raise AgentContractError("child authority exceeds parent")
        return AuthorityGrant(subject_id, child_caps, self.digest, self.generation + 1)


@dataclass(frozen=True)
class SandboxPolicy:
    sandbox_id: str
    allowed_capabilities: tuple[str, ...]
    cpu_units: int
    memory_bytes: int
    wall_time_ms: int
    network_mode: str = "deny"

    def __post_init__(self) -> None:
        require_id(self.sandbox_id, "sandbox_id")
        object.__setattr__(
            self,
            "allowed_capabilities",
            canonical_capabilities(self.allowed_capabilities),
        )
        for name in ("cpu_units", "memory_bytes", "wall_time_ms"):
            value = getattr(self, name)
            if not _is_int(value) or not 1 <= value <= MAX_RESOURCE_UNITS:
                raise AgentContractError(f"invalid {name}")
        if self.network_mode not in {"deny", "allowlisted-read", "allowlisted"}:
            raise AgentContractError("invalid network_mode")


@dataclass(frozen=True)
class SandboxExecutionRequest:
    operation_id: str
    tool_name: str
    tool_version: str
    input_digest: str
    requested_capabilities: tuple[str, ...]
    authority_digest: str
    sandbox_policy_digest: str

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        require_id(self.tool_name, "tool_name")
        require_id(self.tool_version, "tool_version")
        require_digest(self.input_digest, "input_digest")
        object.__setattr__(
            self,
            "requested_capabilities",
            canonical_capabilities(self.requested_capabilities),
        )
        require_digest(self.authority_digest, "authority_digest")
        require_digest(self.sandbox_policy_digest, "sandbox_policy_digest")


def authorize_sandbox_request(
    request: SandboxExecutionRequest,
    *,
    tool: ToolDescriptor,
    authority: AuthorityGrant,
    policy: SandboxPolicy,
) -> str:
    if not isinstance(request, SandboxExecutionRequest):
        raise AgentContractError("SandboxExecutionRequest required")
    if (request.tool_name, request.tool_version) != tool.identity:
        raise AgentContractError("tool identity mismatch")
    if request.authority_digest != authority.digest:
        raise AgentContractError("authority digest mismatch")
    policy_digest = digest_json(
        {
            "sandbox_id": policy.sandbox_id,
            "allowed_capabilities": list(policy.allowed_capabilities),
            "cpu_units": policy.cpu_units,
            "memory_bytes": policy.memory_bytes,
            "wall_time_ms": policy.wall_time_ms,
            "network_mode": policy.network_mode,
        }
    )
    if request.sandbox_policy_digest != policy_digest:
        raise AgentContractError("sandbox policy digest mismatch")
    requested = set(request.requested_capabilities)
    required = set(tool.required_capabilities)
    if requested != required:
        raise AgentContractError("requested capabilities must exactly match tool contract")
    if not requested.issubset(authority.capabilities):
        raise AgentContractError("authority missing requested capability")
    if not requested.issubset(policy.allowed_capabilities):
        raise AgentContractError("sandbox policy missing requested capability")
    return digest_json(
        {
            "request": request.__dict__,
            "tool": tool.__dict__,
            "authority": authority.digest,
            "policy": policy_digest,
        }
    )


@dataclass(frozen=True)
class WriteReceipt:
    idempotency_key: str
    input_digest: str
    result_digest: str
    sequence: int

    def __post_init__(self) -> None:
        require_id(self.idempotency_key, "idempotency_key")
        require_digest(self.input_digest, "input_digest")
        require_digest(self.result_digest, "result_digest")
        if not _is_int(self.sequence) or self.sequence < 0:
            raise AgentContractError("invalid write sequence")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


class IdempotentWriteLedger:
    def __init__(self, receipts: Sequence[WriteReceipt] = ()) -> None:
        entries: dict[str, WriteReceipt] = {}
        for index, receipt in enumerate(receipts):
            if not isinstance(receipt, WriteReceipt) or receipt.sequence != index:
                raise AgentContractError("write receipt sequence drift")
            if receipt.idempotency_key in entries:
                raise AgentContractError("duplicate idempotency key")
            entries[receipt.idempotency_key] = receipt
        self._entries = MappingProxyType(entries)
        self.receipts = tuple(receipts)

    def admit(self, idempotency_key: str, input_digest: str) -> WriteReceipt | None:
        require_id(idempotency_key, "idempotency_key")
        require_digest(input_digest, "input_digest")
        prior = self._entries.get(idempotency_key)
        if prior is None:
            return None
        if prior.input_digest != input_digest:
            raise AgentContractError("idempotency key reused with different input")
        return prior

    def commit(
        self,
        idempotency_key: str,
        input_digest: str,
        result_digest: str,
    ) -> "IdempotentWriteLedger":
        prior = self.admit(idempotency_key, input_digest)
        if prior is not None:
            if prior.result_digest != require_digest(result_digest, "result_digest"):
                raise AgentContractError("idempotent replay result mismatch")
            return self
        receipt = WriteReceipt(
            idempotency_key,
            input_digest,
            result_digest,
            len(self.receipts),
        )
        return IdempotentWriteLedger(self.receipts + (receipt,))


@dataclass(frozen=True)
class CompensationAction:
    action_id: str
    original_receipt_digest: str
    compensation_input_digest: str

    def __post_init__(self) -> None:
        require_id(self.action_id, "action_id")
        require_digest(self.original_receipt_digest, "original_receipt_digest")
        require_digest(self.compensation_input_digest, "compensation_input_digest")


@dataclass(frozen=True)
class CompensationReceipt:
    action_id: str
    original_receipt_digest: str
    outcome: str
    result_digest: str

    def __post_init__(self) -> None:
        require_id(self.action_id, "action_id")
        require_digest(self.original_receipt_digest, "original_receipt_digest")
        if self.outcome not in {"compensated", "already-compensated", "failed"}:
            raise AgentContractError("invalid compensation outcome")
        require_digest(self.result_digest, "result_digest")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def compensation_order(actions: Sequence[CompensationAction]) -> tuple[CompensationAction, ...]:
    ids = [action.action_id for action in actions]
    if len(set(ids)) != len(ids):
        raise AgentContractError("duplicate compensation action")
    return tuple(reversed(tuple(actions)))


@dataclass(frozen=True)
class PlanNode:
    node_id: str
    action_digest: str
    dependencies: tuple[str, ...] = ()
    authority_digest: str | None = None

    def __post_init__(self) -> None:
        require_id(self.node_id, "node_id")
        require_digest(self.action_digest, "action_digest")
        deps = tuple(sorted(self.dependencies))
        if self.node_id in deps or len(set(deps)) != len(deps):
            raise AgentContractError("invalid plan dependencies")
        for dep in deps:
            require_id(dep, "dependency")
        object.__setattr__(self, "dependencies", deps)
        if self.authority_digest is not None:
            require_digest(self.authority_digest, "authority_digest")


class PlanDAG:
    def __init__(self, nodes: Sequence[PlanNode]) -> None:
        if not nodes or len(nodes) > MAX_PLAN_NODES:
            raise AgentContractError("plan node count out of bounds")
        by_id = {node.node_id: node for node in nodes}
        if len(by_id) != len(nodes):
            raise AgentContractError("duplicate plan node")
        edge_count = sum(len(node.dependencies) for node in nodes)
        if edge_count > MAX_PLAN_EDGES:
            raise AgentContractError("plan edge budget exceeded")
        for node in nodes:
            missing = set(node.dependencies) - set(by_id)
            if missing:
                raise AgentContractError(f"unknown plan dependency: {sorted(missing)}")
        self._nodes = MappingProxyType(by_id)
        self._waves = self._topological_waves()

    def _topological_waves(self) -> tuple[tuple[str, ...], ...]:
        remaining = set(self._nodes)
        completed: set[str] = set()
        waves: list[tuple[str, ...]] = []
        while remaining:
            ready = sorted(
                node_id
                for node_id in remaining
                if set(self._nodes[node_id].dependencies).issubset(completed)
            )
            if not ready:
                raise AgentContractError("plan dependency cycle")
            waves.append(tuple(ready))
            completed.update(ready)
            remaining.difference_update(ready)
        return tuple(waves)

    @property
    def waves(self) -> tuple[tuple[str, ...], ...]:
        return self._waves

    @property
    def digest(self) -> str:
        return digest_json(
            [
                {
                    "node_id": node.node_id,
                    "action_digest": node.action_digest,
                    "dependencies": list(node.dependencies),
                    "authority_digest": node.authority_digest,
                }
                for node in sorted(self._nodes.values(), key=lambda item: item.node_id)
            ]
        )


@dataclass(frozen=True)
class WorkerLease:
    lease_id: str
    worker_id: str
    scope_digest: str
    authority_digest: str
    issued_sequence: int
    expires_sequence: int
    generation: int = 0

    def __post_init__(self) -> None:
        require_id(self.lease_id, "lease_id")
        require_id(self.worker_id, "worker_id")
        require_digest(self.scope_digest, "scope_digest")
        require_digest(self.authority_digest, "authority_digest")
        for name in ("issued_sequence", "expires_sequence", "generation"):
            value = getattr(self, name)
            if not _is_int(value) or value < 0 or value > MAX_LEASE_SEQUENCE:
                raise AgentContractError(f"invalid {name}")
        if self.expires_sequence <= self.issued_sequence:
            raise AgentContractError("lease must expire after issue")

    def valid_at(self, sequence: int) -> bool:
        if not _is_int(sequence) or sequence < 0:
            raise AgentContractError("invalid lease query sequence")
        return self.issued_sequence <= sequence < self.expires_sequence

    def renew(self, *, issued_sequence: int, expires_sequence: int) -> "WorkerLease":
        if not _is_int(issued_sequence) or not _is_int(expires_sequence):
            raise AgentContractError("lease renewal sequences must be integers")
        if issued_sequence < self.issued_sequence:
            raise AgentContractError("lease renewal cannot move backwards")
        if self.generation >= MAX_LEASE_SEQUENCE:
            raise AgentContractError("lease generation exhausted")
        return WorkerLease(
            self.lease_id,
            self.worker_id,
            self.scope_digest,
            self.authority_digest,
            issued_sequence,
            expires_sequence,
            self.generation + 1,
        )

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class Checkpoint:
    run_id: str
    sequence: int
    state_digest: str
    plan_digest: str
    authority_digest: str
    prior_checkpoint_digest: str | None = None

    def __post_init__(self) -> None:
        require_id(self.run_id, "run_id")
        if not _is_int(self.sequence) or not 0 <= self.sequence < MAX_CHECKPOINTS:
            raise AgentContractError("invalid checkpoint sequence")
        require_digest(self.state_digest, "state_digest")
        require_digest(self.plan_digest, "plan_digest")
        require_digest(self.authority_digest, "authority_digest")
        if self.prior_checkpoint_digest is not None:
            require_digest(self.prior_checkpoint_digest, "prior_checkpoint_digest")
        if self.sequence == 0 and self.prior_checkpoint_digest is not None:
            raise AgentContractError("genesis checkpoint cannot have parent")
        if self.sequence > 0 and self.prior_checkpoint_digest is None:
            raise AgentContractError("non-genesis checkpoint requires parent")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def append_checkpoint(
    checkpoints: Sequence[Checkpoint],
    *,
    run_id: str,
    state_digest: str,
    plan_digest: str,
    authority_digest: str,
) -> tuple[Checkpoint, ...]:
    if len(checkpoints) >= MAX_CHECKPOINTS:
        raise AgentContractError("checkpoint budget exceeded")
    for index, checkpoint in enumerate(checkpoints):
        if checkpoint.sequence != index:
            raise AgentContractError("checkpoint sequence drift")
        if checkpoint.run_id != run_id:
            raise AgentContractError("checkpoint run identity drift")
        expected_prior = checkpoints[index - 1].digest if index else None
        if checkpoint.prior_checkpoint_digest != expected_prior:
            raise AgentContractError("checkpoint chain drift")
    prior = checkpoints[-1].digest if checkpoints else None
    checkpoint = Checkpoint(
        run_id,
        len(checkpoints),
        state_digest,
        plan_digest,
        authority_digest,
        prior,
    )
    return tuple(checkpoints) + (checkpoint,)


@dataclass(frozen=True)
class HandoffReceipt:
    handoff_id: str
    from_worker: str
    to_worker: str
    scope_digest: str
    from_authority_digest: str
    to_authority_digest: str
    checkpoint_digest: str

    def __post_init__(self) -> None:
        require_id(self.handoff_id, "handoff_id")
        require_id(self.from_worker, "from_worker")
        require_id(self.to_worker, "to_worker")
        if self.from_worker == self.to_worker:
            raise AgentContractError("handoff requires distinct workers")
        for name in (
            "scope_digest",
            "from_authority_digest",
            "to_authority_digest",
            "checkpoint_digest",
        ):
            require_digest(getattr(self, name), name)

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def authorize_handoff(
    *,
    handoff_id: str,
    from_worker: str,
    to_worker: str,
    scope_digest: str,
    parent_authority: AuthorityGrant,
    child_authority: AuthorityGrant,
    checkpoint: Checkpoint,
) -> HandoffReceipt:
    if child_authority.parent_digest != parent_authority.digest:
        raise AgentContractError("handoff authority is not delegated from parent")
    if checkpoint.authority_digest != parent_authority.digest:
        raise AgentContractError("handoff checkpoint authority drift")
    if not set(child_authority.capabilities).issubset(parent_authority.capabilities):
        raise AgentContractError("handoff authority exceeds parent")
    return HandoffReceipt(
        handoff_id,
        from_worker,
        to_worker,
        require_digest(scope_digest, "scope_digest"),
        parent_authority.digest,
        child_authority.digest,
        checkpoint.digest,
    )


@dataclass(frozen=True)
class ArbitrationProposal:
    proposal_id: str
    agent_id: str
    artifact_digest: str
    quality_ppm: int
    risk_ppm: int
    evidence_digest: str

    def __post_init__(self) -> None:
        require_id(self.proposal_id, "proposal_id")
        require_id(self.agent_id, "agent_id")
        require_digest(self.artifact_digest, "artifact_digest")
        require_digest(self.evidence_digest, "evidence_digest")
        for name in ("quality_ppm", "risk_ppm"):
            value = getattr(self, name)
            if not _is_int(value) or not 0 <= value <= MAX_SCORE_PPM:
                raise AgentContractError(f"invalid {name}")


@dataclass(frozen=True)
class ArbitrationDecision:
    winner_proposal_id: str
    evaluated_proposal_ids: tuple[str, ...]
    verifier_digest: str
    decision_digest: str


def arbitrate(
    proposals: Sequence[ArbitrationProposal],
    *,
    verifier_digest: str,
    maximum_risk_ppm: int,
) -> ArbitrationDecision:
    require_digest(verifier_digest, "verifier_digest")
    if not _is_int(maximum_risk_ppm) or not 0 <= maximum_risk_ppm <= MAX_SCORE_PPM:
        raise AgentContractError("invalid maximum_risk_ppm")
    if len(proposals) < 2:
        raise AgentContractError("arbitration requires at least two proposals")
    ids = [proposal.proposal_id for proposal in proposals]
    if len(set(ids)) != len(ids):
        raise AgentContractError("duplicate arbitration proposal")
    eligible = [proposal for proposal in proposals if proposal.risk_ppm <= maximum_risk_ppm]
    if not eligible:
        raise AgentContractError("no proposal satisfies risk gate")
    winner = sorted(
        eligible,
        key=lambda item: (-item.quality_ppm, item.risk_ppm, item.proposal_id),
    )[0]
    evaluated = tuple(sorted(ids))
    decision_digest = digest_json(
        {
            "winner": winner.proposal_id,
            "evaluated": list(evaluated),
            "verifier_digest": verifier_digest,
            "maximum_risk_ppm": maximum_risk_ppm,
        }
    )
    return ArbitrationDecision(
        winner.proposal_id,
        evaluated,
        verifier_digest,
        decision_digest,
    )


@dataclass(frozen=True)
class RecoveryReceipt:
    run_id: str
    failed_generation: int
    recovery_generation: int
    checkpoint_digest: str
    replay_cursor: int
    pending_effects_digest: str
    authority_digest: str

    def __post_init__(self) -> None:
        require_id(self.run_id, "run_id")
        for name in ("failed_generation", "recovery_generation", "replay_cursor"):
            value = getattr(self, name)
            if not _is_int(value) or value < 0:
                raise AgentContractError(f"invalid {name}")
        if self.recovery_generation != self.failed_generation + 1:
            raise AgentContractError("recovery generation must advance exactly once")
        for name in ("checkpoint_digest", "pending_effects_digest", "authority_digest"):
            require_digest(getattr(self, name), name)

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def recover_from_checkpoint(
    *,
    run_id: str,
    failed_generation: int,
    checkpoint: Checkpoint,
    replay_cursor: int,
    pending_effects_digest: str,
    authority_digest: str,
) -> RecoveryReceipt:
    if checkpoint.run_id != run_id:
        raise AgentContractError("recovery checkpoint run mismatch")
    if checkpoint.authority_digest != authority_digest:
        raise AgentContractError("recovery authority drift")
    return RecoveryReceipt(
        run_id,
        failed_generation,
        failed_generation + 1,
        checkpoint.digest,
        replay_cursor,
        pending_effects_digest,
        authority_digest,
    )
