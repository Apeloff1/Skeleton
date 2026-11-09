"""Bind decade architecture epochs and year-granular runtime policy."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .runtime_epochs import RuntimeEpochRegistry, DEFAULT_RUNTIME_EPOCHS
from .runtime_policy import RuntimePolicy, RuntimePolicyCompiler, DEFAULT_RUNTIME_POLICY_COMPILER


@dataclass(frozen=True, slots=True)
class TemporalRuntimePolicy:
    year: int
    decade: int
    inherited_capabilities: tuple[str, ...]
    runtime_policy: RuntimePolicy
    epoch_digest: str
    digest: str


class TemporalRuntimePolicyCompiler:
    def __init__(
        self,
        epochs: RuntimeEpochRegistry = DEFAULT_RUNTIME_EPOCHS,
        years: RuntimePolicyCompiler = DEFAULT_RUNTIME_POLICY_COMPILER,
    ) -> None:
        self.epochs = epochs
        self.years = years

    def compile(
        self,
        year: int,
        *,
        requested: tuple[str, ...] = (),
        enable_experimental: tuple[str, ...] = (),
    ) -> TemporalRuntimePolicy:
        if isinstance(year, bool) or not isinstance(year, int) or not 1950 <= year <= 2100:
            raise ValueError("supported integer policy year required")
        decade = (year // 10) * 10
        # Year-granular serving signals currently begin in the 2020s. Earlier
        # historical replay still receives an epoch receipt but no modern serving policy.
        if year < 2020:
            runtime = RuntimePolicy(year, (), (), hashlib.sha256(
                f"historical-runtime-policy:{year}".encode("utf-8")
            ).hexdigest())
            if requested or enable_experimental:
                raise ValueError("modern serving capabilities unavailable before 2020")
        else:
            runtime = self.years.compile(
                year, requested=requested, enable_experimental=enable_experimental
            )
        epoch_snapshot = self.epochs.snapshot(decade)
        inherited = self.epochs.inherited_capabilities(decade)
        body = {
            "schema": "skeleton.ai.temporal-runtime-policy.v1",
            "year": year,
            "decade": decade,
            "inherited_capabilities": inherited,
            "runtime_policy_digest": runtime.digest,
            "epoch_digest": epoch_snapshot["digest"],
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return TemporalRuntimePolicy(
            year, decade, inherited, runtime, epoch_snapshot["digest"], digest
        )


DEFAULT_TEMPORAL_RUNTIME_POLICY_COMPILER = TemporalRuntimePolicyCompiler()

__all__ = [
    "DEFAULT_TEMPORAL_RUNTIME_POLICY_COMPILER",
    "TemporalRuntimePolicy",
    "TemporalRuntimePolicyCompiler",
]
