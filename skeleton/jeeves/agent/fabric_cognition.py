"""Default-runtime wrapper for Jeeves' canonical cognitive context fabric.

The base :class:`ContextCompiler` owns the rendering contract.  This wrapper
only supplies a fabric by default, records operational status, and decides
whether a fabric failure may fall back to legacy memory retrieval.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .cognition import (
    ContextCompiler,
    ContextPacket,
    ContextSection,
    RunScratchpad,
)
from .context_fabric import (
    CognitiveContextFabric,
    ContextFabricPolicy,
    ContextFabricResult,
)
from .evidence import EvidenceLedger
from .memory import MemoryManager, MemoryNamespace
from .types import (
    AgentContractError,
    Goal,
    Plan,
    PlanStep,
    ToolObservation,
    json_safe,
    positive_int,
)


@dataclass(frozen=True, slots=True)
class FabricCompilerPolicy:
    """Operational bounds for the default runtime fabric."""

    maximum_records: int = 8
    maximum_lenses: int = 6
    maximum_tokens: int = 6_000
    fail_closed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_records",
            positive_int("maximum_records", self.maximum_records, maximum=1_000),
        )
        object.__setattr__(
            self,
            "maximum_lenses",
            positive_int("maximum_lenses", self.maximum_lenses, maximum=1_000),
        )
        object.__setattr__(
            self,
            "maximum_tokens",
            positive_int("maximum_tokens", self.maximum_tokens, maximum=1_000_000),
        )
        if not isinstance(self.fail_closed, bool):
            raise AgentContractError("fail_closed must be boolean")


class FabricContextCompiler(ContextCompiler):
    """ContextCompiler that uses one CognitiveContextFabric by default."""

    def __init__(
        self,
        *,
        fabric: CognitiveContextFabric | None = None,
        fabric_policy: FabricCompilerPolicy | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if fabric is not None and not isinstance(fabric, CognitiveContextFabric):
            raise TypeError("fabric must be CognitiveContextFabric or None")
        self.fabric_policy = fabric_policy or FabricCompilerPolicy()
        self.fabric = fabric or CognitiveContextFabric(
            policy=ContextFabricPolicy(
                fast_limit=self.fabric_policy.maximum_records,
                associative_limit=self.fabric_policy.maximum_records,
                deep_limit=self.fabric_policy.maximum_records,
                maximum_tokens=max(
                    1,
                    min(
                        self.fabric_policy.maximum_tokens,
                        self.budget.memory_chars // 4,
                    ),
                ),
                minimum_deep_trust=self.memory_policy.minimum_trust,
                lens_limit=self.fabric_policy.maximum_lenses,
            )
        )
        self._fabric_state_lock = threading.RLock()
        self._last_result: ContextFabricResult | None = None
        self._last_error: str | None = None

    def compile(
        self,
        *,
        system_instruction: str,
        task_instruction: str,
        goal: Goal,
        namespace: MemoryNamespace,
        memory: MemoryManager,
        evidence: EvidenceLedger,
        plan: Plan | None = None,
        current_step: PlanStep | None = None,
        observations: Sequence[ToolObservation] = (),
        scratchpad: RunScratchpad | None = None,
        extra_sections: Sequence[ContextSection] = (),
        context_fabric: CognitiveContextFabric | None = None,
    ) -> ContextPacket:
        if context_fabric is not None and context_fabric is not self.fabric:
            raise ValueError(
                "FabricContextCompiler owns its fabric; pass a custom ContextCompiler "
                "when per-call fabric replacement is required"
            )
        try:
            return super().compile(
                system_instruction=system_instruction,
                task_instruction=task_instruction,
                goal=goal,
                namespace=namespace,
                memory=memory,
                evidence=evidence,
                plan=plan,
                current_step=current_step,
                observations=observations,
                scratchpad=scratchpad,
                extra_sections=extra_sections,
                context_fabric=self.fabric,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            with self._fabric_state_lock:
                fabric_error = self._last_error
            if fabric_error is None or self.fabric_policy.fail_closed:
                raise
            return super().compile(
                system_instruction=system_instruction,
                task_instruction=task_instruction,
                goal=goal,
                namespace=namespace,
                memory=memory,
                evidence=evidence,
                plan=plan,
                current_step=current_step,
                observations=observations,
                scratchpad=scratchpad,
                extra_sections=extra_sections,
                context_fabric=None,
            )

    def _retrieve_context_fabric(
        self,
        context_fabric: CognitiveContextFabric,
        *,
        namespace: MemoryNamespace,
        query: str,
        memory: MemoryManager,
    ) -> ContextFabricResult:
        try:
            result = super()._retrieve_context_fabric(
                context_fabric,
                namespace=namespace,
                query=query,
                memory=memory,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            with self._fabric_state_lock:
                self._last_result = None
                self._last_error = f"{type(exc).__name__}: {str(exc)[:1024]}"
            raise
        with self._fabric_state_lock:
            self._last_result = result
            self._last_error = None
        return result

    def last_fabric_snapshot(self) -> Mapping[str, Any]:
        """Return bounded operational state without exposing context contents."""

        with self._fabric_state_lock:
            result = self._last_result
            error = self._last_error
        if result is None:
            return json_safe(
                {
                    "ok": error is None,
                    "error": error,
                    "fingerprint": None,
                    "record_count": 0,
                    "broad_search_used": False,
                    "stale_card_count": 0,
                    "unresolved_source_count": 0,
                }
            )
        return json_safe(
            {
                "ok": True,
                "error": None,
                "fingerprint": result.fingerprint,
                "record_count": len(result.records),
                "broad_search_used": result.broad_search_used,
                "stale_card_count": len(result.stale_card_ids),
                "unresolved_source_count": len(result.unresolved_source_refs),
                "lens_ids": list(result.lenses.ids()[: self.fabric_policy.maximum_lenses]),
            }
        )


__all__ = [
    "FabricCompilerPolicy",
    "FabricContextCompiler",
]
