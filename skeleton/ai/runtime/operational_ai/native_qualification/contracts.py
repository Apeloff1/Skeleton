"""Strictly typed local model identity and evaluation provenance."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import hex64, identity, integer
from .errors import deny


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    model_sha256: str
    tokenizer_sha256: str
    tenant: str
    user: str
    license_id: str
    checkpoint_sha256: str

    def __post_init__(self) -> None:
        for key in ("model_sha256", "tokenizer_sha256", "checkpoint_sha256"):
            hex64(getattr(self, key), key)
        for key in ("tenant", "user", "license_id"):
            identity(getattr(self, key), key)

    def record(self) -> dict:
        from .canonical import encode, sha256
        return {"model_sha256": self.model_sha256,
                "tokenizer_sha256": self.tokenizer_sha256,
                "checkpoint_sha256": self.checkpoint_sha256,
                "license_id": self.license_id,
                "principal_sha256": sha256(encode({"tenant": self.tenant,
                                                  "user": self.user}))}


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    max_cases: int = 480
    max_steps_per_case: int = 4
    max_output_chars: int = 262144
    max_total_wall_ms: int = 10800000
    max_case_wall_ms: int = 300000

    def __post_init__(self) -> None:
        integer(self.max_cases, "cases", 1, 480)
        integer(self.max_steps_per_case, "steps", 1, 4)
        integer(self.max_output_chars, "output-length", 1, 262144)
        integer(self.max_total_wall_ms, "total-wall", 1, 36000000)
        integer(self.max_case_wall_ms, "case-wall", 1, 3600000)
