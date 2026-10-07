"""Year-aware engineering signals for local-model serving policy.

Signals are evidence metadata, not feature flags. Experimental research never becomes
an execution default merely because it is newer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json


class SignalMaturity(str, Enum):
    ESTABLISHED = "established"
    VALIDATED = "validated"
    EMERGING = "emerging"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True, slots=True)
class RuntimeSignal:
    signal_id: str
    year: int
    capability: str
    maturity: SignalMaturity
    provenance: str
    production_default: bool = False

    def __post_init__(self) -> None:
        if not self.signal_id or not self.capability or not self.provenance:
            raise ValueError("complete runtime signal required")
        if not 2020 <= self.year <= 2100:
            raise ValueError("runtime signal year outside supported range")
        if self.production_default and self.maturity not in {
            SignalMaturity.ESTABLISHED, SignalMaturity.VALIDATED
        }:
            raise ValueError("emerging/experimental signal cannot be a production default")


_SIGNALS = (
    RuntimeSignal(
        "continuous-batching", 2023, "iteration_level_scheduling",
        SignalMaturity.ESTABLISHED, "Orca/vLLM serving lineage", True,
    ),
    RuntimeSignal(
        "paged-kv-memory", 2023, "paged_kv_memory",
        SignalMaturity.ESTABLISHED, "vLLM PagedAttention lineage", True,
    ),
    RuntimeSignal(
        "prefix-aware-routing", 2024, "prefix_affinity",
        SignalMaturity.VALIDATED, "Preble arXiv:2407.00023", True,
    ),
    RuntimeSignal(
        "kv-centric-serving", 2024, "tiered_kv_reuse",
        SignalMaturity.VALIDATED, "Mooncake arXiv:2407.00079", True,
    ),
    RuntimeSignal(
        "prefill-decode-disaggregation", 2024, "phase_disaggregation",
        SignalMaturity.VALIDATED, "P/D-Serve arXiv:2408.08147", False,
    ),
    RuntimeSignal(
        "speculative-decoding-serving", 2024, "speculative_decoding",
        SignalMaturity.VALIDATED, "speculative decoding serving lineage", False,
    ),
    RuntimeSignal(
        "chunked-prefill", 2024, "chunked_prefill",
        SignalMaturity.VALIDATED, "Sarathi-Serve arXiv:2403.02310", True,
    ),
    RuntimeSignal(
        "slo-aware-admission", 2024, "slo_admission",
        SignalMaturity.VALIDATED, "Mooncake arXiv:2407.00079", True,
    ),
    RuntimeSignal(
        "kv-compression", 2025, "kv_compression",
        SignalMaturity.EXPERIMENTAL, "arXiv:2503.24000 production caveats", False,
    ),
    RuntimeSignal(
        "heterogeneous-pd-serving", 2025, "heterogeneous_phase_placement",
        SignalMaturity.EMERGING, "arXiv:2509.17542", False,
    ),
    RuntimeSignal(
        "agentic-fine-disaggregation", 2026, "attention_ffn_phase_specialization",
        SignalMaturity.EXPERIMENTAL, "HeteroPanacea arXiv:2608.03741", False,
    ),
    RuntimeSignal(
        "phase-specialized-quantization", 2026, "disaggregated_quantization",
        SignalMaturity.EXPERIMENTAL, "arXiv:2609.26333", False,
    ),
)


class RuntimeSignalRegistry:
    def __init__(self, signals: tuple[RuntimeSignal, ...] = _SIGNALS) -> None:
        ids = [signal.signal_id for signal in signals]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate runtime signal identity")
        self._signals = tuple(sorted(signals, key=lambda s: (s.year, s.signal_id)))

    def through_year(self, year: int) -> tuple[RuntimeSignal, ...]:
        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError("integer signal year required")
        return tuple(signal for signal in self._signals if signal.year <= year)

    def production_policy(self, year: int) -> tuple[str, ...]:
        return tuple(
            signal.capability for signal in self.through_year(year)
            if signal.production_default
        )

    def candidates(self, year: int) -> tuple[RuntimeSignal, ...]:
        return tuple(
            signal for signal in self.through_year(year)
            if not signal.production_default
        )

    def snapshot(self, year: int) -> dict[str, object]:
        signals = self.through_year(year)
        body = {
            "schema": "skeleton.ai.runtime-signals.v1",
            "through_year": year,
            "signals": [
                {
                    "id": s.signal_id,
                    "year": s.year,
                    "capability": s.capability,
                    "maturity": s.maturity.value,
                    "provenance": s.provenance,
                    "production_default": s.production_default,
                }
                for s in signals
            ],
        }
        body["digest"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return body


DEFAULT_RUNTIME_SIGNALS = RuntimeSignalRegistry()

__all__ = [
    "DEFAULT_RUNTIME_SIGNALS",
    "RuntimeSignal",
    "RuntimeSignalRegistry",
    "SignalMaturity",
]
