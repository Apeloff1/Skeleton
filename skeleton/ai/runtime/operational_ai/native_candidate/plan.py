"""Immutable admission policy for genuine candidate-only native SGD."""
from __future__ import annotations
from dataclasses import dataclass
from .strict import digest, identity, number
from .errors import deny


@dataclass(frozen=True, slots=True)
class TrainingPlan:
    run_id: str
    expected_base_model_sha256: str
    expected_tokenizer_sha256: str
    learning_rate_ppm: int = 10000
    max_optimizer_steps: int = 16384
    batch_lines: int = 8
    maximum_total_ms: int = 3600000
    max_line_bytes: int = 4096
    min_known_token_fraction_ppm: int = 800000
    maximum_checkpoint_bytes: int = 256000000
    operator_approved: bool = False
    output_kind: str = "candidate-only"

    def __post_init__(self) -> None:
        from .strict import sha
        identity(self.run_id, "run-id")
        sha(self.expected_base_model_sha256, "base")
        sha(self.expected_tokenizer_sha256, "tokenizer")
        for key, lo, hi in (
            ("learning_rate_ppm", 1, 100000),
            ("max_optimizer_steps", 1, 1000000),
            ("batch_lines", 1, 128),
            ("maximum_total_ms", 1, 36000000),
            ("max_line_bytes", 1, 16384),
            ("min_known_token_fraction_ppm", 0, 1000000),
            ("maximum_checkpoint_bytes", 1, 256000000),
        ):
            number(getattr(self, key), key, lo, hi)
        if self.operator_approved is not True:
            deny("operator-approval-required")
        if self.output_kind != "candidate-only":
            deny("production-promotion-refused")

    def record(self) -> dict:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @property
    def digest(self) -> str:
        return digest(self.record())
