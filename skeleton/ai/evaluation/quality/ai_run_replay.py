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
_MAX_RECORDED_EVENT_BYTES = _MAX_JSON_BYTES - 1024 * 1024
_MAX_EVENT_KIND_CHARS = 128
_RUN_FIELDS = frozenset({"schema", "run_id", "seed", "tick_ms", "events", "perf", "budgets", "digest"})


class AiRunReplayError(ValueError):
    """Raised for malformed or tampered AI-run documents (fail closed)."""


def _canonical_bytes(value: Any) -> bytes:
    """Strict, bounded canonical JSON; no key coercion or arbitrary repr."""
    remaining = _MAX_JSON_NODES
    escaped_bytes = _MAX_JSON_BYTES
    active: set[int] = set()

    def visit(item: Any, depth: int = 0) -> None:
        nonlocal remaining, escaped_bytes
        remaining -= 1
        if remaining < 0 or depth > _MAX_JSON_DEPTH:
            raise AiRunReplayError("run JSON shape exceeds bounds")
        if type(item) is str:
            if len(item) + 2 > escaped_bytes:
                raise AiRunReplayError("run JSON text exceeds bounds")
            # Quote and escape bounded slices first: one non-ASCII string
            # must not cause the JSON encoder to allocate many times its
            # admitted byte budget before iterencode can reject the chunk.
            escaped_bytes -= 2
            for start in range(0, len(item), 8192):
                escaped_bytes -= len(json.encoder.encode_basestring_ascii(item[start:start + 8192])) - 2
                if escaped_bytes < 0:
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
    if type(value) not in (int, float):
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

    def __post_init__(self) -> None:
        for key in _PERF_KEYS:
            value = getattr(self, key)
            if value is not None:
                _non_negative(value, key)

    def to_mapping(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in _PERF_KEYS if getattr(self, k) is not None}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "PerfBudgets":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping) or len(payload) > len(_PERF_KEYS) or any(type(k) is not str for k in payload):
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

    def __post_init__(self) -> None:
        for key in _PERF_KEYS:
            values = getattr(self, key)
            if type(values) not in (list, tuple) or len(values) > _MAX_EVENTS:
                raise AiRunReplayError(f"{key} must be a bounded list or tuple")
            object.__setattr__(self, key, tuple(_non_negative(value, key) for value in values))

    def to_mapping(self) -> dict[str, list[float]]:
        return {k: list(getattr(self, k)) for k in _PERF_KEYS}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "PerfObservation":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping) or len(payload) > len(_PERF_KEYS) or any(type(k) is not str for k in payload):
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
    if type(observation) is not PerfObservation or type(budgets) is not PerfBudgets:
        raise AiRunReplayError("typed performance evidence required")
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
    _recorded_bytes: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not 1 <= len(self.run_id) <= 128:
            raise AiRunReplayError("invalid run identity")
        if type(self.seed) is not int or not 0 <= self.seed <= 2**32 - 1:
            raise AiRunReplayError("invalid run seed")
        if not isinstance(self.clock, DeterministicClock) or not isinstance(self.tape, ReplayTape):
            raise AiRunReplayError("typed replay clock and tape required")
        if len(self.tape.events) > _MAX_EVENTS:
            raise AiRunReplayError("event bound exceeded")
        if self.tape.events:
            self._recorded_bytes = len(_canonical_bytes(self.tape.export()))
            if self._recorded_bytes > _MAX_RECORDED_EVENT_BYTES:
                raise AiRunReplayError("cumulative replay event byte budget exceeded")
        observation = self.observation()
        for key in _PERF_KEYS:
            setattr(self, key, list(getattr(observation, key)))

    def record(self, kind: str, payload: Mapping[str, Any]) -> Any:
        if type(kind) is not str or not 1 <= len(kind) <= _MAX_EVENT_KIND_CHARS:
            raise AiRunReplayError("bounded event kind required")
        if (not isinstance(payload, Mapping) or len(payload) > _MAX_JSON_NODES
                or "t_ms" in payload or len(self.tape.events) >= _MAX_EVENTS):
            raise AiRunReplayError("reserved timestamp or event bound exceeded")
        snapshot = json.loads(_canonical_bytes(dict(payload)))
        preview = self.clock.now_ms() + self.clock.tick_ms
        if not math.isfinite(preview) or (self.clock.tick_ms > 0 and preview == self.clock.now_ms()):
            raise AiRunReplayError("logical clock cannot advance")
        snapshot["t_ms"] = round(preview, 3)
        event_bytes = len(_canonical_bytes({
            "sequence": len(self.tape.events), "kind": kind,
            "payload": snapshot, "digest": "0" * 64,
        })) + 1
        if event_bytes > _MAX_RECORDED_EVENT_BYTES - self._recorded_bytes:
            raise AiRunReplayError("cumulative replay event byte budget exceeded")
        try:
            self.clock.advance()
        except ValueError as exc:
            raise AiRunReplayError("logical clock cannot advance") from exc
        event = self.tape.append(kind, snapshot)
        self._recorded_bytes += event_bytes
        return event

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
    if len(document) != len(_RUN_FIELDS) or document.get("schema") != SCHEMA_ID or set(document) != _RUN_FIELDS:
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
    if type(document["digest"]) is not str or document["digest"] != hashlib.sha256(canonical).hexdigest():
        raise AiRunReplayError("ai run digest mismatch")
    snapshot = json.loads(canonical)
    events = snapshot["events"]
    tick = _non_negative(snapshot["tick_ms"], "tick_ms")
    try:
        clock = DeterministicClock(tick)
        for index, event in enumerate(events):
            if not isinstance(event, dict) or set(event) != {"sequence", "kind", "payload", "digest"}:
                raise AiRunReplayError("invalid replay event shape")
            if (type(event["sequence"]) is not int or event["sequence"] != index
                    or type(event["kind"]) is not str or not 1 <= len(event["kind"]) <= _MAX_EVENT_KIND_CHARS
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
        if not isinstance(step, Mapping) or len(step) > _MAX_JSON_NODES:
            raise AiRunReplayError("bounded scripted step required")
        step = dict(step)
        perf = step.pop("perf", None)
        if perf is None:
            perf = {}
        if type(perf) is not dict or len(perf) > len(_PERF_KEYS) or not set(perf) <= set(_PERF_KEYS):
            raise AiRunReplayError("invalid scripted performance fields")
        decision = policy(step) if policy else step
        recorder.record(step.get("kind", "decision"), decision)
        recorder.observe(**perf)
    return recorder.export(budgets)


__all__ = [
    "SCHEMA_ID", "AiRunRecorder", "AiRunReplayError", "PerfBudgets", "PerfObservation",
    "evaluate_perf_against_budgets", "load_ai_run", "record_scripted_ai_run", "replay_ai_run",
]
