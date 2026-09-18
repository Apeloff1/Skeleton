"""Operational bridge from the cognitive context fabric into model context.

The fabric is a retrieval/routing sidecar, not an evidence authority.  The base
ContextCompiler remains responsible for goal, plan, evidence, observations,
memory, scratch, and global context budgeting.  This adapter contributes only
bounded, provenance-visible supplemental context and interpretive routing
metadata.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .cognition import ContextCompiler, ContextSection, RunScratchpad
from .context_fabric import (
    CognitiveContextFabric,
    ContextFabricPolicy,
    ContextFabricResult,
    MemoryManagerAdapter,
)
from .evidence import EvidenceLedger
from .memory import MemoryManager, MemoryNamespace
from .memory_game_index import SourceTier
from .types import (
    AgentContractError,
    Goal,
    Plan,
    PlanStep,
    ToolObservation,
    canonical_json,
    json_safe,
    positive_int,
)


@dataclass(frozen=True, slots=True)
class FabricCompilerPolicy:
    """Prompt-facing bounds and failure semantics for the fabric sidecar."""

    maximum_records: int = 8
    maximum_record_chars: int = 3_000
    maximum_lenses: int = 6
    maximum_section_chars: int = 16_000
    section_priority: int = 60
    fail_closed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "maximum_records",
            "maximum_record_chars",
            "maximum_lenses",
            "maximum_section_chars",
        ):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=256_000),
            )
        priority = self.section_priority
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
            raise AgentContractError("section_priority must be a non-negative integer")
        if priority > 1_000_000:
            raise AgentContractError("section_priority is too large")
        if not isinstance(self.fail_closed, bool):
            raise AgentContractError("fail_closed must be boolean")


class FabricContextCompiler(ContextCompiler):
    """ContextCompiler with an operational CognitiveContextFabric sidecar.

    The sidecar may influence retrieval/query selection and provide canonical
    supplemental records.  It cannot turn a lens activation, index card, stale
    cue, or unverified source into factual evidence.
    """

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
                deep_limit=self.memory_policy.limit,
                maximum_tokens=max(1, min(6_000, self.budget.memory_chars // 4)),
                minimum_deep_trust=self.memory_policy.minimum_trust,
                lens_limit=max(1, self.fabric_policy.maximum_lenses),
            )
        )
        self._fabric_state_lock = threading.RLock()
        self._last_result: ContextFabricResult | None = None
        self._last_error: str | None = None

    def _extension_sections(
        self,
        *,
        query: str,
        goal: Goal,
        namespace: MemoryNamespace,
        memory: MemoryManager,
        evidence: EvidenceLedger,
        plan: Plan | None,
        current_step: PlanStep | None,
        observations: Sequence[ToolObservation],
        scratchpad: RunScratchpad | None,
        memory_ids: tuple[str, ...],
    ) -> tuple[ContextSection, ...]:
        del evidence, observations, scratchpad  # authority remains with base compiler
        try:
            result = self.fabric.retrieve(
                namespace.key,
                query,
                call_adapters=(MemoryManagerAdapter(memory, namespace),),
            )
            with self._fabric_state_lock:
                self._last_result = result
                self._last_error = None
            section = self._section(result, memory_ids=memory_ids)
            return () if section is None else (section,)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            with self._fabric_state_lock:
                self._last_result = None
                self._last_error = f"{type(exc).__name__}: {str(exc)[:1024]}"
            if self.fabric_policy.fail_closed:
                raise
            return ()

    def _section(
        self,
        result: ContextFabricResult,
        *,
        memory_ids: tuple[str, ...],
    ) -> ContextSection | None:
        memory_id_set = set(memory_ids)
        candidates = [
            record
            for record in result.records
            if record.trust >= self.memory_policy.minimum_trust
            and not (
                record.source_tier is SourceTier.MEMORY_STORE
                and record.source_ref in memory_id_set
            )
        ]

        activations = [
            {
                "lens_id": activation.lens.lens_id,
                "family": activation.lens.family.value,
                "authority": activation.lens.authority.value,
                "score": round(activation.score, 8),
                "matched_cues": list(activation.matched_cues[:8]),
            }
            for activation in result.lenses.activations[: self.fabric_policy.maximum_lenses]
        ]
        governance = [
            {
                "lens_id": decision.lens_id,
                "grade": decision.grade.value,
                "scientific_status": decision.scientific_status.value,
                "permissions": [item.value for item in decision.permissions],
                "predictive_weight": round(decision.predictive_weight, 8),
                "decision_feature_authorized": decision.decision_feature_authorized,
                "factual_assertion_authorized": False,
                "causal_assertion_authorized": False,
            }
            for decision in result.lens_governance[: self.fabric_policy.maximum_lenses]
        ]

        payload: dict[str, Any] = {
            "contract": {
                "authority": "context_only",
                "evidence_ledger_remains_authoritative": True,
                "records_are_not_evidence_by_inclusion": True,
                "lens_activations_are_interpretive_not_evidence": True,
                "stale_index_cards_are_not_canonical": True,
                "canonical_source_content_wins_over_index_preview": True,
            },
            "fabric_fingerprint": result.fingerprint,
            "fast_recall_fingerprint": result.fast_recall.fingerprint,
            "broad_search_used": result.broad_search_used,
            "stale_card_ids": list(result.stale_card_ids),
            "unresolved_source_refs": list(result.unresolved_source_refs),
            "lenses": activations,
            "lens_governance": governance,
            "records": [],
        }

        for record in candidates[: self.fabric_policy.maximum_records]:
            row = {
                "source_tier": record.source_tier.value,
                "source_ref": record.source_ref,
                "source_provider": record.source_provider,
                "source_fingerprint": record.source_fingerprint,
                "canonical": record.canonical,
                "trust": record.trust,
                "confidence": record.confidence,
                "salience": record.salience,
                "tags": list(record.tags),
                "content": record.content[: self.fabric_policy.maximum_record_chars],
            }
            trial = dict(payload)
            trial["records"] = [*payload["records"], row]
            if len(canonical_json(trial)) > self.fabric_policy.maximum_section_chars:
                break
            payload["records"].append(row)

        encoded = canonical_json(payload)
        if len(encoded) > self.fabric_policy.maximum_section_chars:
            payload = {
                "contract": payload["contract"],
                "fabric_fingerprint": result.fingerprint,
                "broad_search_used": result.broad_search_used,
                "stale_card_ids": list(result.stale_card_ids[:16]),
                "unresolved_source_refs": list(result.unresolved_source_refs[:16]),
                "records": [],
            }
            encoded = canonical_json(payload)

        if not (
            payload.get("records")
            or result.fast_recall.all_hits
            or result.stale_card_ids
            or result.unresolved_source_refs
            or activations
        ):
            return None

        source_ids = tuple(
            dict.fromkeys(
                record.source_ref
                for record in candidates[: self.fabric_policy.maximum_records]
            )
        )
        return ContextSection(
            "context_fabric",
            encoded,
            priority=self.fabric_policy.section_priority,
            source_ids=source_ids,
        )

    def last_fabric_snapshot(self) -> Mapping[str, Any]:
        """Return bounded operational state without exposing prompt contents."""

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
