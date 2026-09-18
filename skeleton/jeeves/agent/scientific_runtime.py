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
from typing import Any, Callable, Mapping, Sequence

from .adaptive_runtime import AdaptiveJeevesRuntime
from .associative_memory import AssociativeMemoryMesh
from .context_pipeline import ContextSourceAdapter, LayeredContextResolver, ResolutionPolicy
from .context_repository import ContextRepository
from .memory import MemoryManager, MemoryNamespace
from .memory_game import InteractionCard, MemoryGameIndex, MemoryGamePolicy
from .nuance_runtime import (
    ScientificContextCompiler,
    ScientificNuanceRuntime,
)
from .runtime import JeevesAgentRuntime, RunCheckpoint, RunInputs, _RunState


class _ScientificRuntimeMixin:
    """Shared wiring for deterministic and adaptive runtime variants."""

    scientific_context: ScientificContextCompiler

    def __init__(
        self,
        *,
        memory: MemoryManager | None = None,
        memory_cards: MemoryGameIndex | None = None,
        associative_memory: AssociativeMemoryMesh | None = None,
        context_resolver: LayeredContextResolver | None = None,
        context_repository: ContextRepository | None = None,
        context_adapters: Sequence[ContextSourceAdapter] = (),
        scientific_context: ScientificContextCompiler | None = None,
        nuance_runtime: ScientificNuanceRuntime | None = None,
        memory_game_policy: MemoryGamePolicy | None = None,
        resolution_policy: ResolutionPolicy | None = None,
        wall_clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        if "context_compiler" in kwargs:
            raise TypeError(
                "scientific runtimes own context_compiler; pass scientific_context instead"
            )
        shared_memory = memory or MemoryManager(clock=wall_clock)
        cards = memory_cards or MemoryGameIndex(
            policy=memory_game_policy,
            clock=wall_clock,
        )
        associations = associative_memory or AssociativeMemoryMesh(clock=wall_clock)

        if context_resolver is None:
            resolver = LayeredContextResolver(
                cards=cards,
                memory=shared_memory,
                repository=context_repository,
                associations=associations,
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
            if resolver.associations is None:
                resolver.associations = associations
            else:
                associations = resolver.associations

        if scientific_context is None:
            nuance = nuance_runtime or ScientificNuanceRuntime(resolver)
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

        self.memory_cards = cards
        self.associative_memory = associations
        self.context_resolver = resolver
        self.scientific_context = compiler
        self.nuance_runtime = compiler.nuance
        self._scientific_capture_lock = threading.RLock()
        self._scientific_captured_runs: set[str] = set()

        super().__init__(
            memory=shared_memory,
            context_compiler=compiler,
            wall_clock=wall_clock,
            **kwargs,
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
        # A resumed checkpoint necessarily postdates the original first-turn
        # retrieval. Restoring a missing run card is therefore leakage-safe.
        self._capture_run_interaction(state)
        return state

    def scientific_summary(self) -> Mapping[str, Any]:
        return {
            "context_compiler_fingerprint": self.scientific_context.fingerprint,
            "nuance_runtime_fingerprint": self.nuance_runtime.fingerprint,
            "associative_memory_fingerprint": self.associative_memory.fingerprint,
            "captured_runs": tuple(sorted(self._scientific_captured_runs)),
            "invariants": {
                "capture_after_initial_resolution": True,
                "association_never_promotes_trust": True,
                "semantic_interpretation_is_not_evidence": True,
            },
        }


class ScientificJeevesRuntime(_ScientificRuntimeMixin, JeevesAgentRuntime):
    """Deterministic Jeeves runtime with the scientific context stack enabled."""


class ScientificAdaptiveJeevesRuntime(_ScientificRuntimeMixin, AdaptiveJeevesRuntime):
    """Adaptive Jeeves runtime with the same evidence-safe scientific context."""
