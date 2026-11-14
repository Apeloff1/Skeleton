"""Finite training counters; distinguishes actual optimization from task counts."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import number



@dataclass(frozen=True, slots=True)
class TrainingMetrics:
    lines: int
    actual_optimizer_steps: int
    elapsed_ms: int
    checkpoint_bytes: int
    unknown_token_fraction_ppm: int
    source_domains: int
    validation_items: int
    holdout_items: int

    def __post_init__(self) -> None:
        for name, min_value, max_value in (
            ("lines", 0, 576), ("actual_optimizer_steps", 0, 1000000),
            ("elapsed_ms", 0, 36000000), ("checkpoint_bytes", 0, 256000000),
            ("unknown_token_fraction_ppm", 0, 1000000),
            ("source_domains", 0, 24), ("validation_items", 0, 576),
            ("holdout_items", 0, 576),
        ):
            number(getattr(self, name), name, min_value, max_value)

    def record(self) -> dict:
        return {**{k: getattr(self, k) for k in self.__dataclass_fields__},
                "validation_score": None, "holdout_score": None,
                "native_device_qualified": False,
                "production_authorized": False}
