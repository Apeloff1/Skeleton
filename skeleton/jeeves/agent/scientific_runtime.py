"""Frontier Jeeves runtimes with scientific context and nuance enabled.

The base Jeeves runtime remains the authority for tools, budgets, evidence,
verification, and checkpoints. These classes only replace the prompt-context
compiler and add post-resolution interaction capture.

The capture order is intentional:

    first planning retrieval -> accepted plan -> capture current user goal

This prevents the current goal from satisfying its own "memory" query while
making it available as an episodic cue to later reasoning steps and future runs.
"""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

from .adaptive_runtime import AdaptiveJeevesRuntime
from .relational_memory import RelationalMemoryIndex
from .context_pipeline import ContextSourceAdapter, LayeredContextResolver, ResolutionPolicy
from .context_repository import ContextRepository
from .interpretive_science import ScientificLensLab
from .lens_governance import LensScienceRegistry
from .memory import MemoryManager, MemoryNamespace
from .memory_game import InteractionCard, MemoryGameIndex, MemoryGamePolicy
from .nuance_runtime import (
    ScientificContextCompiler,
    ScientificNuanceRuntime,
)
from .runtime import JeevesAgentRuntime, RunCheckpoint, RunInputs, _RunState
from .semantic_governance_bridge import SemanticGovernanceBridge
from .semantic_lenses import SemanticFinding, SemanticObservation
from .semantic_plane import (
    SemanticLensPlane,
    SemanticPlaneLearningUpdate,
    SemanticPlaneSnapshot,
)
from .types import AgentResult, EvidenceRef, MemoryKind, json_safe


