"""Jeeves 100-level adversarial release engine.

All candidates cross the same fail-closed release boundary. Local deterministic
checks are always run. An optional batch judge can deepen semantic checks in at
most ten category calls instead of one call per gate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple


class GateStatus(str, Enum):
    PASS = "pass"
    REPAIR = "repair"
    BLOCK = "block"


CRITICAL_GATES = frozenset({12, 20, 23, 31, 59, 60, 71, 90, 91, 93, 95, 96, 98, 99, 100})

_GATE_NAMES: Tuple[str, ...] = (
    'Intent integrity',
    'Ambiguity attack',
    'Missing-variable check',
    'Contradiction check',
    'Scope containment',
    'Assumption inventory',
    'Instruction hierarchy',
    'Context relevance',
    'Context poisoning detection',
    'Objective verification',
    'Source existence',
    'Evidence attachment',
    'Primary-source preference',
    'Source independence',
    'Authority evaluation',
    'Evidence freshness',
    'Evidence completeness',
    'Citation consistency',
    'Quote integrity',
    'Unsupported-claim blocker',
    'Timestamp validation',
    'Clock synchronization',
    'Future-information leakage',
    'Stale-feed detection',
    'Market-session awareness',
    'Corporate-action adjustment',
    'Currency normalization',
    'Exchange/timezone normalization',
    'Historical revision detection',
    'Snapshot reproducibility',
    'Arithmetic recomputation',
    'Unit analysis',
    'Alternative derivation',
    'Boundary-condition testing',
    'Counterexample search',
    'Causal-vs-correlational test',
    'Base-rate challenge',
    'Selection-bias attack',
    'Survivorship-bias attack',
    'Logical-chain reconstruction',
    'Contrarian agent',
    "Devil's-advocate agent",
    'False-premise injection test',
    'Confidence manipulation test',
    'Consensus manipulation test',
    'Popularity-vs-truth test',
    'Narrative seduction test',
    'Anchoring attack',
    'Framing attack',
    'Adversarial paraphrase',
    'Market-manipulation awareness',
    'Abnormal-volume challenge',
    'Liquidity test',
    'Spread/slippage test',
    'Transaction-cost test',
    'Volatility regime test',
    'Tail-risk test',
    'Scenario inversion',
    'Forecast calibration',
    'Prediction-vs-fact separation',
    'Model disagreement',
    'Ensemble dispersion',
    'Sensitivity analysis',
    'Parameter fragility',
    'Overfitting attack',
    'Out-of-sample test',
    'Regime-shift simulation',
    'Random-baseline comparison',
    'Simple-model comparison',
    'Uncertainty propagation',
    'Tool-output validation',
    'Tool disagreement check',
    'API-error interpretation',
    'Partial-response detection',
    'Schema validation',
    'Rate-limit degradation',
    'Fallback-provider verification',
    'Cache-integrity check',
    'Retry duplication test',
    'Tool provenance',
    'Code syntax validation',
    'Static-analysis challenge',
    'Dependency verification',
    'Version compatibility',
    'Test-generation adversary',
    'Negative-path tests',
    'Resource-exhaustion check',
    'Concurrency challenge',
    'Rollback viability',
    'Side-effect boundary',
    'Secret detection',
    'Data-minimization check',
    'Prompt-injection resistance',
    'Cross-user/context isolation',
    'Hallucination sweep',
    'Internal consistency sweep',
    'Fact-first ordering',
    'Confidence ceiling',
    'Independent final judge',
    'Release seal',
)

_CATEGORIES = (
    "request_integrity", "evidence", "time_data", "logic",
    "adversarial_reasoning", "market_forecast", "model_validation",
    "tools", "code_execution", "security_release",
)


@dataclass(frozen=True)
class GateSpec:
    gate_id: int
    name: str
    category: str
    critical: bool = False


@dataclass(frozen=True)
class GateResult:
    gate_id: int
    name: str
    status: GateStatus
    reason: str
    confidence: float = 1.0
    critical: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
            "confidence": round(float(self.confidence), 6),
            "critical": self.critical,
        }


@dataclass(frozen=True)
class AdversarialContext:
    request: str
    candidate: Any
    evidence: Tuple[Mapping[str, Any], ...] = ()
    tool_outputs: Tuple[Mapping[str, Any], ...] = ()
    external_content: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    requires_evidence: bool = False
    is_prediction: bool = False
    has_side_effects: bool = False


@dataclass(frozen=True)
class ReleaseDecision:
    allowed: bool
    score: float
    results: Tuple[GateResult, ...]
    candidate: Any
    repair_rounds: int = 0
    seal: Optional[str] = None

    @property
    def blockers(self) -> Tuple[GateResult, ...]:
        return tuple(r for r in self.results if r.status is GateStatus.BLOCK)

    @property
    def repairs(self) -> Tuple[GateResult, ...]:
        return tuple(r for r in self.results if r.status is GateStatus.REPAIR)


class AdversarialReleaseBlocked(RuntimeError):
    def __init__(self, decision: ReleaseDecision):
        failed = [r.gate_id for r in decision.results if r.status is not GateStatus.PASS]
        super().__init__(f"Jeeves adversarial release blocked by gates: {failed}")
        self.decision = decision


BatchJudge = Callable[[AdversarialContext, Tuple[GateSpec, ...]], Mapping[int, Any]]
Repairer = Callable[[AdversarialContext, Tuple[GateResult, ...]], Any]


def gate_registry() -> Tuple[GateSpec, ...]:
    return tuple(
        GateSpec(i, name, _CATEGORIES[(i - 1) // 10], i in CRITICAL_GATES)
        for i, name in enumerate(_GATE_NAMES, 1)
    )


def _snapshot(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _snapshot(value.to_dict())
    if is_dataclass(value):
        return _snapshot(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _snapshot(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_snapshot(v) for v in value]
    return repr(value)


def _review_state(ctx: AdversarialContext) -> Dict[str, Any]:
    """Snapshot nested state a semantic judge may observe but never mutate."""
    return {
        "request": ctx.request,
        "candidate": _snapshot(ctx.candidate),
        "evidence": _snapshot(ctx.evidence),
        "tool_outputs": _snapshot(ctx.tool_outputs),
        "external_content": _snapshot(ctx.external_content),
        "metadata": _snapshot(ctx.metadata),
        "confidence": float(ctx.confidence),
        "requires_evidence": bool(ctx.requires_evidence),
        "is_prediction": bool(ctx.is_prediction),
        "has_side_effects": bool(ctx.has_side_effects),
    }


_REVIEW_IMMUTABLE_ATOMS = (type(None), bool, int, float, complex, str, bytes, range)


def _mutable_graph_ids(value: Any, seen: Optional[set[int]] = None) -> set[int]:
    """Collect mutable/opaque identities so deceptive deepcopy aliases fail closed."""
    if isinstance(value, _REVIEW_IMMUTABLE_ATOMS):
        return set()
    if seen is None:
        seen = set()
    object_id = id(value)
    if object_id in seen:
        return set()
    seen.add(object_id)

    identities: set[int] = set()
    children: Iterable[Any] = ()
    if isinstance(value, Mapping):
        identities.add(object_id)
        children = tuple(value.keys()) + tuple(value.values())
    elif isinstance(value, (list, set, bytearray)):
        identities.add(object_id)
        children = value
    elif isinstance(value, (tuple, frozenset)):
        children = value
    else:
        # Unknown non-primitive objects are treated as mutable security state.
        # If deepcopy intentionally returns the same instance, the overlap below
        # proves the isolation boundary is not trustworthy.
        identities.add(object_id)
        try:
            children = tuple(vars(value).values())
        except (TypeError, AttributeError):
            children = ()

    for child in children:
        identities.update(_mutable_graph_ids(child, seen))
    return identities


def _isolated_review_context(ctx: AdversarialContext) -> AdversarialContext:
    """Deep-isolate untrusted judge callbacks from caller and repairer state."""
    isolated: Optional[AdversarialContext]
    try:
        isolated = deepcopy(ctx)
        shared_mutable = _mutable_graph_ids(ctx) & _mutable_graph_ids(isolated)
        semantically_equal = _review_state(ctx) == _review_state(isolated)
    except Exception:
        isolated = None
        shared_mutable = set()
        semantically_equal = False
    if isolated is None or shared_mutable or not semantically_equal:
        raise RuntimeError(
            "adversarial invariant violated: judge review context isolation failed"
        )
    return isolated


def _text(value: Any) -> str:
    try:
        return json.dumps(_snapshot(value), sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError, OverflowError):
        return repr(value)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _status(value: Any) -> Optional[GateStatus]:
    if isinstance(value, GateStatus):
        return value
    if isinstance(value, bool):
        return GateStatus.PASS if value else GateStatus.BLOCK
    if isinstance(value, str):
        try:
            return GateStatus(value.lower())
        except ValueError:
            return None
    return None


def _result(spec: GateSpec, status: GateStatus, reason: str, confidence: float = 1.0) -> GateResult:
    return GateResult(spec.gate_id, spec.name, status, reason, confidence, spec.critical)


def _override(spec: GateSpec, meta: Mapping[str, Any]) -> Optional[GateResult]:
    """Return only fail-closed explicit overrides.

    Overrides are diagnostic/test inputs, not an authorization path. Accepting
    PASS or REPAIR here would bypass deterministic blockers because overrides are
    evaluated before the baseline gate logic. Therefore overrides may only make a
    gate stricter by forcing BLOCK; weaker statuses are ignored.
    """
    values = meta.get("gate_overrides", {})
    if not isinstance(values, Mapping):
        return None
    raw = values.get(spec.gate_id, values.get(str(spec.gate_id), values.get(spec.name)))
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        status = _status(raw.get("status")) or GateStatus.BLOCK
        reason = str(raw.get("reason") or "explicit gate override")
        confidence = float(raw.get("confidence", 1.0))
    else:
        status = _status(raw) or GateStatus.BLOCK
        reason = "explicit gate override"
        confidence = 1.0
    if status is not GateStatus.BLOCK:
        return None
    return _result(spec, GateStatus.BLOCK, reason, confidence)


def _adverse(spec: GateSpec, meta: Mapping[str, Any], *aliases: str) -> bool:
    signals = meta.get("adverse_signals", {})
    keys = (spec.gate_id, str(spec.gate_id), spec.name, _slug(spec.name), *aliases)
    for key in keys:
        if bool(meta.get(key, False)):
            return True
        if isinstance(signals, Mapping) and bool(signals.get(key, False)):
            return True
    return False


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*\b", re.IGNORECASE),
)
_INJECTION_MARKERS = (
    "ignore previous instructions", "ignore all previous",
    "system message:", "developer message:", "<|im_start|>",
    "<|system|>", "do not follow the above",
)


def _baseline(spec: GateSpec, ctx: AdversarialContext, prior: Sequence[GateResult]) -> GateResult:
    meta = ctx.metadata
    explicit = _override(spec, meta)
    if explicit is not None:
        return explicit
    i = spec.gate_id

    if i == 1 and not (ctx.request or "").strip():
        return _result(spec, GateStatus.BLOCK, "empty request has no releasable intent")
    if i == 2 and _adverse(spec, meta, "ambiguous_intent"):
        return _result(spec, GateStatus.REPAIR, "material ambiguity remains")
    if i == 3 and _adverse(spec, meta, "missing_variables", "missing_required_inputs"):
        return _result(spec, GateStatus.REPAIR, "required variables are missing")
    if i == 4 and _adverse(spec, meta, "contradictions"):
        return _result(spec, GateStatus.REPAIR, "requirements contradict each other")
    if i == 7 and _adverse(spec, meta, "instruction_conflict"):
        return _result(spec, GateStatus.BLOCK, "instruction hierarchy is unresolved")
    if i == 9 and _adverse(spec, meta, "context_poisoning"):
        return _result(spec, GateStatus.BLOCK, "context poisoning detected")

    if 11 <= i <= 20 and not ctx.requires_evidence:
        if i == 20 and _adverse(spec, meta, "unsupported_claims", "hallucinated_claims"):
            return _result(spec, GateStatus.BLOCK, "unsupported factual claim detected")
        return _result(spec, GateStatus.PASS, "not applicable: creation does not require external evidence")
    if i == 11 and not ctx.evidence:
        return _result(spec, GateStatus.REPAIR, "evidence-required output has no sources")
    if i == 12 and (not ctx.evidence or _adverse(spec, meta, "unattached_claims")):
        return _result(spec, GateStatus.BLOCK, "material claims are not attached to evidence")
    if i == 20 and _adverse(spec, meta, "unsupported_claims"):
        return _result(spec, GateStatus.BLOCK, "unsupported factual claim remains")

    if i == 23 and _adverse(spec, meta, "future_information_leakage"):
        return _result(spec, GateStatus.BLOCK, "future-information leakage detected")
    if i == 31 and _adverse(spec, meta, "arithmetic_error"):
        return _result(spec, GateStatus.BLOCK, "arithmetic recomputation failed")

    if 51 <= i <= 60 and not ctx.is_prediction and not bool(meta.get("market_analysis")):
        return _result(spec, GateStatus.PASS, "not applicable: candidate is not a forecast")
    if i == 59 and _adverse(spec, meta, "forecast_uncalibrated"):
        return _result(spec, GateStatus.BLOCK, "forecast is not calibrated")
    if i == 60 and _adverse(spec, meta, "prediction_fact_blurred"):
        return _result(spec, GateStatus.BLOCK, "prediction and fact are not separated")

    if i == 71:
        if any(bool(out.get("error")) or out.get("ok") is False for out in ctx.tool_outputs):
            return _result(spec, GateStatus.BLOCK, "tool output reports an error")

    if i == 90 and ctx.has_side_effects and not bool(meta.get("side_effects_authorized")):
        return _result(spec, GateStatus.BLOCK, "side effects were not explicitly authorized")

    if i == 91 and any(p.search(_text(ctx.candidate)) for p in _SECRET_PATTERNS):
        return _result(spec, GateStatus.BLOCK, "candidate appears to expose a credential or private key")
    if i == 93:
        haystack = "\n".join(ctx.external_content).lower()
        if haystack and any(marker in haystack for marker in _INJECTION_MARKERS):
            return _result(spec, GateStatus.BLOCK, "prompt-injection marker found in untrusted content")
    if i == 95 and _adverse(spec, meta, "hallucinated_claims"):
        return _result(spec, GateStatus.BLOCK, "hallucination signal remains")
    if i == 96 and _adverse(spec, meta, "internal_inconsistency"):
        return _result(spec, GateStatus.BLOCK, "candidate is internally inconsistent")
    if i == 98:
        evidence_conf = meta.get("evidence_confidence")
        if evidence_conf is not None and float(ctx.confidence) > float(evidence_conf) + 1e-9:
            return _result(spec, GateStatus.BLOCK, "candidate confidence exceeds evidence confidence")
    if i == 99:
        if bool(meta.get("require_independent_judge")) and not bool(meta.get("independent_judge_passed")):
            return _result(spec, GateStatus.BLOCK, "required independent judge has not approved")
        if any(r.status is GateStatus.BLOCK for r in prior):
            return _result(spec, GateStatus.BLOCK, "independent arbiter observes an earlier blocker")

    if _adverse(spec, meta):
        status = GateStatus.BLOCK if spec.critical else GateStatus.REPAIR
        return _result(spec, status, f"adverse signal: {_slug(spec.name)}")

    return _result(spec, GateStatus.PASS, "check completed with no adverse signal")


class AdversarialEngine:
    def __init__(
        self,
        *,
        threshold: float = 95.0,
        max_repair_rounds: int = 2,
        judge: Optional[BatchJudge] = None,
        repairer: Optional[Repairer] = None,
        seal_key: Optional[bytes] = None,
    ) -> None:
        if not 0.0 <= float(threshold) <= 100.0:
            raise ValueError("threshold must be between 0 and 100")
        if int(max_repair_rounds) < 0:
            raise ValueError("max_repair_rounds must be >= 0")
        self.threshold = float(threshold)
        self.max_repair_rounds = int(max_repair_rounds)
        self.judge = judge
        self.repairer = repairer
        if seal_key is None:
            raw_key = os.getenv("SKELETON_ADVERSARIAL_SEAL_KEY")
            seal_key = raw_key.encode("utf-8") if raw_key else None
        self.seal_key = seal_key
        self.registry = gate_registry()

    def evaluate(self, ctx: AdversarialContext) -> ReleaseDecision:
        current = ctx
        rounds = 0
        while True:
            results = list(self._evaluate_1_to_99(current))
            blockers = tuple(r for r in results if r.status is GateStatus.BLOCK)
            repairs = tuple(r for r in results if r.status is GateStatus.REPAIR)

            if repairs and not blockers and self.repairer is not None and rounds < self.max_repair_rounds:
                current = replace(current, candidate=self.repairer(current, repairs))
                rounds += 1
                continue

            ratio = 100.0 * sum(r.status is GateStatus.PASS for r in results) / 99.0
            seal_spec = self.registry[99]
            if blockers:
                gate100 = _result(seal_spec, GateStatus.BLOCK, "release seal denied: blocker remains")
            elif repairs:
                gate100 = _result(seal_spec, GateStatus.BLOCK, "release seal denied: repair remains unresolved")
            elif ratio + 1e-9 < self.threshold:
                gate100 = _result(seal_spec, GateStatus.BLOCK, f"release score {ratio:.2f} below {self.threshold:.2f}")
            else:
                gate100 = _result(seal_spec, GateStatus.PASS, "release preconditions satisfied")

            all_results = tuple(results) + (gate100,)
            score = float(sum(r.status is GateStatus.PASS for r in all_results))
            allowed = gate100.status is GateStatus.PASS
            seal = self._make_seal(current, all_results, rounds) if allowed else None
            return ReleaseDecision(allowed, score, all_results, current.candidate, rounds, seal)

    def guard(self, ctx: AdversarialContext) -> Any:
        decision = self.evaluate(ctx)
        if not decision.allowed:
            raise AdversarialReleaseBlocked(decision)
        return decision.candidate

    def _evaluate_1_to_99(self, ctx: AdversarialContext) -> Tuple[GateResult, ...]:
        specs = self.registry[:99]
        results = [_baseline(spec, ctx, ()) for spec in specs]

        if self.judge is not None:
            review_ctx = _isolated_review_context(ctx)
            for start in range(0, 99, 10):
                batch = tuple(specs[start:min(start + 10, 99)])
                before = _review_state(review_ctx)
                verdicts = self.judge(review_ctx, batch) or {}
                if _review_state(review_ctx) != before:
                    raise RuntimeError(
                        "adversarial invariant violated: judge mutated review context"
                    )
                for spec in batch:
                    if spec.gate_id not in verdicts:
                        continue
                    idx = spec.gate_id - 1
                    judged = self._coerce(spec, verdicts[spec.gate_id])
                    severity = {GateStatus.PASS: 0, GateStatus.REPAIR: 1, GateStatus.BLOCK: 2}
                    if severity[judged.status] > severity[results[idx].status]:
                        results[idx] = judged

        baseline99 = _baseline(specs[98], ctx, tuple(results[:98]))
        if baseline99.status is GateStatus.BLOCK or results[98].status is GateStatus.PASS:
            results[98] = baseline99
        return tuple(results)

    @staticmethod
    def _coerce(spec: GateSpec, raw: Any) -> GateResult:
        if isinstance(raw, GateResult):
            return _result(spec, raw.status, raw.reason, raw.confidence)
        if isinstance(raw, Mapping):
            return _result(
                spec,
                _status(raw.get("status")) or GateStatus.BLOCK,
                str(raw.get("reason") or "batch judge verdict"),
                float(raw.get("confidence", 1.0)),
            )
        return _result(spec, _status(raw) or GateStatus.BLOCK, "batch judge verdict")

    def _make_seal(
        self,
        ctx: AdversarialContext,
        results: Sequence[GateResult],
        rounds: int,
    ) -> str:
        record = {
            "request": ctx.request,
            "candidate": _snapshot(ctx.candidate),
            "results": [r.to_dict() for r in results],
            "repair_rounds": rounds,
            "version": 1,
        }
        payload = json.dumps(
            record, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), default=str,
        ).encode("utf-8")
        if self.seal_key:
            return "hmac-sha256:" + hmac.new(self.seal_key, payload, hashlib.sha256).hexdigest()
        return "sha256:" + hashlib.sha256(payload).hexdigest()


_DEFAULT_ENGINE = AdversarialEngine()


def evaluate_creation(
    *,
    request: str,
    candidate: Any,
    evidence: Iterable[Mapping[str, Any]] = (),
    tool_outputs: Iterable[Mapping[str, Any]] = (),
    external_content: Iterable[str] = (),
    metadata: Optional[Mapping[str, Any]] = None,
    confidence: float = 1.0,
    requires_evidence: bool = False,
    is_prediction: bool = False,
    has_side_effects: bool = False,
    engine: Optional[AdversarialEngine] = None,
) -> ReleaseDecision:
    ctx = AdversarialContext(
        request=request,
        candidate=candidate,
        evidence=tuple(evidence),
        tool_outputs=tuple(tool_outputs),
        external_content=tuple(external_content),
        metadata=dict(metadata or {}),
        confidence=float(confidence),
        requires_evidence=bool(requires_evidence),
        is_prediction=bool(is_prediction),
        has_side_effects=bool(has_side_effects),
    )
    return (engine or _DEFAULT_ENGINE).evaluate(ctx)


def guard_creation(**kwargs: Any) -> Any:
    decision = evaluate_creation(**kwargs)
    if not decision.allowed:
        raise AdversarialReleaseBlocked(decision)
    return decision.candidate


__all__ = [
    "AdversarialContext", "AdversarialEngine", "AdversarialReleaseBlocked",
    "CRITICAL_GATES", "GateResult", "GateSpec", "GateStatus",
    "ReleaseDecision", "evaluate_creation", "gate_registry", "guard_creation",
]
