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
from .memory import MemoryManager, MemoryNamespace
from .memory_game import InteractionCard, MemoryGameIndex, MemoryGamePolicy
from .nuance_runtime import (
    NuanceRuntimePolicy,
    ScientificContextCompiler,
    ScientificNuanceRuntime,
)
from .semantic_maximal import MaximalLensRouter, MaximalSemanticRegistry
from .runtime import JeevesAgentRuntime, RunCheckpoint, RunInputs, _RunState
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
        lens_lab: ScientificLensLab | None = None,
        maximal_semantics: bool = False,
        memory_game_policy: MemoryGamePolicy | None = None,
        resolution_policy: ResolutionPolicy | None = None,
        wall_clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        if "context_compiler" in kwargs:
            raise TypeError(
                "scientific runtimes own context_compiler; pass scientific_context instead"
            )
        if not isinstance(maximal_semantics, bool):
            raise TypeError("maximal_semantics must be boolean")
        if maximal_semantics and (scientific_context is not None or nuance_runtime is not None):
            raise ValueError(
                "maximal_semantics owns semantic runtime construction; "
                "do not combine it with scientific_context or nuance_runtime"
            )
        if (
            lens_lab is not None
            and nuance_runtime is not None
            and nuance_runtime.lens_lab is not lens_lab
        ):
            raise ValueError(
                "lens_lab and nuance_runtime must share one ScientificLensLab"
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

        if scientific_context is None:
            if nuance_runtime is not None:
                nuance = nuance_runtime
            elif maximal_semantics:
                registry = MaximalSemanticRegistry()
                nuance = ScientificNuanceRuntime(
                    resolver,
                    semantic_registry=registry,
                    semantic_router=MaximalLensRouter(registry),
                    lens_lab=lens_lab,
                    policy=NuanceRuntimePolicy(
                        max_lenses=28,
                        max_lenses_per_family=5,
                        minimum_rare_lenses_when_supported=3,
                    ),
                )
            else:
                nuance = ScientificNuanceRuntime(resolver, lens_lab=lens_lab)
            compiler = ScientificContextCompiler(resolver, nuance=nuance)
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
            if lens_lab is not None and compiler.nuance.lens_lab is not lens_lab:
                raise ValueError(
                    "scientific_context and lens_lab refer to different lens-science planes"
                )

        self.memory_cards = cards
        self.relational_memory = relations
        self.context_resolver = resolver
        self.scientific_context = compiler
        self.nuance_runtime = compiler.nuance
        self.lens_lab = compiler.nuance.lens_lab
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
                        if isinstance(state.inputs.goal.metadata.get("domain"), str)
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

    def scientific_frame_diagnostics(self, frame_id: str) -> Mapping[str, Any]:
        return self.nuance_runtime.frame_diagnostics(frame_id)

    def _decorate_scientific_result(self, result: AgentResult) -> AgentResult:
        if not isinstance(result, AgentResult):
            raise TypeError("result must be AgentResult")
        summary = self.scientific_summary()
        metadata = dict(result.metadata)
        metadata["jeeves_scientific"] = {
            "context_compiler_fingerprint": summary[
                "context_compiler_fingerprint"
            ],
            "nuance_runtime_fingerprint": summary[
                "nuance_runtime_fingerprint"
            ],
            "maximal_semantics_enabled": summary[
                "maximal_semantics_enabled"
            ],
            "semantic_lens_count": summary["semantic_lens_count"],
            "lens_science": summary["lens_science"],
            "invariants": summary["invariants"],
        }
        return replace(result, metadata=json_safe(metadata))

    def run(self, inputs: RunInputs) -> AgentResult:
        return self._decorate_scientific_result(super().run(inputs))

    def resume(self, inputs: RunInputs, run_id: str) -> AgentResult:
        return self._decorate_scientific_result(
            super().resume(inputs, run_id)
        )

    def scientific_summary(self) -> Mapping[str, Any]:
        return {
            "context_compiler_fingerprint": self.scientific_context.fingerprint,
            "nuance_runtime_fingerprint": self.nuance_runtime.fingerprint,
            "relational_memory_count": self.relational_memory.store.count(),
            "captured_runs": tuple(sorted(self._scientific_captured_runs)),
            "lens_science": self.nuance_runtime.lens_science_summary(),
            "maximal_semantics_enabled": isinstance(
                self.nuance_runtime.semantic_registry,
                MaximalSemanticRegistry,
            ),
            "semantic_lens_count": len(self.nuance_runtime.semantic_registry.all()),
            "invariants": {
                "run_goal_memory_deferred_until_after_first_retrieval": True,
                "capture_after_initial_resolution": True,
                "resume_requires_accepted_plan_before_capture": True,
                "relational_memory_never_promotes_factual_trust": True,
                "semantic_interpretation_is_not_evidence": True,
            },
        }


class ScientificJeevesRuntime(_ScientificRuntimeMixin, JeevesAgentRuntime):
    """Deterministic Jeeves runtime with the scientific context stack enabled."""


class ScientificAdaptiveJeevesRuntime(_ScientificRuntimeMixin, AdaptiveJeevesRuntime):
    """Adaptive Jeeves runtime with the same evidence-safe scientific context."""


class MaximalScientificJeevesRuntime(ScientificJeevesRuntime):
    """Deterministic scientific runtime with the complete rare-lens catalog."""

    def __init__(self, **kwargs: Any) -> None:
        if "maximal_semantics" in kwargs:
            raise TypeError("MaximalScientificJeevesRuntime owns maximal_semantics")
        super().__init__(maximal_semantics=True, **kwargs)


class MaximalScientificAdaptiveJeevesRuntime(ScientificAdaptiveJeevesRuntime):
    """Adaptive scientific runtime with the complete rare-lens catalog."""

    def __init__(self, **kwargs: Any) -> None:
        if "maximal_semantics" in kwargs:
            raise TypeError(
                "MaximalScientificAdaptiveJeevesRuntime owns maximal_semantics"
            )
        super().__init__(maximal_semantics=True, **kwargs)
