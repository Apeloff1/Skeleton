"""Proof of bounded single-device training budgets with no background effects."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import number
from .errors import deny


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    maximum_memory_bytes: int = 1000000000
    maximum_model_bytes: int = 256000000
    maximum_gradient_steps: int = 16384
    maximum_wall_ms: int = 3600000
    maximum_examples: int = 576

    def __post_init__(self) -> None:
        for key, lo, hi in (
            ("maximum_memory_bytes", 1048576, 16000000000),
            ("maximum_model_bytes", 1, 256000000),
            ("maximum_gradient_steps", 1, 1000000),
            ("maximum_wall_ms", 1, 36000000),
            ("maximum_examples", 1, 576),
        ):
            number(getattr(self, key), key, lo, hi)

    def admit(self, *, model_bytes: int, steps: int, examples: int,
              estimated_working_bytes: int) -> dict:
        for key, value, bound in (
            ("model", model_bytes, self.maximum_model_bytes),
            ("steps", steps, self.maximum_gradient_steps),
            ("examples", examples, self.maximum_examples),
            ("working", estimated_working_bytes, self.maximum_memory_bytes),
        ):
            if type(value) is not int or not 1 <= value <= bound:
                deny("resource-" + key)
        return {"admitted": True, "working_bytes": estimated_working_bytes,
                "model_bytes": model_bytes, "steps": steps, "examples": examples,
                "device_validated": False}
