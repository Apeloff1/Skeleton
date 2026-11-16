"""Evidence-gated local inference tuning within the existing GGUF owner.

This module never runs inference, downloads weights, changes deployment files
or grants runtime admission. It proposes shape candidates and selects only a
measured, quality-preserving improvement. Native admission remains authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from itertools import islice
import json
from statistics import median
from typing import Iterable

from .llama_cpp import (
    ConsumerHardwareBudget, ConsumerLlamaPlan, LlamaCppConfig,
    LlamaCppRuntimeError, plan_consumer_llama_cpp,
)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("ascii")).hexdigest()


def _pin(value: str) -> None:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected lowercase SHA256 identity")


def _integer(value: int, lo: int, hi: int) -> None:
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("quantity outside explicit bounds")


@dataclass(frozen=True, slots=True)
class TuningScope:
    model_sha256: str
    runtime_sha256: str
    tokenizer_sha256: str
    host_profile_sha256: str
    corpus_sha256: str
    protocol_sha256: str

    def __post_init__(self) -> None:
        for value in (self.model_sha256, self.runtime_sha256,
                      self.tokenizer_sha256, self.host_profile_sha256,
                      self.corpus_sha256, self.protocol_sha256):
            _pin(value)

    @property
    def identity(self) -> str:
        return _digest([self.model_sha256, self.runtime_sha256,
                        self.tokenizer_sha256, self.host_profile_sha256,
                        self.corpus_sha256, self.protocol_sha256])


@dataclass(frozen=True, slots=True)
class Candidate:
    scope: TuningScope
    plan: ConsumerLlamaPlan

    def __post_init__(self) -> None:
        if type(self.scope) is not TuningScope or type(self.plan) is not ConsumerLlamaPlan:
            raise ValueError("typed scope and plan required")
        c = self.plan.configuration
        if type(c) is not LlamaCppConfig or c.context_size is None or c.threads is None or c.batch_size is None or c.kv_bytes_per_token is None:
            raise ValueError("candidate needs a complete planned configuration")
        for value in (self.plan.model_bytes, self.plan.reserved_ram_bytes, self.plan.reserved_kv_bytes, self.plan.estimated_total_bytes, self.plan.available_ram_bytes):
            _integer(value, 1, 1 << 53)
        if (self.plan.reserved_kv_bytes != c.context_size * c.kv_bytes_per_token
                or self.plan.estimated_total_bytes != self.plan.model_bytes + self.plan.reserved_ram_bytes + self.plan.reserved_kv_bytes + c.runtime_scratch_bytes + c.speculation_reserve_bytes
                or self.plan.estimated_total_bytes > self.plan.available_ram_bytes):
            raise ValueError("inconsistent candidate capacity accounting")

    @property
    def identity(self) -> str:
        c = self.plan.configuration
        # Include only identity digests in public evidence, not paths, prompts
        # or environment values. All behavior-changing settings are committed.
        return _digest({
            "scope": self.scope.identity,
            "config": {k: getattr(c, k) for k in (
                "model_id", "context_size", "threads", "batch_size", "gpu_layers",
                "kv_cache_location", "kv_cache_type_k", "kv_cache_type_v",
                "temperature", "timeout_seconds", "output_framing",
                "max_output_bytes", "max_stderr_bytes", "runtime_scratch_bytes",
                "kv_bytes_per_token", "reject_model_symlink", "rehash_artifacts_each_run",
                "speculation_runtime_sha256", "speculation_ngram", "speculation_draft_tokens",
                "speculation_min_hits", "speculation_reserve_bytes",
                "runtime_libraries",
            )},
            "args": _digest(c.extra_args), "environment": _digest(dict(c.environment)),
            "model_bytes": self.plan.model_bytes,
            "total_bytes": self.plan.estimated_total_bytes,
            "available_bytes": self.plan.available_ram_bytes,
        })


def candidates(config: LlamaCppConfig, budget: ConsumerHardwareBudget, *,
               model_bytes: int, scope: TuningScope) -> tuple[Candidate, ...]:
    """Baseline then a finite, deterministic CPU-thread/prefill search space.

    Keep context, output behavior, GPU assignment, quantization and safety
    reserves fixed. Tuning never expands the operator's original bounds.
    """
    if type(scope) is not TuningScope:
        raise TypeError("typed identity scope required")
    baseline = plan_consumer_llama_cpp(config, budget, model_bytes=model_bytes)
    chosen = baseline.configuration
    threads = chosen.threads
    batch = chosen.batch_size
    if threads is None or batch is None:
        raise LlamaCppRuntimeError("missing effective baseline shape")
    rows = [Candidate(scope, baseline)]
    seen = {(threads, batch)}
    for t in sorted({1, max(1, threads // 2), max(1, threads * 3 // 4), threads}):
        for b in sorted({max(1, batch // 4), max(1, batch // 2), batch}):
            if (t, b) in seen:
                continue
            seen.add((t, b))
            trial = plan_consumer_llama_cpp(replace(chosen, threads=t, batch_size=b),
                                           budget, model_bytes=model_bytes)
            if trial.configuration.context_size != chosen.context_size:
                raise LlamaCppRuntimeError("candidate changed context")
            rows.append(Candidate(scope, trial))
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class Sample:
    """Caller-observed paired trial, including a separate quality decision.

    Integer microseconds and bytes avoid NaN, rounding and unit ambiguity.
    Quality is in basis points; failed/aborted attempts must not be hidden.
    No self-asserted sample constitutes signed hardware qualification.
    """
    candidate_sha256: str
    case_sha256: str
    repeat: int
    prompt_tokens: int
    output_tokens: int
    first_token_us: int
    total_us: int
    peak_bytes: int
    quality_bp: int
    succeeded: bool

    def __post_init__(self) -> None:
        _pin(self.candidate_sha256)
        _pin(self.case_sha256)
        _integer(self.repeat, 0, 63)
        _integer(self.prompt_tokens, 1, 1_048_576)
        _integer(self.output_tokens, 0, 1_048_576)
        _integer(self.first_token_us, 1, 86_400_000_000)
        _integer(self.total_us, self.first_token_us, 86_400_000_000)
        _integer(self.peak_bytes, 1, 1 << 53)
        _integer(self.quality_bp, 0, 10_000)
        if type(self.succeeded) is not bool:
            raise ValueError("explicit success flag required")
        if self.succeeded and not self.output_tokens:
            raise ValueError("successful trial returned no tokens")


@dataclass(frozen=True, slots=True)
class Decision:
    selected_sha256: str
    baseline_sha256: str
    reason: str
    paired_trials: int
    median_latency_gain_bp: int
    evaluated_candidates: int
    advisory_only: bool = True


def corpus_identity(case_ids: Iterable[str]) -> str:
    ids = tuple(islice(case_ids, 257))
    if not 1 <= len(ids) <= 256:
        raise ValueError("expected bounded benchmark corpus")
    for item in ids:
        _pin(item)
    if len(set(ids)) != len(ids):
        raise ValueError("expected unique benchmark corpus")
    return _digest(sorted(ids))


def select(profiles: tuple[Candidate, ...], samples: Iterable[Sample], *,
           case_ids: tuple[str, ...], repetitions: int = 3,
           minimum_quality_bp: int = 9000, min_gain_bp: int = 500,
           max_ttft_regression_bp: int = 500) -> Decision:
    """Reject incomplete, cross-scope, slow-tail, quality or memory regressions.

    Same-case matched repeats are required, including equal prompt and output
    token counts. Benchmark callers must use pinned deterministic workloads;
    this comparison is not suitable for variable-length open-ended generation.
    """
    _integer(repetitions, 3, 16)
    _integer(minimum_quality_bp, 0, 10000)
    _integer(min_gain_bp, 1, 10000)
    _integer(max_ttft_regression_bp, 0, 10000)
    if type(profiles) is not tuple or not 1 <= len(profiles) <= 16:
        raise ValueError("expected bounded candidate set")
    if any(type(p) is not Candidate for p in profiles):
        raise ValueError("typed candidate required")
    baseline = profiles[0]
    if corpus_identity(case_ids) != baseline.scope.corpus_sha256:
        raise ValueError("corpus identity mismatch")
    if any(p.scope != baseline.scope for p in profiles):
        raise ValueError("candidate crosses evidence scope")
    config = baseline.plan.configuration
    for p in profiles[1:]:
        c = p.plan.configuration
        if (replace(c, threads=config.threads, batch_size=config.batch_size) != config
                or c.threads > config.threads or c.batch_size > config.batch_size
                or (p.plan.model_bytes, p.plan.reserved_ram_bytes, p.plan.reserved_kv_bytes,
                    p.plan.estimated_total_bytes, p.plan.available_ram_bytes) !=
                   (baseline.plan.model_bytes, baseline.plan.reserved_ram_bytes, baseline.plan.reserved_kv_bytes,
                    baseline.plan.estimated_total_bytes, baseline.plan.available_ram_bytes)):
            raise ValueError("candidate changed a non-tunable setting or capacity reserve")
    expected = {p.identity: p for p in profiles}
    if len(expected) != len(profiles):
        raise ValueError("duplicate candidate")
    keys = {(case, r) for case in case_ids for r in range(repetitions)}
    grouped: dict[str, dict[tuple[str, int], Sample]] = {key: {} for key in expected}
    for index, sample in enumerate(samples):
        if index >= len(expected) * len(keys) or type(sample) is not Sample:
            raise ValueError("invalid or excessive trial data")
        if sample.candidate_sha256 not in expected:
            raise ValueError("unknown candidate evidence")
        key = (sample.case_sha256, sample.repeat)
        table = grouped[sample.candidate_sha256]
        if key not in keys or key in table:
            raise ValueError("unexpected or duplicate trial")
        table[key] = sample

    def qualified(candidate: Candidate) -> bool:
        table = grouped[candidate.identity]
        if set(table) != keys:
            return False
        cap = candidate.plan.available_ram_bytes - candidate.plan.reserved_ram_bytes
        context = candidate.plan.configuration.context_size or 0
        return all(s.succeeded and s.quality_bp >= minimum_quality_bp
                   and s.peak_bytes <= cap
                   and s.prompt_tokens + s.output_tokens <= context
                   for s in table.values())

    bid = baseline.identity
    if not qualified(baseline):
        return Decision(bid, bid, "baseline_unqualified_no_promotion", 0, 0, 0)
    base = grouped[bid]
    winner = bid
    best_gain = 0
    evaluated = 1
    for candidate in profiles[1:]:
        if not qualified(candidate):
            continue
        table = grouped[candidate.identity]
        if any((table[k].prompt_tokens, table[k].output_tokens) !=
               (base[k].prompt_tokens, base[k].output_tokens)
               or table[k].quality_bp < base[k].quality_bp
               or table[k].first_token_us * 10000 >
                  base[k].first_token_us * (10000 + max_ttft_regression_bp)
               or table[k].total_us * 10000 >
                  base[k].total_us * (10000 + max_ttft_regression_bp)
               for k in keys):
            continue
        evaluated += 1
        gain = int(median((base[k].total_us - table[k].total_us) * 10000 //
                          base[k].total_us for k in keys))
        if gain >= min_gain_bp and (gain > best_gain or
                                   (gain == best_gain and candidate.identity < winner)):
            winner, best_gain = candidate.identity, gain
    return Decision(winner, bid, "measured_candidate" if winner != bid else
                    "baseline_retained", len(keys), best_gain, evaluated)
