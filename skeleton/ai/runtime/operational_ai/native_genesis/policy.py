"""Explicit, bounded original native-model genesis. Candidate-only by contract.

This policy describes actual initial model weights, NOT a promise of model
quality. It refuses external datasets, implicit provider fallback, GPU drift,
unbounded parameter allocations and serving self-promotion.
"""
from __future__ import annotations
from dataclasses import dataclass, fields
from .errors import refuse
from .canonical import required_id, required_int
from ..native_candidate.records import LICENSE, SCOPE


@dataclass(frozen=True, slots=True)
class GenesisPolicy:
    run_id: str = "original_genesis_001"
    seed: int = 42
    dim: int = 16
    ctx: int = 128
    n_heads: int = 2
    n_layers: int = 1
    d_ff: int = 64
    max_vocab: int = 4096
    minimum_document_frequency: int = 1
    maximum_model_bytes: int = 256_000_000
    max_optimizer_steps: int = 32000
    learning_rate_ppm: int = 10000
    batch_lines: int = 8
    minimum_known_fraction_ppm: int = 900000
    maximum_wall_ms: int = 3600000
    license_id: str = LICENSE
    training_scope: str = SCOPE
    operator_approved: bool = False
    candidate_only: bool = True
    device: str = "cpu"
    position_mode: str = "rope"
    norm: str = "ln"
    ffn_kind: str = "gelu"

    def __post_init__(self) -> None:
        required_id(self.run_id, "run")
        for name, minimum, maximum in (
            ("seed", 0, 2**32 - 1),
            ("dim", 8, 256), ("ctx", 32, 2048),
            ("n_heads", 1, 16), ("n_layers", 1, 12),
            ("d_ff", 0, 4096), ("max_vocab", 32, 32768),
            ("minimum_document_frequency", 1, 50),
            ("maximum_model_bytes", 1_048_576, 256_000_000),
            ("max_optimizer_steps", 1, 100000),
            ("learning_rate_ppm", 1, 100000),
            ("batch_lines", 1, 128),
            ("minimum_known_fraction_ppm", 0, 1000000),
            ("maximum_wall_ms", 1, 36000000),
        ):
            required_int(getattr(self, name), name, minimum, maximum)
        if self.dim % self.n_heads:
            refuse("head-dimension-incompatible")
        if self.dim < self.n_heads * 2:
            refuse("head-width-underflow")
        if self.license_id != LICENSE:
            refuse("unsupported-original-license")
        if self.training_scope != SCOPE:
            refuse("unapproved-training-purpose")
        if self.operator_approved is not True:
            refuse("operator-approval-required")
        if self.candidate_only is not True:
            refuse("production-promotion-refused")
        if self.device != "cpu":
            refuse("unsupported-genesis-device")
        if self.position_mode not in ("rope", "learned_rope"):
            refuse("unsupported-position")
        if self.norm not in ("ln", "rms"):
            refuse("unsupported-norm")
        if self.ffn_kind not in ("gelu", "swiglu"):
            refuse("unsupported-ffn")

    @classmethod
    def from_record(cls, record: dict) -> "GenesisPolicy":
        if type(record) is not dict:
            refuse("policy-record-required")
        accepted = {field.name for field in fields(cls)}
        if set(record) - accepted:
            refuse("policy-unknown-fields")
        try:
            return cls(**record)
        except TypeError:
            refuse("policy-invalid-shape")

    def record(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @property
    def digest(self) -> str:
        from .canonical import digest
        return digest(self.record())

    def for_candidate_training(self, model_sha256: str, tokenizer_sha256: str):
        from ..native_candidate.plan import TrainingPlan
        return TrainingPlan(
            run_id=self.run_id,
            expected_base_model_sha256=model_sha256,
            expected_tokenizer_sha256=tokenizer_sha256,
            learning_rate_ppm=self.learning_rate_ppm,
            max_optimizer_steps=self.max_optimizer_steps,
            batch_lines=self.batch_lines,
            maximum_total_ms=self.maximum_wall_ms,
            min_known_token_fraction_ppm=self.minimum_known_fraction_ppm,
            maximum_checkpoint_bytes=self.maximum_model_bytes,
            operator_approved=True,
            output_kind="candidate-only",
        )
