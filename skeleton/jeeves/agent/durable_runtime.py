"""Restart-safe frontier Jeeves runtime backed by transactional SQLite state.

This composition closes the process-loss gap between three independently useful
primitives:

* ``SQLiteRunStore`` persists typed runtime checkpoints under worker leases;
* ``SQLiteExecutionAuditStore`` durably appends security/tool events before a
  consequential observation can be forgotten;
* ``DurableLearnedTransitionModel`` write-ahead journals every model mutation.

The components intentionally do not pretend to be one distributed transaction
with an external tool. Instead recovery uses monotonic roots:

* the durable runtime checkpoint may lag;
* the execution audit may be ahead and can prove an ambiguous side effect;
* the transition journal may be ahead and deterministically reconstructs all
  committed learning;
* the checkpoint's model-lineage root must remain an ancestor of the restored
  model lineage.

This is the same pattern used by durable workflow engines: external effects are
made observable/idempotent and recovery reasons over durable facts rather than
assuming that process memory survived.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from skeleton.state.run_store import (
    InvalidTransition,
    RunNotFound,
    RunStatus,
    SQLiteRunStore,
    StateConflict,
)

from .durable_audit import SQLiteExecutionAuditStore
from .durable_transition_model import (
    DurableLearnedTransitionModel,
    SQLiteTransitionJournal,
)
from .evidence import EvidenceArtifact
from .frontier_runtime import (
    FrontierJeevesAgentRuntime,
    ScopedGeneralizingRuntimeEpistemicGuard,
)
from .provider import ProviderRouter
from .runtime import InMemoryCheckpointer, RunCheckpoint, RunInputs
from .types import (
    AgentPhase,
    EvidenceKind,
    EvidenceRef,
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    TerminationReason,
    ToolObservation,
    Usage,
    json_safe,
    require_id,
    stable_fingerprint,
)
from .world_model import (
    BeliefEdge,
    BeliefRevision,
    BeliefState,
    ContradictionGroup,
    EdgeKind,
    Hypothesis,
    HypothesisStatus,
    Proposition,
    RevisionKind,
)


DURABLE_JEEVES_STATE_VERSION = 1


class DurableRuntimeError(RuntimeError):
    """Raised when restart-safe runtime state is absent or inconsistent."""


class _WorldStateCodec:
    """Exact current-state codec for the host-side epistemic world graph.

    Historical rollback snapshots are intentionally not persisted; the current
    beliefs, revisions, graph edges, contradiction groups and hypotheses are.
    That is sufficient to reconstruct the exact current world fingerprint and
    continue evidence revision after a restart.
    """

    @classmethod
    def encode(cls, world) -> Mapping[str, Any]:
        with world._lock:
            payload = {
                "version": world._version,
                "min_probability": world._min_probability,
                "max_probability": world._max_probability,
                "beliefs": [
                    cls._belief_to_dict(world._beliefs[key])
                    for key in sorted(world._beliefs)
                ],
                "revisions": [
                    cls._revision_to_dict(world._revisions[revision_id])
                    for revision_id in world._revision_order
                    if revision_id in world._revisions
                ],
                "revision_order": list(world._revision_order),
                "edges": [
                    cls._edge_to_dict(world._edges[key])
                    for key in sorted(world._edges)
                ],
                "contradictions": [
                    cls._contradiction_to_dict(world._contradictions[key])
                    for key in sorted(world._contradictions)
                ],
                "hypotheses": [
                    cls._hypothesis_to_dict(world._hypotheses[key])
                    for key in sorted(world._hypotheses)
                ],
            }
        payload = json_safe(payload)
        return {
            **payload,
            "world_fingerprint": world.snapshot(persist=False).fingerprint,
        }

    @classmethod
    def restore(cls, world, raw: Mapping[str, Any]) -> None:
        expected = str(raw["world_fingerprint"])
        minimum = float(raw["min_probability"])
        maximum = float(raw["max_probability"])
        if minimum != world._min_probability or maximum != world._max_probability:
            raise DurableRuntimeError("world probability bounds differ from durable state")

        beliefs = {
            item.proposition_id: item
            for item in (cls._belief_from_dict(value) for value in raw.get("beliefs", ()))
        }
        revisions = {
            item.revision_id: item
            for item in (cls._revision_from_dict(value) for value in raw.get("revisions", ()))
        }
        revision_order = [str(value) for value in raw.get("revision_order", ())]
        if any(revision_id not in revisions for revision_id in revision_order):
            raise DurableRuntimeError("durable world revision order references missing revision")
        edges = {
            item.edge_id: item
            for item in (cls._edge_from_dict(value) for value in raw.get("edges", ()))
        }
        contradictions = {
            item.group_id: item
            for item in (
                cls._contradiction_from_dict(value)
                for value in raw.get("contradictions", ())
            )
        }
        hypotheses = {
            item.hypothesis_id: item
            for item in (
                cls._hypothesis_from_dict(value)
                for value in raw.get("hypotheses", ())
            )
        }

        with world._lock:
            world._beliefs = beliefs
            world._semantic_index = {
                belief.proposition.semantic_key: proposition_id
                for proposition_id, belief in beliefs.items()
            }
            world._revisions = revisions
            world._revision_order = revision_order
            world._edges = edges
            world._out_edges = defaultdict(set)
            world._in_edges = defaultdict(set)
            for edge_id, edge in edges.items():
                world._out_edges[edge.source_id].add(edge_id)
                world._in_edges[edge.target_id].add(edge_id)
            world._contradictions = contradictions
            world._hypotheses = hypotheses
            world._version = int(raw["version"])
            world._snapshots = deque(maxlen=world._max_snapshots)

        actual = world.snapshot(persist=False).fingerprint
        if actual != expected:
            raise DurableRuntimeError("restored world fingerprint mismatch")

    @staticmethod
    def _proposition_to_dict(value: Proposition) -> Mapping[str, Any]:
        return {
            "proposition_id": value.proposition_id,
            "subject": value.subject,
            "predicate": value.predicate,
            "object": value.object,
            "polarity": value.polarity,
            "scope": value.scope,
            "temporal_key": value.temporal_key,
            "metadata": dict(value.metadata),
        }

    @staticmethod
    def _proposition_from_dict(raw: Mapping[str, Any]) -> Proposition:
        return Proposition(
            proposition_id=str(raw["proposition_id"]),
            subject=str(raw["subject"]),
            predicate=str(raw["predicate"]),
            object=raw.get("object"),
            polarity=bool(raw.get("polarity", True)),
            scope=str(raw.get("scope", "default")),
            temporal_key=raw.get("temporal_key"),
            metadata=dict(raw.get("metadata", {})),
        )

    @classmethod
    def _belief_to_dict(cls, value: BeliefState) -> Mapping[str, Any]:
        return {
            "proposition": cls._proposition_to_dict(value.proposition),
            "probability": value.probability,
            "prior_probability": value.prior_probability,
            "created_at": value.created_at,
            "updated_at": value.updated_at,
            "revision_ids": list(value.revision_ids),
            "supporting_evidence_ids": list(value.supporting_evidence_ids),
            "refuting_evidence_ids": list(value.refuting_evidence_ids),
            "contradiction_group_ids": list(value.contradiction_group_ids),
            "locked": value.locked,
            "metadata": dict(value.metadata),
        }

    @classmethod
    def _belief_from_dict(cls, raw: Mapping[str, Any]) -> BeliefState:
        return BeliefState(
            proposition=cls._proposition_from_dict(raw["proposition"]),
            probability=float(raw["probability"]),
            prior_probability=float(raw["prior_probability"]),
            created_at=float(raw["created_at"]),
            updated_at=float(raw["updated_at"]),
            revision_ids=tuple(raw.get("revision_ids", ())),
            supporting_evidence_ids=tuple(raw.get("supporting_evidence_ids", ())),
            refuting_evidence_ids=tuple(raw.get("refuting_evidence_ids", ())),
            contradiction_group_ids=tuple(raw.get("contradiction_group_ids", ())),
            locked=bool(raw.get("locked", False)),
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _revision_to_dict(value: BeliefRevision) -> Mapping[str, Any]:
        return {
            "revision_id": value.revision_id,
            "proposition_id": value.proposition_id,
            "kind": value.kind.value,
            "prior_probability": value.prior_probability,
            "posterior_probability": value.posterior_probability,
            "evidence_id": value.evidence_id,
            "likelihood_ratio": value.likelihood_ratio,
            "reliability": value.reliability,
            "at": value.at,
            "reason": value.reason,
            "transaction_id": value.transaction_id,
            "metadata": dict(value.metadata),
        }

    @staticmethod
    def _revision_from_dict(raw: Mapping[str, Any]) -> BeliefRevision:
        return BeliefRevision(
            revision_id=str(raw["revision_id"]),
            proposition_id=str(raw["proposition_id"]),
            kind=RevisionKind(str(raw["kind"])),
            prior_probability=float(raw["prior_probability"]),
            posterior_probability=float(raw["posterior_probability"]),
            evidence_id=raw.get("evidence_id"),
            likelihood_ratio=float(raw["likelihood_ratio"]),
            reliability=float(raw["reliability"]),
            at=float(raw["at"]),
            reason=str(raw["reason"]),
            transaction_id=raw.get("transaction_id"),
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _edge_to_dict(value: BeliefEdge) -> Mapping[str, Any]:
        return {
            "edge_id": value.edge_id,
            "source_id": value.source_id,
            "target_id": value.target_id,
            "kind": value.kind.value,
            "weight": value.weight,
            "confidence": value.confidence,
            "evidence_ids": list(value.evidence_ids),
            "created_at": value.created_at,
            "metadata": dict(value.metadata),
        }

    @staticmethod
    def _edge_from_dict(raw: Mapping[str, Any]) -> BeliefEdge:
        return BeliefEdge(
            edge_id=str(raw["edge_id"]),
            source_id=str(raw["source_id"]),
            target_id=str(raw["target_id"]),
            kind=EdgeKind(str(raw["kind"])),
            weight=float(raw.get("weight", 1.0)),
            confidence=float(raw.get("confidence", 1.0)),
            evidence_ids=tuple(raw.get("evidence_ids", ())),
            created_at=float(raw["created_at"]),
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _contradiction_to_dict(value: ContradictionGroup) -> Mapping[str, Any]:
        return {
            "group_id": value.group_id,
            "proposition_ids": list(value.proposition_ids),
            "exclusive": value.exclusive,
            "normalized": value.normalized,
            "description": value.description,
            "created_at": value.created_at,
        }

    @staticmethod
    def _contradiction_from_dict(raw: Mapping[str, Any]) -> ContradictionGroup:
        return ContradictionGroup(
            group_id=str(raw["group_id"]),
            proposition_ids=tuple(raw["proposition_ids"]),
            exclusive=bool(raw.get("exclusive", True)),
            normalized=bool(raw.get("normalized", True)),
            description=str(raw.get("description", "")),
            created_at=float(raw["created_at"]),
        )

    @staticmethod
    def _hypothesis_to_dict(value: Hypothesis) -> Mapping[str, Any]:
        return {
            "hypothesis_id": value.hypothesis_id,
            "label": value.label,
            "proposition_ids": list(value.proposition_ids),
            "prior": value.prior,
            "posterior": value.posterior,
            "status": value.status.value,
            "explanatory_power": value.explanatory_power,
            "complexity_penalty": value.complexity_penalty,
            "evidence_coverage": value.evidence_coverage,
            "contradiction_count": value.contradiction_count,
            "notes": value.notes,
        }

    @staticmethod
    def _hypothesis_from_dict(raw: Mapping[str, Any]) -> Hypothesis:
        return Hypothesis(
            hypothesis_id=str(raw["hypothesis_id"]),
            label=str(raw["label"]),
            proposition_ids=tuple(raw["proposition_ids"]),
            prior=float(raw["prior"]),
            posterior=float(raw["posterior"]),
            status=HypothesisStatus(str(raw["status"])),
            explanatory_power=float(raw.get("explanatory_power", 0.5)),
            complexity_penalty=float(raw.get("complexity_penalty", 0.0)),
            evidence_coverage=float(raw.get("evidence_coverage", 0.0)),
            contradiction_count=int(raw.get("contradiction_count", 0)),
            notes=str(raw.get("notes", "")),
        )


class _CheckpointCodec:
    @classmethod
    def encode(cls, checkpoint: RunCheckpoint) -> Mapping[str, Any]:
        payload = {
            "run_id": checkpoint.run_id,
            "goal_id": checkpoint.goal_id,
            "phase": checkpoint.phase.value,
            "sequence": checkpoint.sequence,
            "usage": cls._usage_to_dict(checkpoint.usage),
            "plan": checkpoint.plan.to_dict() if checkpoint.plan is not None else None,
            "observations": [cls._observation_to_dict(item) for item in checkpoint.observations],
            "evidence": [cls._artifact_to_dict(item) for item in checkpoint.evidence],
            "scratch": dict(checkpoint.scratch),
            "replan_count": checkpoint.replan_count,
            "previous_trace_fingerprint": checkpoint.previous_trace_fingerprint,
            "current_trace_fingerprint": checkpoint.current_trace_fingerprint,
            "last_error": checkpoint.last_error,
            "created_at": checkpoint.created_at,
            "updated_at": checkpoint.updated_at,
            "metadata": dict(checkpoint.metadata),
        }
        return json_safe(payload)

    @classmethod
    def decode(cls, raw: Mapping[str, Any]) -> RunCheckpoint:
        checkpoint = RunCheckpoint(
            run_id=str(raw["run_id"]),
            goal_id=str(raw["goal_id"]),
            phase=AgentPhase(str(raw["phase"])),
            sequence=int(raw["sequence"]),
            usage=cls._usage_from_dict(raw["usage"]),
            plan=None if raw.get("plan") is None else cls._plan_from_dict(raw["plan"]),
            observations=tuple(
                cls._observation_from_dict(item)
                for item in raw.get("observations", ())
            ),
            evidence=tuple(
                cls._artifact_from_dict(item)
                for item in raw.get("evidence", ())
            ),
            scratch=dict(raw.get("scratch", {})),
            replan_count=int(raw.get("replan_count", 0)),
            previous_trace_fingerprint=str(raw.get("previous_trace_fingerprint", "")),
            current_trace_fingerprint=str(raw.get("current_trace_fingerprint", "")),
            last_error=raw.get("last_error"),
            created_at=float(raw["created_at"]),
            updated_at=float(raw["updated_at"]),
            metadata=dict(raw.get("metadata", {})),
        )
        return checkpoint

    @staticmethod
    def _usage_to_dict(value: Usage) -> Mapping[str, int]:
        return {
            "steps": value.steps,
            "model_calls": value.model_calls,
            "tool_calls": value.tool_calls,
            "prompt_tokens": value.prompt_tokens,
            "completion_tokens": value.completion_tokens,
            "cached_model_calls": value.cached_model_calls,
        }

    @staticmethod
    def _usage_from_dict(raw: Mapping[str, Any]) -> Usage:
        return Usage(
            steps=int(raw.get("steps", 0)),
            model_calls=int(raw.get("model_calls", 0)),
            tool_calls=int(raw.get("tool_calls", 0)),
            prompt_tokens=int(raw.get("prompt_tokens", 0)),
            completion_tokens=int(raw.get("completion_tokens", 0)),
            cached_model_calls=int(raw.get("cached_model_calls", 0)),
        )

    @staticmethod
    def _ref_to_dict(value: EvidenceRef) -> Mapping[str, Any]:
        return {
            "evidence_id": value.evidence_id,
            "kind": value.kind.value,
            "source": value.source,
            "fingerprint": value.fingerprint,
            "confidence": value.confidence,
            "observed_at": value.observed_at,
            "uri": value.uri,
        }

    @staticmethod
    def _ref_from_dict(raw: Mapping[str, Any]) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=str(raw["evidence_id"]),
            kind=EvidenceKind(str(raw["kind"])),
            source=str(raw["source"]),
            fingerprint=str(raw["fingerprint"]),
            confidence=float(raw.get("confidence", 1.0)),
            observed_at=float(raw["observed_at"]),
            uri=raw.get("uri"),
        )

    @classmethod
    def _observation_to_dict(cls, value: ToolObservation) -> Mapping[str, Any]:
        return {
            "call_id": value.call_id,
            "tool_name": value.tool_name,
            "ok": value.ok,
            "payload": value.payload,
            "error": value.error,
            "evidence": [cls._ref_to_dict(item) for item in value.evidence],
            "latency_ms": value.latency_ms,
            "cached": value.cached,
        }

    @classmethod
    def _observation_from_dict(cls, raw: Mapping[str, Any]) -> ToolObservation:
        return ToolObservation(
            call_id=str(raw["call_id"]),
            tool_name=str(raw["tool_name"]),
            ok=bool(raw["ok"]),
            payload=raw.get("payload"),
            error=raw.get("error"),
            evidence=tuple(cls._ref_from_dict(item) for item in raw.get("evidence", ())),
            latency_ms=float(raw.get("latency_ms", 0.0)),
            cached=bool(raw.get("cached", False)),
        )

    @staticmethod
    def _artifact_to_dict(value: EvidenceArtifact) -> Mapping[str, Any]:
        return {
            "evidence_id": value.evidence_id,
            "kind": value.kind.value,
            "source": value.source,
            "payload": value.payload,
            "observed_at": value.observed_at,
            "confidence": value.confidence,
            "uri": value.uri,
            "parent_ids": list(value.parent_ids),
            "metadata": dict(value.metadata),
        }

    @staticmethod
    def _artifact_from_dict(raw: Mapping[str, Any]) -> EvidenceArtifact:
        return EvidenceArtifact(
            evidence_id=str(raw["evidence_id"]),
            kind=EvidenceKind(str(raw["kind"])),
            source=str(raw["source"]),
            payload=raw.get("payload"),
            observed_at=float(raw["observed_at"]),
            confidence=float(raw.get("confidence", 1.0)),
            uri=raw.get("uri"),
            parent_ids=tuple(raw.get("parent_ids", ())),
            metadata=dict(raw.get("metadata", {})),
        )

    @staticmethod
    def _plan_from_dict(raw: Mapping[str, Any]) -> Plan:
        steps = tuple(
            PlanStep(
                step_id=str(item["step_id"]),
                title=str(item["title"]),
                description=str(item["description"]),
                dependencies=tuple(item.get("dependencies", ())),
                tool=item.get("tool"),
                arguments=dict(item.get("arguments", {})),
                expected_outcome=str(item.get("expected_outcome", "")),
                verification=str(item.get("verification", "")),
                risk=RiskTier(str(item.get("risk", RiskTier.READ_ONLY.value))),
                status=StepStatus(str(item.get("status", StepStatus.PENDING.value))),
                attempts=int(item.get("attempts", 0)),
                max_attempts=int(item.get("max_attempts", 2)),
            )
            for item in raw["steps"]
        )
        return Plan(
            plan_id=str(raw["plan_id"]),
            goal_id=str(raw["goal_id"]),
            steps=steps,
            version=int(raw.get("version", 1)),
            rationale=str(raw.get("rationale", "")),
            created_at=float(raw.get("created_at", 0.0)),
        )


class DurableFrontierJeevesAgentRuntime(FrontierJeevesAgentRuntime):
    """Frontier runtime whose restart-critical state is SQLite durable."""

    def __init__(
        self,
        *,
        provider_router: ProviderRouter,
        state_path: str | Path,
        worker_id: str,
        lease_seconds: float = 60.0,
        model_id: str = "jeeves-frontier-global",
        maximum_checkpoint_bytes: int = 64 * 1024 * 1024,
        **kwargs: Any,
    ) -> None:
        self.state_path = Path(state_path)
        self.worker_id = require_id("worker_id", worker_id)
        self.lease_seconds = float(lease_seconds)
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.run_store = SQLiteRunStore(
            self.state_path,
            max_payload_bytes=maximum_checkpoint_bytes,
        )
        self.audit_store = SQLiteExecutionAuditStore(self.state_path)
        self.transition_journal = SQLiteTransitionJournal(self.state_path)

        # Build the ordinary frontier runtime first to reuse its validated tool
        # executor, world model and policies, then replace only the persistence
        # implementations before a run can start.
        super().__init__(provider_router=provider_router, **kwargs)
        old_guard = self.runtime_guard
        durable_model = DurableLearnedTransitionModel(
            self.transition_journal,
            model_id=model_id,
        )
        durable_guard = ScopedGeneralizingRuntimeEpistemicGuard(
            self.tool_executor,
            policy=old_guard.policy,
            world=old_guard.world,
            transition_model=durable_model,
            audit_store=self.audit_store,
            wall_clock=self._wall_clock,
            argument_abstractor=old_guard.argument_abstractor,
        )
        self.runtime_guard = durable_guard
        self._restore_lineage_from_journal(durable_guard)

    def run(self, inputs: RunInputs):
        if inputs.run_id is None:
            raise DurableRuntimeError(
                "durable Jeeves runs require an explicit run_id for deterministic recovery"
            )
        run_id = inputs.run_id
        try:
            self.run_store.get_run(run_id)
        except RunNotFound:
            self.run_store.create_run(
                run_id,
                input={
                    "runtime": "jeeves-frontier-durable-v1",
                    "goal_id": inputs.goal.goal_id,
                    "tenant_id": inputs.tenant_id,
                    "user_id": inputs.user_id,
                    "workspace_id": inputs.workspace_id,
                    "session_id": inputs.session_id,
                },
            )
        else:
            raise DurableRuntimeError(f"durable run already exists: {run_id}")
        self.run_store.claim_run(
            run_id,
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        result = super().run(inputs)
        self._persist_terminal(result)
        return result

    def resume(self, inputs: RunInputs, run_id: str):
        run_id = require_id("run_id", run_id)
        if inputs.run_id is not None and inputs.run_id != run_id:
            raise DurableRuntimeError("RunInputs.run_id differs from requested durable run")
        durable = self.run_store.resume_state(run_id)
        if durable.checkpoint is None:
            raise DurableRuntimeError("durable run has no persisted Jeeves checkpoint")
        self.run_store.claim_run(
            run_id,
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        checkpoint = self._restore_envelope(durable.checkpoint.state)
        existing = self.checkpointer.latest(run_id)
        if existing is not None:
            if existing.fingerprint != checkpoint.fingerprint:
                self.checkpointer.clear(run_id)
            else:
                checkpoint = existing
        if self.checkpointer.latest(run_id) is None:
            self.checkpointer.save(checkpoint)
        resumed_inputs = inputs if inputs.run_id == run_id else replace(inputs, run_id=run_id)
        result = super().resume(resumed_inputs, run_id)
        self._persist_terminal(result)
        return result

    def _checkpoint(self, state) -> RunCheckpoint:
        checkpoint = super()._checkpoint(state)
        try:
            self.run_store.heartbeat(
                state.run_id,
                self.worker_id,
                lease_seconds=self.lease_seconds,
            )
        except (RunNotFound, InvalidTransition, StateConflict) as exc:
            raise DurableRuntimeError(
                "durable checkpoint lost its live worker lease"
            ) from exc
        envelope = self._capture_envelope(checkpoint)
        self.run_store.checkpoint(
            state.run_id,
            envelope,
            worker_id=self.worker_id,
            state_version=DURABLE_JEEVES_STATE_VERSION,
        )
        self.metrics.increment("agent.checkpoints.durable_saved")
        return checkpoint

    def _capture_envelope(self, checkpoint: RunCheckpoint) -> Mapping[str, Any]:
        if not isinstance(self.runtime_guard, ScopedGeneralizingRuntimeEpistemicGuard):
            raise DurableRuntimeError("durable runtime lost scoped frontier guard")
        audit = self.runtime_guard.audit_checkpoint(checkpoint.run_id)
        lineage = self.runtime_guard.model_lineage_checkpoint()
        world = _WorldStateCodec.encode(self.runtime_guard.world)
        payload = {
            "schema_version": DURABLE_JEEVES_STATE_VERSION,
            "checkpoint": _CheckpointCodec.encode(checkpoint),
            "checkpoint_fingerprint": checkpoint.fingerprint,
            "audit": audit.to_dict(),
            "model": {
                "model_id": self.runtime_guard.transition_model.model_id,
                "fingerprint": self.runtime_guard.transition_model.fingerprint,
                "lineage_count": lineage["count"],
                "lineage_hash": lineage["lineage_hash"],
            },
            "world": world,
        }
        payload = json_safe(payload)
        return {
            **payload,
            "envelope_fingerprint": stable_fingerprint(payload),
        }

    def _restore_envelope(self, envelope: Mapping[str, Any]) -> RunCheckpoint:
        raw = dict(envelope)
        supplied = str(raw.pop("envelope_fingerprint", ""))
        actual = stable_fingerprint(raw)
        if supplied != actual:
            raise DurableRuntimeError("durable Jeeves envelope fingerprint mismatch")
        if int(raw.get("schema_version", 0)) != DURABLE_JEEVES_STATE_VERSION:
            raise DurableRuntimeError("unsupported durable Jeeves checkpoint version")
        checkpoint = _CheckpointCodec.decode(raw["checkpoint"])
        if checkpoint.fingerprint != raw.get("checkpoint_fingerprint"):
            raise DurableRuntimeError("durable checkpoint fingerprint mismatch")

        _WorldStateCodec.restore(self.runtime_guard.world, raw["world"])

        # The audit/model journals may be ahead of this checkpoint after a
        # crash. Frontier resume intentionally accepts that monotonic future;
        # it rejects a missing/rewound durable root instead.
        checkpoint_audit = raw["audit"]
        ledger = self.audit_store.get(checkpoint.run_id)
        if ledger is None:
            if int(checkpoint_audit.get("event_count", 0)) != 0:
                raise DurableRuntimeError("durable checkpoint audit history is missing")
        else:
            entries = ledger.entries()
            count = int(checkpoint_audit["event_count"])
            if len(entries) < count:
                raise DurableRuntimeError("durable audit journal was truncated")
            prefix_head = "0" * 64 if count == 0 else entries[count - 1].event_hash
            if prefix_head != checkpoint_audit["head_hash"]:
                raise DurableRuntimeError("durable audit checkpoint prefix was rewritten")

        model = raw["model"]
        if model.get("model_id") != self.runtime_guard.transition_model.model_id:
            raise DurableRuntimeError("durable transition model id mismatch")
        self.runtime_guard.verify_model_lineage_checkpoint(
            count=int(model["lineage_count"]),
            lineage_hash=str(model["lineage_hash"]),
        )
        return checkpoint

    def _restore_lineage_from_journal(
        self,
        guard: ScopedGeneralizingRuntimeEpistemicGuard,
    ) -> None:
        entries = self.transition_journal.verify(guard.transition_model.model_id)
        empty_model = DurableLearnedTransitionModel(
            SQLiteTransitionJournal(self.state_path),
            model_id="jeeves-lineage-genesis-probe",
            restore=False,
        ).fingerprint
        lineage_hash = stable_fingerprint(
            {
                "kind": "jeeves-runtime-model-lineage-genesis-v1",
                "model_fingerprint": empty_model,
                "guard_policy": guard.policy.fingerprint,
            }
        )
        history: list[tuple[int, str, str]] = [(0, lineage_hash, empty_model)]
        count = 0
        for entry in entries:
            if entry.kind != "experience":
                continue
            experience = entry.payload["experience"]
            model_after = entry.model_fingerprint_after
            if model_after is None:
                raise DurableRuntimeError("transition journal has unapplied experience after replay")
            metadata = dict(experience.get("metadata", {}))
            operation_id = metadata.get("operation_id")
            if not isinstance(operation_id, str) or not operation_id:
                raise DurableRuntimeError("durable experience is missing guard operation id")
            count += 1
            lineage_hash = stable_fingerprint(
                {
                    "previous": lineage_hash,
                    "count": count,
                    "operation_id": operation_id,
                    "experience_id": experience["experience_id"],
                    "model_fingerprint": model_after,
                    "outcome": experience["outcome"],
                    "verification_score": experience["verification_score"],
                }
            )
            history.append((count, lineage_hash, model_after))
        if history[-1][2] != guard.transition_model.fingerprint:
            raise DurableRuntimeError(
                "reconstructed model lineage does not end at durable model root"
            )
        with guard._model_lineage_lock:
            guard._model_lineage_count = count
            guard._model_lineage_hash = lineage_hash
            guard._model_lineage_history = deque(
                history[-guard._MODEL_LINEAGE_HISTORY :],
                maxlen=guard._MODEL_LINEAGE_HISTORY,
            )

    def _persist_terminal(self, result) -> None:
        try:
            if result.success:
                target = RunStatus.SUCCEEDED
            elif result.reason is TerminationReason.CANCELLED:
                target = RunStatus.CANCELLED
            else:
                target = RunStatus.FAILED
            self.run_store.transition_run(
                result.run_id,
                target,
                worker_id=self.worker_id,
                output={
                    "success": result.success,
                    "reason": result.reason.value,
                    "trace_fingerprint": result.trace_fingerprint,
                },
                error=None if result.success else result.answer[:4096],
            )
        except (RunNotFound, InvalidTransition, StateConflict) as exc:
            raise DurableRuntimeError("failed to persist terminal durable run state") from exc