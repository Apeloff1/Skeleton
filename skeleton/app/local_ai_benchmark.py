"""Offline, bounded, category-aware evaluation of native model checkpoints.

This is an application adapter over the existing native causal model; it does
not own training, release promotion, safety certification, provider calls or
durable assistant state. A strict suite file may contain multiple independent
categories. A candidate only passes this *local statistical gate* when:
  - all records are validated under the canonical tokenizer,
  - weighted held-out perplexity strictly improves,
  - no protected category's token-weighted perplexity regresses, and
  - optional next-token objectives never regress in correct/incorrect count.

A successful outcome is *not* an automatic model promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import load_native_checkpoint
from skeleton.app.local_ai_improvement import MIN_VALIDATION_IMPROVEMENT
from skeleton.app.local_ai_training import _read_corpus


SCHEMA = "skeleton.ai.offline.benchmark.v1"
MAX_SUITE_BYTES = 128 * 1024
MAX_CASES = 64
MAX_CASE_CHARS = 2048
MAX_TOTAL_TOKENS = 1024
MAX_CATEGORIES = 16


class OfflineBenchmarkError(ValueError):
    """Malformed suite, unbound model or invalid benchmark result."""


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    category: str
    text: str
    predicted_tokens: int
    expected_next: str | None
    text_digest: str


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    suite_digest: str
    cases: tuple[BenchmarkCase, ...]
    total_predicted_tokens: int
    categories: tuple[str, ...]


def _validate_id(label: str, value: object, limit: int = 64) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= limit
        or not value.strip()
        or any(ord(ch) < 32 for ch in value)
    ):
        raise OfflineBenchmarkError(label + " must be bounded, non-empty printable text")
    return value


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    item: dict[str, object] = {}
    for name, value in pairs:
        if name in item:
            raise OfflineBenchmarkError("duplicate benchmark JSON key: " + name)
        item[name] = value
    return item


def _reject_constant(_: str) -> None:
    raise OfflineBenchmarkError("nonfinite benchmark constant")


def _canonical(obj: object) -> bytes:
    try:
        return json.dumps(
            obj, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise OfflineBenchmarkError("suite cannot be canonicalized") from exc


def _read_suite_bytes(path: str | Path) -> bytes:
    target = Path(path)
    try:
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SUITE_BYTES:
            raise OfflineBenchmarkError("benchmark suite must be a bounded regular JSON file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > MAX_SUITE_BYTES
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
            ):
                raise OfflineBenchmarkError("suite file changed during open")
            raw = stream.read(MAX_SUITE_BYTES + 1)
            if len(raw) != opened.st_size or os.fstat(stream.fileno()).st_size != opened.st_size:
                raise OfflineBenchmarkError("suite file changed while reading")
    except OSError as exc:
        raise OfflineBenchmarkError("cannot read bounded benchmark suite") from exc
    return raw


def _admit_checkpoint(backend: NativeRuntimeLocalModel) -> None:
    if not isinstance(backend, NativeRuntimeLocalModel):
        raise OfflineBenchmarkError("canonical native model required")
    backend.assert_identity()
    if not hasattr(backend.runtime.model, "_ids") or not hasattr(backend.runtime.model, "logprob"):
        raise OfflineBenchmarkError("model lacks native tokenizer/logprob execution")


def load_benchmark_suite(
    path: str | Path,
    *,
    backend: NativeRuntimeLocalModel,
) -> BenchmarkSuite:
    """Validate suite structure AND all expected text tokens before inference."""
    _admit_checkpoint(backend)
    raw = _read_suite_bytes(path)
    try:
        obj = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise OfflineBenchmarkError("invalid UTF-8 JSON benchmark") from exc
    if not isinstance(obj, dict) or set(obj) != {"schema", "cases"}:
        raise OfflineBenchmarkError("suite requires exactly schema and cases")
    if obj.get("schema") != SCHEMA:
        raise OfflineBenchmarkError("unsupported benchmark suite schema")
    data = obj["cases"]
    if not isinstance(data, list) or not 1 <= len(data) <= MAX_CASES:
        raise OfflineBenchmarkError("suite must contain 1-64 cases")
    vocab = backend.runtime.model.stoi
    cases: list[BenchmarkCase] = []
    identities: set[str] = set()
    seen_text: set[tuple[int, ...]] = set()
    categories: set[str] = set()
    total_tokens = 0
    for record in data:
        if not isinstance(record, dict) or set(record) not in (
            {"id", "category", "text"},
            {"id", "category", "text", "expected_next"},
        ):
            raise OfflineBenchmarkError("unknown or missing benchmark case fields")
        case_id = _validate_id("case id", record["id"])
        category = _validate_id("category", record["category"], 48)
        passage = record["text"]
        if not isinstance(passage, str) or not passage.strip() or len(passage) > MAX_CASE_CHARS:
            raise OfflineBenchmarkError("case text violates character budget")
        if case_id in identities:
            raise OfflineBenchmarkError("duplicate benchmark case identity")
        identities.add(case_id)
        categories.add(category)
        if len(categories) > MAX_CATEGORIES:
            raise OfflineBenchmarkError("too many benchmark categories")

        # The canonical native tokenizer maps casing/punctuation to token
        # identities. Never count the same normalized sequence twice.
        normalized = tuple(backend.runtime.model._ids(passage))
        known = backend.runtime.model.stoi
        from skeleton.cortex.port import tokens
        if any(word not in known for word in tokens(passage)):
            raise OfflineBenchmarkError("benchmark contains out-of-vocabulary source tokens")
        if len(normalized) < 2:
            raise OfflineBenchmarkError("benchmark case needs at least two tokens")
        if normalized in seen_text:
            raise OfflineBenchmarkError("duplicate normalized benchmark case")
        seen_text.add(normalized)
        predicted = len(normalized) - 1
        total_tokens += len(normalized)
        if total_tokens > MAX_TOTAL_TOKENS:
            raise OfflineBenchmarkError("suite exceeds token budget")

        expected: str | None = None
        if "expected_next" in record:
            expected = _validate_id("expected next token", record["expected_next"])
            if expected not in vocab:
                raise OfflineBenchmarkError("expected next token missing from checkpoint vocabulary")
        cases.append(BenchmarkCase(
            case_id=case_id,
            category=category,
            text=passage,
            predicted_tokens=predicted,
            expected_next=expected,
            text_digest=hashlib.sha256(passage.encode("utf-8")).hexdigest(),
        ))
    return BenchmarkSuite(
        suite_digest=hashlib.sha256(_canonical(obj)).hexdigest(),
        cases=tuple(cases),
        total_predicted_tokens=sum(c.predicted_tokens for c in cases),
        categories=tuple(sorted(categories)),
    )


def _exclude_leaked_training_cases(
    suite: BenchmarkSuite,
    *,
    checkpoint: NativeRuntimeLocalModel,
    source: str | Path,
) -> str:
    """Reject normalized evaluation lines seen in selected local training data.

    Explicit source-binding also rejects sentence fragments copied into a
    larger training line (or the inverse). This only checks the selected
    corpus; it cannot prove that all historical training data is disjoint.
    """
    raw, content = _read_corpus(source)
    sentences = [
        tuple(checkpoint.runtime.model._ids(line.strip()))
        for line in content.splitlines() if line.strip()
    ]
    if not sentences or len(sentences) > 512:
        raise OfflineBenchmarkError("training exclusion corpus has invalid line count")
    if sum(len(line) for line in sentences) > MAX_TOTAL_TOKENS:
        raise OfflineBenchmarkError("training exclusion corpus exceeds token budget")

    def contains(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
        if len(a) < len(b):
            return False
        return any(a[i:i + len(b)] == b for i in range(len(a) - len(b) + 1))

    for case in suite.cases:
        case_ids = tuple(checkpoint.runtime.model._ids(case.text))
        for training_ids in sentences:
            if (
                training_ids == case_ids
                or (len(case_ids) >= 3 and contains(training_ids, case_ids))
                or (len(training_ids) >= 3 and contains(case_ids, training_ids))
            ):
                raise OfflineBenchmarkError(
                    "held-out benchmark case overlaps normalized local training source"
                )
    return hashlib.sha256(raw).hexdigest()


def _evaluate_backend(
    suite: BenchmarkSuite,
    backend: NativeRuntimeLocalModel,
) -> dict[str, Any]:
    _admit_checkpoint(backend)
    model = backend.runtime.model
    aggregates: dict[str, dict[str, float | int]] = {}
    scores: list[dict[str, Any]] = []
    logp_sum = 0.0
    total = 0
    for case in suite.cases:
        count = len(model._ids(case.text)) - 1
        if count != case.predicted_tokens:
            raise OfflineBenchmarkError("tokenizer prediction count drift")
        mean_logp = model.logprob(case.text)
        if not math.isfinite(mean_logp) or mean_logp > 1e-9:
            raise OfflineBenchmarkError("model returned nonfinite or positive log probability")
        weighted = mean_logp * count
        logp_sum += weighted
        total += count
        agg = aggregates.setdefault(
            case.category, {"cases": 0, "predicted_tokens": 0, "sum_log_probability": 0.0},
        )
        agg["cases"] += 1
        agg["predicted_tokens"] += count
        agg["sum_log_probability"] += weighted
        top1: bool | None = None
        if case.expected_next is not None:
            raw_scores = model._logits(model._ids(case.text))
            if len(raw_scores) != len(model.itos) or any(not math.isfinite(x) for x in raw_scores):
                raise OfflineBenchmarkError("model returned invalid next-token logits")
            winner = max(range(len(raw_scores)), key=raw_scores.__getitem__)
            top1 = model.itos[winner] == case.expected_next
            agg["next_token_trials"] = int(agg.get("next_token_trials", 0)) + 1
            agg["next_token_correct"] = int(agg.get("next_token_correct", 0)) + int(top1)
        scores.append({
            "id": case.case_id,
            "category": case.category,
            "text_digest": case.text_digest,
            "predicted_tokens": count,
            "mean_log_probability": mean_logp,
            "expected_next_top1_correct": top1,
        })
    if total != suite.total_predicted_tokens or total < 1:
        raise OfflineBenchmarkError("aggregate benchmark prediction count mismatch")

    def perplexity(weighted_logp: float, count: int) -> float:
        try:
            result = math.exp(-weighted_logp / count)
        except OverflowError as exc:
            raise OfflineBenchmarkError("benchmark perplexity overflow") from exc
        if not math.isfinite(result) or result <= 0:
            raise OfflineBenchmarkError("benchmark perplexity is invalid")
        return result

    summaries = {
        cat: {
            "case_count": int(info["cases"]),
            "predicted_tokens": int(info["predicted_tokens"]),
            "perplexity": perplexity(
                float(info["sum_log_probability"]), int(info["predicted_tokens"]),
            ),
            "next_token_trials": int(info.get("next_token_trials", 0)),
            "next_token_correct": int(info.get("next_token_correct", 0)),
        }
        for cat, info in sorted(aggregates.items())
    }
    return {
        "model_digest": backend.model_digest,
        "tokenizer_digest": backend.tokenizer_digest,
        "overall_perplexity": perplexity(logp_sum, total),
        "category_scores": summaries,
        "case_scores": scores,
    }


def benchmark_native_models(
    suite_path: str | Path,
    *,
    baseline: str | Path,
    candidate: str | Path | None = None,
    excluded_training_text: str | Path | None = None,
) -> dict[str, Any]:
    """Read-only benchmark: candidate must beat baseline and protect each lane."""
    original = load_native_checkpoint(baseline)
    suite = load_benchmark_suite(suite_path, backend=original)
    excluded_source_sha256 = (
        _exclude_leaked_training_cases(
            suite, checkpoint=original, source=excluded_training_text,
        )
        if excluded_training_text is not None else None
    )
    original_result = _evaluate_backend(suite, original)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "suite_digest": suite.suite_digest,
        "excluded_training_source_sha256": excluded_source_sha256,
        "historical_training_disjointness_proven": False,
        "case_count": len(suite.cases),
        "category_count": len(suite.categories),
        "predicted_tokens": suite.total_predicted_tokens,
        "baseline": original_result,
        "candidate": None,
        "passes_local_regression_gate": None,
        "candidate_promoted": False,
        "model_quality_certified": False,
    }
    if candidate is None:
        return report
    other = load_native_checkpoint(candidate)
    if original.model_digest == other.model_digest:
        raise OfflineBenchmarkError("candidate and baseline must have distinct native weights")
    if original.tokenizer_digest != other.tokenizer_digest:
        raise OfflineBenchmarkError("benchmark tokenizer identity differs between checkpoints")
    if original.runtime.model.itos != other.runtime.model.itos:
        raise OfflineBenchmarkError("benchmark vocabulary ordering differs")
    result = _evaluate_backend(suite, other)
    categories = {}
    for name, base in original_result["category_scores"].items():
        contender = result["category_scores"][name]
        categories[name] = {
            "baseline_perplexity": base["perplexity"],
            "candidate_perplexity": contender["perplexity"],
            "perplexity_nonregression": (
                contender["perplexity"] <= base["perplexity"] + MIN_VALIDATION_IMPROVEMENT
            ),
            "top1_nonregression": (
                contender["next_token_correct"] >= base["next_token_correct"]
            ),
        }
    improves = (
        result["overall_perplexity"]
        < original_result["overall_perplexity"] - MIN_VALIDATION_IMPROVEMENT
    )
    safe_categories = all(
        row["perplexity_nonregression"] and row["top1_nonregression"]
        for row in categories.values()
    )
    report["candidate"] = result
    report["category_comparisons"] = categories
    report["overall_improves"] = improves
    report["passes_local_regression_gate"] = improves and safe_categories
    return report


def smoke_offline_native_benchmark() -> bool:
    """Exercise real weight-backed category evaluation inside the frozen app."""
    import tempfile

    from skeleton.ai.model_runtime import NativeLLMRuntime
    from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
    from skeleton.cortex.transformer import TinyTransformer

    with tempfile.TemporaryDirectory(prefix="skeleton-local-benchmark-") as directory:
        root = Path(directory)
        base = root / "baseline.json"
        other = root / "candidate.json"
        suite = root / "suite.json"
        vocabulary = ("user", "assistant", "hello", "world", "alpha", "beta")
        for seed, target in ((31, base), (53, other)):
            model = TinyTransformer(
                vocab=vocabulary, dim=8, ctx=48, seed=seed,
                n_heads=2, n_layers=1, d_ff=16,
            )
            from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel

            write_local_model_artifact(
                NativeRuntimeLocalModel(NativeLLMRuntime(model)), target,
            )
        suite.write_text(json.dumps({
            "schema": SCHEMA,
            "cases": [
                {"id": "dialog-1", "category": "dialog", "text": "user hello assistant world"},
                {"id": "dialog-2", "category": "dialog", "text": "hello assistant world user"},
                {"id": "reason-1", "category": "reason", "text": "hello alpha beta"},
                {"id": "reason-2", "category": "reason", "text": "beta alpha world"},
            ],
        }), encoding="utf-8")
        result = benchmark_native_models(suite, baseline=base, candidate=other)
        return bool(
            result["case_count"] == 4
            and result["category_count"] == 2
            and result["candidate"] is not None
            and isinstance(result["passes_local_regression_gate"], bool)
            and len(result["suite_digest"]) == 64
            and result["baseline"]["overall_perplexity"] > 0
            and result["candidate"]["overall_perplexity"] > 0
            and result["candidate_promoted"] is False
        )
