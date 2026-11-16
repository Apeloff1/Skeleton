"""Local reasoning economics: finite, empirical, per-stage budget proposals.

No model invocation, permission, tool execution, queue reservation or automatic
retry is provided. A stage's cost is an observational bound, not a deadline
guarantee. The canonical supervisor admits each request independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import islice
import json


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("ascii")).hexdigest()


def _pin(value: str) -> None:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected pinned identity")


def _int(value: int, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid finite budget quantity")


@dataclass(frozen=True, slots=True)
class CalibrationScope:
    model_sha256: str
    runtime_sha256: str
    tokenizer_sha256: str
    profile_sha256: str
    device_sha256: str
    protocol_sha256: str
    thermal_band: str

    def __post_init__(self) -> None:
        for value in (self.model_sha256, self.runtime_sha256, self.tokenizer_sha256,
                      self.profile_sha256, self.device_sha256, self.protocol_sha256):
            _pin(value)
        if self.thermal_band not in ("cool", "warm", "hot"):
            raise ValueError("explicit observed thermal band required")

    @property
    def identity(self) -> str:
        return _hash([self.model_sha256, self.runtime_sha256, self.tokenizer_sha256,
                      self.profile_sha256, self.device_sha256, self.protocol_sha256,
                      self.thermal_band])


@dataclass(frozen=True, slots=True)
class Observation:
    scope_sha256: str
    trial_sha256: str
    stage: str
    input_ceiling: int
    output_ceiling: int
    actual_input_tokens: int
    actual_output_tokens: int
    elapsed_ms: int
    queue_ms: int
    observed_at: int
    success: bool

    def __post_init__(self) -> None:
        _pin(self.scope_sha256)
        _pin(self.trial_sha256)
        if self.stage not in ("answer", "plan", "verify", "repair", "retrieve"):
            raise ValueError("unsupported stage")
        _int(self.input_ceiling, 1, 1_048_576)
        _int(self.output_ceiling, 1, 8192)
        _int(self.actual_input_tokens, 0, 1_048_576)
        _int(self.actual_output_tokens, 0, 8192)
        _int(self.elapsed_ms, 1, 86_400_000)
        _int(self.queue_ms, 0, 86_400_000)
        _int(self.observed_at, 0, (1 << 53)-1)
        if type(self.success) is not bool:
            raise ValueError("explicit outcome required")
        if self.success and (self.actual_input_tokens != self.input_ceiling
                             or self.actual_output_tokens != self.output_ceiling):
            raise ValueError("successful calibration must exercise the full requested shape")


@dataclass(frozen=True, slots=True)
class Stage:
    stage_id: str
    kind: str
    dependencies: tuple[str, ...]
    input_ceiling: int
    output_ceiling: int
    required: bool
    value_bp: int

    def __post_init__(self) -> None:
        _pin(self.stage_id)
        if self.kind not in ("answer", "plan", "verify", "repair", "retrieve"):
            raise ValueError("unsupported stage")
        if type(self.dependencies) is not tuple or len(self.dependencies) > 32:
            raise ValueError("bounded dependency tuple required")
        for item in self.dependencies:
            _pin(item)
        if len(set(self.dependencies)) != len(self.dependencies) or self.stage_id in self.dependencies:
            raise ValueError("duplicate or self dependency")
        _int(self.input_ceiling, 1, 1_048_576)
        _int(self.output_ceiling, 1, 8192)
        _int(self.value_bp, 0, 10000)
        if type(self.required) is not bool:
            raise ValueError("explicit necessity flag required")


@dataclass(frozen=True, slots=True)
class Limits:
    context_tokens: int
    aggregate_input_tokens: int
    aggregate_output_tokens: int
    available_ms: int
    max_stages: int
    max_sample_age_seconds: int = 3600
    min_samples: int = 5
    reserve_bp: int = 1500
    calibration_margin_bp: int = 2000

    def __post_init__(self) -> None:
        _int(self.context_tokens, 2, 1_048_576)
        _int(self.aggregate_input_tokens, 1, 32*1_048_576)
        _int(self.aggregate_output_tokens, 1, 32*8192)
        _int(self.available_ms, 1, 86_400_000)
        _int(self.max_stages, 1, 32)
        _int(self.max_sample_age_seconds, 1, 86400*30)
        _int(self.min_samples, 3, 128)
        _int(self.reserve_bp, 0, 9000)
        _int(self.calibration_margin_bp, 0, 10000)


@dataclass(frozen=True, slots=True)
class Reservation:
    stage: Stage
    estimated_ms: int
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Plan:
    scope_sha256: str
    reservations: tuple[Reservation, ...]
    held: tuple[tuple[str, str], ...]
    input_tokens: int
    output_tokens: int
    estimated_ms: int
    budget_ms: int
    receipt_sha256: str

    @property
    def ready(self) -> bool:
        return bool(self.reservations) and not any(reason.startswith("required:")
                                                 for _, reason in self.held)


def propose(stages: tuple[Stage, ...], observations, *,
            scope: CalibrationScope, limits: Limits, now: int) -> Plan:
    """Reserve required dependency closure before considering optional stages.

    Calibration uses exact input/output ceilings, stage, scope and observed
    thermal band. Any recorded failure in that bucket holds it. No extrapolated
    tokens/sec, cross-device receipts, or speculative credit for cache hits.
    """
    if type(scope) is not CalibrationScope or type(limits) is not Limits:
        raise ValueError("typed calibration scope and limits required")
    _int(now, 0, (1 << 53)-1)
    if type(stages) is not tuple or not 1 <= len(stages) <= 32:
        raise ValueError("bounded stage graph required")
    if any(type(s) is not Stage for s in stages):
        raise ValueError("typed stages required")
    index = {s.stage_id: s for s in stages}
    if len(index) != len(stages):
        raise ValueError("duplicate stage identity")
    if any(dep not in index for s in stages for dep in s.dependencies):
        raise ValueError("missing dependency")
    # Stable topological sort, detects even cycles in optional work.
    ordered = []
    remaining = dict(index)
    while remaining:
        ready = sorted((s for s in remaining.values()
                        if all(dep not in remaining for dep in s.dependencies)),
                       key=lambda s: s.stage_id)
        if not ready:
            raise ValueError("cyclic reasoning graph")
        for s in ready:
            ordered.append(s)
            del remaining[s.stage_id]

    mandatory = {s.stage_id for s in stages if s.required}
    if not mandatory:
        raise ValueError("at least one required stage")
    for s in reversed(ordered):
        if s.stage_id in mandatory:
            mandatory.update(s.dependencies)

    rows = tuple(islice(observations, 4097))
    if len(rows) > 4096 or any(type(o) is not Observation for o in rows):
        raise ValueError("bounded typed calibration required")
    if len({o.trial_sha256 for o in rows}) != len(rows):
        raise ValueError("duplicate calibration trial")
    usable = [o for o in rows if o.scope_sha256 == scope.identity
              and 0 <= now-o.observed_at <= limits.max_sample_age_seconds]
    reservations = {}
    held = {}
    costs = {}
    for s in ordered:
        same = [o for o in usable if (o.stage, o.input_ceiling, o.output_ceiling) ==
                (s.kind, s.input_ceiling, s.output_ceiling)]
        if s.input_ceiling+s.output_ceiling > limits.context_tokens:
            costs[s.stage_id] = "context"
        elif len(same) < limits.min_samples:
            costs[s.stage_id] = "insufficient_calibration"
        elif any(not o.success for o in same):
            costs[s.stage_id] = "recorded_failure"
        else:
            # Max not average: finite sample upper observation, plus margin.
            worst = max(o.elapsed_ms + o.queue_ms for o in same)
            estimate = (worst*(10000+limits.calibration_margin_bp)+9999)//10000
            costs[s.stage_id] = Reservation(s, estimate,
                tuple(sorted(_hash([o.trial_sha256, o.scope_sha256, o.stage,
                                    o.input_ceiling, o.output_ceiling,
                                    o.actual_input_tokens, o.actual_output_tokens, o.elapsed_ms,
                                    o.queue_ms, o.observed_at, o.success]) for o in same)))

    budget = limits.available_ms*(10000-limits.reserve_bp)//10000
    input_used = output_used = time_used = 0

    def admit(s: Stage, required: bool) -> bool:
        nonlocal input_used, output_used, time_used
        prefix = "required:" if required else "optional:"
        cost = costs[s.stage_id]
        if type(cost) is str:
            held[s.stage_id] = prefix + cost
        elif any(dep not in reservations for dep in s.dependencies):
            held[s.stage_id] = prefix + "dependency"
        elif (len(reservations) >= limits.max_stages
              or input_used+s.input_ceiling > limits.aggregate_input_tokens
              or output_used+s.output_ceiling > limits.aggregate_output_tokens
              or time_used+cost.estimated_ms > budget):
            held[s.stage_id] = prefix + "aggregate_budget"
        else:
            reservations[s.stage_id] = cost
            input_used += s.input_ceiling
            output_used += s.output_ceiling
            time_used += cost.estimated_ms
            return True
        return False

    for s in ordered:
        if s.stage_id in mandatory:
            admit(s, True)

    # Required work is atomic at the advisory plan boundary. Do not return
    # an executable-looking partial plan if a required dependency is blocked.
    if any(reason.startswith("required:") for reason in held.values()):
        for s in ordered:
            if s.stage_id not in held:
                held[s.stage_id] = ("required:atomic_hold" if s.stage_id in mandatory
                                    else "optional:required_hold")
        reservations.clear()
        input_used = output_used = time_used = 0
    else:
        optional = {s.stage_id: s for s in ordered if s.stage_id not in mandatory}
        while optional:
            ready = [s for s in optional.values()
                     if all(dep not in optional for dep in s.dependencies)]
            def rank(s):
                cost = costs[s.stage_id]
                return (-(s.value_bp*1_000_000//max(1,cost.estimated_ms))
                        if type(cost) is Reservation else 1, s.stage_id)
            s = min(ready, key=rank)
            admit(s, False)
            del optional[s.stage_id]

    result = tuple(reservations.values())
    held_rows = tuple(sorted(held.items()))
    receipt = _hash({"scope":scope.identity, "now":now,
                     "limits": [getattr(limits,k) for k in limits.__dataclass_fields__],
                     "graph": [[s.stage_id,s.kind,s.dependencies,s.input_ceiling,
                                s.output_ceiling,s.required,s.value_bp] for s in ordered],
                     "chosen":[[r.stage.stage_id,r.estimated_ms,r.evidence] for r in result],
                     "held":held_rows})
    return Plan(scope.identity,result,held_rows,input_used,output_used,
                time_used,budget,receipt)
