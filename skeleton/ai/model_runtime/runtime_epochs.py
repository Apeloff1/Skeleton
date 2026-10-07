"""Decade-scale capability epochs for deterministic AI runtime policy.

Epochs describe architectural inheritance. Historical epochs are descriptive; future
epochs are forecast-only and cannot become production defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json


class EpochStatus(str, Enum):
    HISTORICAL = "historical"
    CURRENT = "current"
    FORECAST = "forecast"


@dataclass(frozen=True, slots=True)
class RuntimeEpoch:
    decade: int
    status: EpochStatus
    capabilities: tuple[str, ...]
    thesis: str

    def __post_init__(self) -> None:
        if self.decade % 10 or not 1950 <= self.decade <= 2100:
            raise ValueError("epoch must be a supported decade boundary")
        if not self.capabilities or len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("epoch capabilities must be unique and non-empty")
        if not self.thesis:
            raise ValueError("epoch thesis required")
        if self.status is EpochStatus.FORECAST and self.decade <= 2020:
            raise ValueError("historical decade cannot be forecast")


_EPOCHS = (
    RuntimeEpoch(1950, EpochStatus.HISTORICAL, (
        "symbolic_search", "finite_state_computation", "information_theory",
    ), "Formal computation, search, and information foundations."),
    RuntimeEpoch(1960, EpochStatus.HISTORICAL, (
        "interactive_computing", "early_nlp", "knowledge_representation",
    ), "Interactive systems and early language/knowledge machinery."),
    RuntimeEpoch(1970, EpochStatus.HISTORICAL, (
        "relational_data", "expert_systems", "backprop_foundations",
    ), "Structured data and rule-based intelligence foundations."),
    RuntimeEpoch(1980, EpochStatus.HISTORICAL, (
        "distributed_systems", "connectionism", "probabilistic_reasoning",
    ), "Distributed computation and revived neural/probabilistic methods."),
    RuntimeEpoch(1990, EpochStatus.HISTORICAL, (
        "statistical_nlp", "web_scale_information", "accelerated_linear_algebra",
    ), "Statistical learning meets web-scale information and faster compute."),
    RuntimeEpoch(2000, EpochStatus.HISTORICAL, (
        "large_scale_ml", "gpu_compute", "distributed_storage", "web_crawling",
    ), "Commodity parallelism and internet-scale data infrastructure."),
    RuntimeEpoch(2010, EpochStatus.HISTORICAL, (
        "deep_learning", "transformer_attention", "representation_learning",
        "hardware_acceleration", "large_scale_pretraining",
    ), "Deep representation learning, accelerators, and transformer pretraining."),
    RuntimeEpoch(2020, EpochStatus.CURRENT, (
        "foundation_models", "instruction_tuning", "retrieval_augmentation",
        "tool_use", "continuous_batching", "paged_kv_memory", "prefix_caching",
        "speculative_decoding", "mixture_of_experts", "multimodal_models",
        "agentic_runtime", "prefill_decode_disaggregation",
    ), "Foundation-model systems become serving, retrieval, tool, and agent runtimes."),
    RuntimeEpoch(2030, EpochStatus.FORECAST, (
        "adaptive_runtime_topology", "verified_self_optimization",
        "cross_modal_world_models", "hardware_software_codesign",
    ), "Forecast candidates only; no automatic production authority."),
    RuntimeEpoch(2040, EpochStatus.FORECAST, (
        "autonomous_architecture_search", "persistent_world_simulation",
        "formal_runtime_governance",
    ), "Long-horizon forecast candidates requiring future evidence."),
)


class RuntimeEpochRegistry:
    def __init__(self, epochs: tuple[RuntimeEpoch, ...] = _EPOCHS) -> None:
        decades = [epoch.decade for epoch in epochs]
        if len(decades) != len(set(decades)):
            raise ValueError("duplicate runtime epoch")
        self._epochs = tuple(sorted(epochs, key=lambda epoch: epoch.decade))

    def through_decade(self, decade: int, *, include_forecast: bool = False) -> tuple[RuntimeEpoch, ...]:
        if isinstance(decade, bool) or not isinstance(decade, int) or decade % 10:
            raise ValueError("integer decade boundary required")
        return tuple(
            epoch for epoch in self._epochs
            if epoch.decade <= decade and (include_forecast or epoch.status is not EpochStatus.FORECAST)
        )

    def inherited_capabilities(self, decade: int) -> tuple[str, ...]:
        capabilities: set[str] = set()
        for epoch in self.through_decade(decade):
            capabilities.update(epoch.capabilities)
        return tuple(sorted(capabilities))

    def snapshot(self, decade: int, *, include_forecast: bool = False) -> dict[str, object]:
        epochs = self.through_decade(decade, include_forecast=include_forecast)
        body = {
            "schema": "skeleton.ai.runtime-epochs.v1",
            "through_decade": decade,
            "include_forecast": include_forecast,
            "epochs": [
                {
                    "decade": epoch.decade,
                    "status": epoch.status.value,
                    "capabilities": list(epoch.capabilities),
                    "thesis": epoch.thesis,
                }
                for epoch in epochs
            ],
        }
        body["digest"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return body


DEFAULT_RUNTIME_EPOCHS = RuntimeEpochRegistry()

__all__ = ["DEFAULT_RUNTIME_EPOCHS", "EpochStatus", "RuntimeEpoch", "RuntimeEpochRegistry"]