class _ScientificRuntimeMixin:
    """Shared wiring for deterministic and adaptive runtime variants."""

    scientific_context: ScientificContextCompiler

    def __init__(
        self,
        *,
        memory: MemoryManager | None = None,
        memory_cards: MemoryGameIndex | None = None,
        relational_memory: RelationalMemoryIndex | None = None,
        context_resolver: LayeredContextResolver | None = None,
        context_repository: ContextRepository | None = None,
        context_adapters: Sequence[ContextSourceAdapter] = (),
        scientific_context: ScientificContextCompiler | None = None,
        nuance_runtime: ScientificNuanceRuntime | None = None,
        semantic_plane: SemanticLensPlane | None = None,
        lens_lab: ScientificLensLab | None = None,
        memory_game_policy: MemoryGamePolicy | None = None,
        resolution_policy: ResolutionPolicy | None = None,
        wall_clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        if "context_compiler" in kwargs:
            raise TypeError(
                "scientific runtimes own context_compiler; pass scientific_context instead"
            )
        if (
            semantic_plane is not None
            and lens_lab is not None
            and semantic_plane.governance.registry.lab is not lens_lab
        ):
            raise ValueError(
                "semantic_plane and lens_lab must share one ScientificLensLab"
            )
        shared_memory = memory or MemoryManager(clock=wall_clock)
        cards = memory_cards or MemoryGameIndex(
            policy=memory_game_policy,
            clock=wall_clock,
        )
        relations = relational_memory or RelationalMemoryIndex(cards, clock=wall_clock)

        if context_resolver is None:
            resolver = LayeredContextResolver(
                cards=cards,
                memory=shared_memory,
                repository=context_repository,
                relations=relations,
                adapters=context_adapters,
                policy=resolution_policy,
            )
        else:
            if context_repository is not None or context_adapters:
                raise ValueError(
                    "context_repository/context_adapters are only valid when "
                    "context_resolver is not supplied"
                )
            resolver = context_resolver
            if resolver.memory is not shared_memory:
                raise ValueError(
                    "context_resolver must share the exact runtime MemoryManager"
                )
            if resolver.cards is not cards and memory_cards is not None:
                raise ValueError(
                    "context_resolver and memory_cards refer to different L0 indexes"
                )
            cards = resolver.cards
            if resolver.relations is None:
                if relational_memory is not None:
                    if relational_memory.cards is not cards:
                        raise ValueError(
                            "relational_memory must use context_resolver cards"
                        )
                    relations = relational_memory
                else:
                    relations = RelationalMemoryIndex(cards, clock=wall_clock)
                resolver.relations = relations
            elif relational_memory is not None and resolver.relations is not relational_memory:
                raise ValueError(
                    "context_resolver and relational_memory refer to different indexes"
                )
            else:
                relations = resolver.relations

        if semantic_plane is not None:
            plane = semantic_plane
        elif (
            scientific_context is not None
            and scientific_context.semantic_plane is not None
        ):
            plane = scientific_context.semantic_plane
        elif lens_lab is None:
            plane = SemanticLensPlane()
        else:
            plane = SemanticLensPlane(
                governance=SemanticGovernanceBridge(
                    LensScienceRegistry(lab=lens_lab)
                )
            )
        if (
            lens_lab is not None
            and plane.governance.registry.lab is not lens_lab
        ):
            raise ValueError(
                "semantic plane and lens_lab must share one ScientificLensLab"
            )

        if scientific_context is None:
            nuance = nuance_runtime or ScientificNuanceRuntime(resolver)
            compiler = ScientificContextCompiler(
                resolver,
                nuance=nuance,
                semantic_plane=plane,
            )
        else:
            compiler = scientific_context
            if compiler.resolver is not resolver:
                raise ValueError(
                    "scientific_context and context_resolver must share one resolver"
                )
            if nuance_runtime is not None and compiler.nuance is not nuance_runtime:
                raise ValueError(
                    "scientific_context and nuance_runtime refer to different nuance planes"
                )
            if compiler.semantic_plane is None:
                compiler.semantic_plane = plane
            elif compiler.semantic_plane is not plane:
                raise ValueError(
                    "scientific_context and semantic_plane refer to different semantic planes"
                )

        self.memory_cards = cards
        self.relational_memory = relations
        self.context_resolver = resolver
        self.scientific_context = compiler
        self.nuance_runtime = compiler.nuance
        self.semantic_plane = plane
        self.lens_lab = plane.governance.registry.lab
        self._scientific_capture_lock = threading.RLock()
        self._scientific_captured_runs: set[str] = set()

        super().__init__(
            memory=shared_memory,
            context_compiler=compiler,
            wall_clock=wall_clock,
            **kwargs,
        )

    def _remember_working(
        self,
        namespace: MemoryNamespace,
        content: str,
        *,
        kind: MemoryKind = MemoryKind.WORKING,
        source: str,
        tags: Sequence[str],
        trust: float,
        salience: float,
        evidence: Sequence[EvidenceRef] = (),
    ) -> None:
        # The base runtime stores source=run-goal from _new_state(), before the
        # first planning retrieval. Scientific runtimes defer that current-turn
        # memory so the goal cannot satisfy its own prior-context query.
        if source == "run-goal":
            return
        super()._remember_working(
            namespace,
            content,
            kind=kind,
            source=source,
            tags=tags,
            trust=trust,
            salience=salience,
            evidence=evidence,
        )

    @staticmethod
    def _interaction_tags(inputs: RunInputs) -> tuple[str, ...]:
        tags = {"user-intent", "run-goal"}
        for key in ("domain", "task", "mode"):
            value = inputs.goal.metadata.get(key)
            if isinstance(value, str) and value.strip():
                tags.add(value.strip().casefold()[:128])
        for value in inputs.metadata.get("context_tags", ()):
            if isinstance(value, str) and value.strip():
                tags.add(value.strip().casefold()[:128])
        return tuple(sorted(tags))

    def _existing_run_card(
        self,
        namespace: MemoryNamespace,
        run_id: str,
    ) -> InteractionCard | None:
        for card in self.memory_cards.store.namespace_cards(namespace):
            if card.metadata.get("captured_run_id") == run_id:
                return card
        return None

    def _capture_run_interaction(self, state: _RunState) -> InteractionCard:
        with self._scientific_capture_lock:
            if state.run_id in self._scientific_captured_runs:
                existing = self._existing_run_card(state.inputs.namespace, state.run_id)
                if existing is not None:
                    return existing
            existing = self._existing_run_card(state.inputs.namespace, state.run_id)
            if existing is not None:
                self._scientific_captured_runs.add(state.run_id)
                return existing

            card = self.scientific_context.capture_user_interaction(
                state.inputs.namespace,
                state.inputs.goal.objective,
                context_tags=self._interaction_tags(state.inputs),
                metadata={
                    "captured_run_id": state.run_id,
                    "goal_id": state.inputs.goal.goal_id,
                    "domain": (
                        state.inputs.goal.metadata.get("domain")
                        if isinstance(
                            state.inputs.goal.metadata.get("domain"),
                            str,
                        )
                        else None
                    ),
                    "semantic_scope": "user_intent",
                    "is_evidence": False,
                    "capture_boundary": "after_initial_plan_resolution",
                },
            )
            self._scientific_captured_runs.add(state.run_id)
            state.trace.emit(
                "context.user_interaction_captured",
                {
                    "card_id": card.card_id,
                    "run_id": state.run_id,
                    "goal_id": state.inputs.goal.goal_id,
                    "context_compiler": self.scientific_context.fingerprint,
                    "is_evidence": False,
                },
            )
            return card

    def _plan(self, state: _RunState) -> None:
        # super()._plan performs the first scientific context retrieval. Only
        # after that retrieval and successful plan acceptance may the current
        # goal become an episodic card.
        super()._plan(state)
        self._capture_run_interaction(state)

    def _state_from_checkpoint(
        self,
        inputs: RunInputs,
        checkpoint: RunCheckpoint,
    ) -> _RunState:
        state = super()._state_from_checkpoint(inputs, checkpoint)
        # The initial CREATED checkpoint predates planning retrieval. Only an
        # accepted plan proves the first retrieval boundary has been crossed.
        if state.plan is not None:
            self._capture_run_interaction(state)
        return state

    def analyze_semantics(
        self,
        observations: Sequence[SemanticObservation],
        *,
        findings: Sequence[SemanticFinding] = (),
        requested: Sequence[str] = (),
        base_rate: float | None = None,
        sequence: int = 0,
        domain: str | None = None,
    ) -> SemanticPlaneSnapshot:
        return self.semantic_plane.analyze(
            observations,
            findings=findings,
            requested=requested,
            base_rate=base_rate,
            sequence=sequence,
            domain=domain,
        )

    def resolve_semantic_forecast(
        self,
        forecast_id: str,
        *,
        outcome: bool,
        domain: str,
        independent_run: str,
        observed_at: float | None = None,
        observation_id: str | None = None,
        negative_control: bool = False,
    ) -> SemanticPlaneLearningUpdate:
        return self.semantic_plane.resolve_forecast(
            forecast_id,
            outcome=outcome,
            domain=domain,
            independent_run=independent_run,
            observed_at=observed_at,
            observation_id=observation_id,
            negative_control=negative_control,
        )

    def _decorate_scientific_result(self, result: AgentResult) -> AgentResult:
        if not isinstance(result, AgentResult):
            raise TypeError("result must be AgentResult")
        metadata = dict(result.metadata)
        metadata["jeeves_scientific"] = self.scientific_summary()
        return replace(result, metadata=json_safe(metadata))

    def run(self, inputs: RunInputs) -> AgentResult:
        return self._decorate_scientific_result(super().run(inputs))

    def resume(self, inputs: RunInputs, run_id: str) -> AgentResult:
        return self._decorate_scientific_result(
            super().resume(inputs, run_id)
        )

    def scientific_summary(self) -> Mapping[str, Any]:
        statuses = {
            key: value.value
            for key, value in self.lens_lab.status_map().items()
        }
        return {
            "context_compiler_fingerprint": self.scientific_context.fingerprint,
            "nuance_runtime_fingerprint": self.nuance_runtime.fingerprint,
            "semantic_plane_fingerprint": self.semantic_plane.fingerprint,
            "semantic_lens_count": len(self.semantic_plane.registry.all()),
            "semantic_forecasts_open": len(
                self.semantic_plane.prediction_ledger.open()
            ),
            "semantic_forecasts_resolved": len(
                self.semantic_plane.prediction_ledger.resolved()
            ),
            "semantic_calibrated_lens_count": len(statuses),
            "semantic_lens_statuses": statuses,
            "lens_lab_fingerprint": self.lens_lab.fingerprint,
            "relational_memory_count": self.relational_memory.store.count(),
            "captured_runs": tuple(sorted(self._scientific_captured_runs)),
            "invariants": {
                "run_goal_memory_deferred_until_after_first_retrieval": True,
                "capture_after_initial_resolution": True,
                "resume_requires_accepted_plan_before_capture": True,
                "relational_memory_never_promotes_factual_trust": True,
                "semantic_interpretation_is_not_evidence": True,
                "semantic_plane_is_governed": True,
                "semantic_target_fusions_are_target_bounded": True,
                "semantic_calibration_retains_forecast_custody": True,
            },
        }


class ScientificJeevesRuntime(_ScientificRuntimeMixin, JeevesAgentRuntime):
    """Deterministic Jeeves runtime with the scientific context stack enabled."""


class ScientificAdaptiveJeevesRuntime(_ScientificRuntimeMixin, AdaptiveJeevesRuntime):
    """Adaptive Jeeves runtime with the same evidence-safe scientific context."""
