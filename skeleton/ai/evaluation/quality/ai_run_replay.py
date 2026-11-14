"""AI-run replay evidence with performance gates (#807 B072).

Extend-only: reuses the cognition ``ReplayTape`` (via replay_evidence's loader)
instead of introducing a second replay core.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from skeleton.quality.deterministic_time import DeterministicClock, budget_within
from skeleton.quality.replay_evidence import ReplayTape

SCHEMA_ID = "quality.ai_run_replay.v1"
_PERF_KEYS = ("frame_ms", "alloc_bytes", "load_ms")
_MAX_EVENTS = 10_000
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_JSON_NODES = 250_000
_MAX_JSON_DEPTH = 32
_RUN_FIELDS = frozenset({"schema", "run_id", "seed", "tick_ms", "events", "perf", "budgets", "digest"})


class AiRunReplayError(ValueError):
    """Raised for malformed or tampered AI-run documents (fail closed)."""


def _canonical_bytes(value: Any) -> bytes:
    """Strict, bounded canonical JSON; no key coercion or arbitrary repr."""
    remaining = _MAX_JSON_NODES
    chars = _MAX_JSON_BYTES
    active: set[int] = set()

    def visit(item: Any, depth: int = 0) -> None:
        nonlocal remaining, chars
        remaining -= 1
        if remaining < 0 or depth > _MAX_JSON_DEPTH:
            raise AiRunReplayError("run JSON shape exceeds bounds")
        if type(item) is str:
            chars -= len(item)
            if chars < 0:
                raise AiRunReplayError("run JSON text exceeds bounds")
        elif type(item) in (dict, list, tuple):
            if id(item) in active or len(item) > remaining:
                raise AiRunReplayError("cyclic or unbounded run JSON")
            active.add(id(item))
            try:
                if type(item) is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            raise AiRunReplayError("run JSON keys must be strings")
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        visit(child, depth + 1)
            finally:
                active.remove(id(item))
        elif item is None or type(item) is bool:
            return
        elif type(item) is int:
            if item.bit_length() > 16384:
                raise AiRunReplayError("run JSON integer exceeds bounds")
        elif type(item) is float:
            if not math.isfinite(item):
                raise AiRunReplayError("run JSON number is not finite")
        else:
            raise AiRunReplayError("run is not canonically serializable")

    visit(value)
    result = bytearray()
    try:
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
        for chunk in encoder.iterencode(value):
            if len(chunk) > _MAX_JSON_BYTES - len(result):
                raise AiRunReplayError("run JSON byte limit exceeded")
            result.extend(chunk.encode("ascii"))
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, AiRunReplayError):
            raise
        raise AiRunReplayError("run is not canonically serializable") from exc
    return bytes(result)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _non_negative(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AiRunReplayError(f"{name} must be a number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise AiRunReplayError(f"{name} is outside the numeric range") from exc
    if not math.isfinite(number) or number < 0:
        raise AiRunReplayError(f"{name} must be finite and non-negative")
    return number


@dataclass(frozen=True, slots=True)
class PerfBudgets:
    frame_ms: float | None = None
    alloc_bytes: float | None = None
    load_ms: float | None = None

    def to_mapping(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in _PERF_KEYS if getattr(self, k) is not None}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "PerfBudgets":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping) or any(not isinstance(k, str) for k in payload):
            raise AiRunReplayError("performance fields must be an object with string keys")
        unknown = set(payload) - set(_PERF_KEYS)
        if unknown:
            raise AiRunReplayError(f"unknown perf budget keys: {sorted(unknown)}")
        return cls(**{k: _non_negative(payload[k], k) for k in _PERF_KEYS if payload.get(k) is not None})


@dataclass(frozen=True, slots=True)
class PerfObservation:
    frame_ms: tuple[float, ...] = ()
    alloc_bytes: tuple[float, ...] = ()
    load_ms: tuple[float, ...] = ()

    def to_mapping(self) -> dict[str, list[float]]:
        return {k: list(getattr(self, k)) for k in _PERF_KEYS}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "PerfObservation":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping) or any(not isinstance(k, str) for k in payload):
            raise AiRunReplayError("performance fields must be an object with string keys")
        unknown = set(payload) - set(_PERF_KEYS)
        if unknown:
            raise AiRunReplayError(f"unknown perf observation keys: {sorted(unknown)}")
        out: dict[str, tuple[float, ...]] = {}
        for key in _PERF_KEYS:
            values = payload.get(key, ())
            if not isinstance(values, (list, tuple)) or len(values) > _MAX_EVENTS:
                raise AiRunReplayError(f"{key} must be a list")
            out[key] = tuple(_non_negative(v, key) for v in values)
        return cls(**out)


def evaluate_perf_against_budgets(observation: PerfObservation, budgets: PerfBudgets) -> dict[str, Any]:
    """Return a perf envelope. Budgeted metrics with no samples fail closed."""
    metrics: dict[str, Any] = {}
    reasons: list[str] = []
    for key in _PERF_KEYS:
        budget = getattr(budgets, key)
        samples = getattr(observation, key)
        if budget is None:
            continue
        worst = max(samples) if samples else None
        ok = bool(samples) and all(budget_within(s, budget) for s in samples)
        if not samples:
            reasons.append(f"missing {key} observations")
        elif not ok:
            reasons.append(f"{key} budget exceeded")
        metrics[key] = {"budget": budget, "worst": worst, "samples": len(samples), "within": ok}
    return {"within": not reasons, "metrics": metrics, "reasons": reasons}


@dataclass(slots=True)
class AiRunRecorder:
    """Records AI decisions onto a cognition ReplayTape with deterministic timestamps."""

    run_id: str
    seed: int = 0
    clock: DeterministicClock = field(default_factory=DeterministicClock)
    tape: Any = field(default_factory=ReplayTape)
    frame_ms: list[float] = field(default_factory=list)
    alloc_bytes: list[float] = field(default_factory=list)
    load_ms: list[float] = field(default_factory=list)

    def record(self, kind: str, payload: Mapping[str, Any]) -> Any:
        if not isinstance(kind, str) or not kind:
            raise AiRunReplayError("event kind required")
        if (not isinstance(payload, Mapping) or len(payload) > _MAX_JSON_NODES
                or "t_ms" in payload or len(self.tape.events) >= _MAX_EVENTS):
            raise AiRunReplayError("reserved timestamp or event bound exceeded")
        snapshot = json.loads(_canonical_bytes(dict(payload)))
        try:
            self.clock.advance()
        except ValueError as exc:
            raise AiRunReplayError("logical clock cannot advance") from exc
        return self.tape.append(kind, {**snapshot, "t_ms": round(self.clock.now_ms(), 3)})

    def observe(self, *, frame_ms: float | None = None, alloc_bytes: float | None = None, load_ms: float | None = None) -> None:
        staged = []
        for key, sample in (("frame_ms", frame_ms), ("alloc_bytes", alloc_bytes), ("load_ms", load_ms)):
            if sample is not None:
                target = getattr(self, key)
                if len(target) >= _MAX_EVENTS:
                    raise AiRunReplayError("performance sample bound exceeded")
                staged.append((target, _non_negative(sample, key)))
        for target, sample in staged:
            target.append(sample)

    def observation(self) -> PerfObservation:
        return PerfObservation(tuple(self.frame_ms), tuple(self.alloc_bytes), tuple(self.load_ms))

    def export(self, budgets: PerfBudgets | None = None) -> dict[str, Any]:
        body = {
            "schema": SCHEMA_ID,
            "run_id": self.run_id,
            "seed": self.seed,
            "tick_ms": self.clock.tick_ms,
            "events": self.tape.export(),
            "perf": self.observation().to_mapping(),
            "budgets": (budgets or PerfBudgets()).to_mapping(),
        }
        document = json.loads(_canonical_bytes(body))
        document["digest"] = _digest(document)
        load_ai_run(document)
        return document


def load_ai_run(document: Mapping[str, Any]) -> tuple[Any, PerfObservation, PerfBudgets]:
    if not isinstance(document, Mapping):
        raise AiRunReplayError("ai run must be an object")
    if document.get("schema") != SCHEMA_ID or set(document) != _RUN_FIELDS:
        raise AiRunReplayError("unsupported or incomplete ai run schema")
    run_id, seed, tick = document["run_id"], document["seed"], document["tick_ms"]
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 128:
        raise AiRunReplayError("invalid run identity")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise AiRunReplayError("invalid run seed")
    tick = _non_negative(tick, "tick_ms")
    events = document["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= _MAX_EVENTS:
        raise AiRunReplayError("missing or unbounded replay events")
    if not isinstance(document["perf"], Mapping) or not isinstance(document["budgets"], Mapping):
        raise AiRunReplayError("performance evidence must be an object")
    body = {k: v for k, v in document.items() if k != "digest"}
    canonical = _canonical_bytes(body)
    if document["digest"] != hashlib.sha256(canonical).hexdigest():
        raise AiRunReplayError("ai run digest mismatch")
    snapshot = json.loads(canonical)
    events = snapshot["events"]
    try:
        clock = DeterministicClock(tick)
        for index, event in enumerate(events):
            if not isinstance(event, dict) or set(event) != {"sequence", "kind", "payload", "digest"}:
                raise AiRunReplayError("invalid replay event shape")
            if (type(event["sequence"]) is not int or event["sequence"] != index
                    or not isinstance(event["kind"], str) or not event["kind"]
                    or not isinstance(event["payload"], dict) or not isinstance(event["digest"], str)):
                raise AiRunReplayError("invalid replay event identity")
            clock.advance()
            timestamp = _non_negative(event["payload"].get("t_ms"), "t_ms")
            if timestamp != round(clock.now_ms(), 3):
                raise AiRunReplayError("replay timestamp disagrees with deterministic clock")
        tape = ReplayTape.from_events(events)
    except AiRunReplayError:
        raise
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
        raise AiRunReplayError("corrupt replay tape") from exc
    return tape, PerfObservation.from_mapping(snapshot["perf"]), PerfBudgets.from_mapping(snapshot["budgets"])


def replay_ai_run(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any], *, budgets: PerfBudgets | None = None
) -> dict[str, Any]:
    """Compare two recorded AI runs. Corrupt input yields CORRUPT, never PASS."""
    try:
        base_tape, _, base_budgets = load_ai_run(baseline)
        cand_tape, cand_perf, _ = load_ai_run(candidate)
    except AiRunReplayError as exc:
        return {"schema": SCHEMA_ID, "verdict": "CORRUPT", "passed": False, "reasons": [str(exc)],
                "divergence": None, "perf": None}
    reasons: list[str] = []
    if any(baseline[key] != candidate[key] for key in ("run_id", "seed", "tick_ms")):
        reasons.append("replay metadata mismatch")
    divergence = base_tape.divergence(cand_tape)
    if divergence is not None:
        reasons.append("ai run diverged")
    perf = evaluate_perf_against_budgets(cand_perf, budgets or base_budgets)
    reasons.extend(perf["reasons"])
    verdict = "PASS" if not reasons else "FAIL"
    return {"schema": SCHEMA_ID, "verdict": verdict, "passed": verdict == "PASS", "reasons": reasons,
            "divergence": divergence, "perf": perf}


def record_scripted_ai_run(
    run_id: str,
    steps: Sequence[Mapping[str, Any]],
    *,
    seed: int = 0,
    tick_ms: float = 16.667,
    budgets: PerfBudgets | None = None,
    policy: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record a scripted AI run; each step may carry 'perf' samples."""
    recorder = AiRunRecorder(run_id=run_id, seed=seed, clock=DeterministicClock(tick_ms))
    for step in steps:
        step = dict(step)
        perf = step.pop("perf", None) or {}
        decision = dict(policy(step)) if policy else step
        recorder.record(str(step.get("kind", "decision")), decision)
        recorder.observe(**perf)
    return recorder.export(budgets)


__all__ = [
    "SCHEMA_ID", "AiRunRecorder", "AiRunReplayError", "PerfBudgets", "PerfObservation",
    "evaluate_perf_against_budgets", "load_ai_run", "record_scripted_ai_run", "replay_ai_run",
]
