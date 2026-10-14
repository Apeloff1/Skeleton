"""FLGB-06 deterministic evaluation, reliability, recovery, and release contracts."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS = 256
MAX_CASES = 100_000
MAX_BENCHMARKS = 10_000
MAX_FIXTURES = 100_000
MAX_TRACE_EVENTS = 1_000_000
MAX_METRICS = 100_000
MAX_FAULTS = 10_000
MAX_STEPS = 100_000
MAX_SCORE_PPM = 1_000_000
MAX_TIME_MS = 31_536_000_000


class AssuranceContractError(ValueError):
    """Fail-closed FLGB-06 contract error."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_id(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_ID_CHARS
        or any(ord(ch) < 32 for ch in value)
    ):
        raise AssuranceContractError(f"invalid {name}")
    return value


def require_digest(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise AssuranceContractError(f"invalid {name}")
    return value


def digest_json(value: Any) -> str:
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode("utf-8")
    except (TypeError,ValueError) as exc:
        raise AssuranceContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    input_digest: str
    expected_digest: str
    rubric_digest: str
    weight_ppm: int = MAX_SCORE_PPM

    def __post_init__(self) -> None:
        require_id(self.case_id,"case_id")
        for name in ("input_digest","expected_digest","rubric_digest"): require_digest(getattr(self,name),name)
        if not _is_int(self.weight_ppm) or not 1 <= self.weight_ppm <= MAX_SCORE_PPM:
            raise AssuranceContractError("invalid weight_ppm")


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    output_digest: str
    score_ppm: int
    evidence_digest: str

    def __post_init__(self) -> None:
        require_id(self.case_id,"case_id")
        require_digest(self.output_digest,"output_digest")
        require_digest(self.evidence_digest,"evidence_digest")
        if not _is_int(self.score_ppm) or not 0 <= self.score_ppm <= MAX_SCORE_PPM:
            raise AssuranceContractError("invalid score_ppm")


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    candidate_digest: str
    benchmark_digest: str
    seed_manifest_digest: str
    case_results: tuple[CaseResult,...]

    def __post_init__(self) -> None:
        require_id(self.run_id,"run_id")
        for name in ("candidate_digest","benchmark_digest","seed_manifest_digest"): require_digest(getattr(self,name),name)
        if not self.case_results or len(self.case_results)>MAX_CASES:
            raise AssuranceContractError("evaluation result count out of bounds")
        ids=[r.case_id for r in self.case_results]
        if len(set(ids))!=len(ids): raise AssuranceContractError("duplicate evaluation case result")

    @property
    def digest(self) -> str:
        return digest_json({"run_id":self.run_id,"candidate_digest":self.candidate_digest,"benchmark_digest":self.benchmark_digest,"seed_manifest_digest":self.seed_manifest_digest,"case_results":[r.__dict__ for r in self.case_results]})


def aggregate_score(cases: Sequence[EvaluationCase], run: EvaluationRun) -> int:
    if len(cases)!=len(run.case_results): raise AssuranceContractError("evaluation case/result cardinality mismatch")
    by_id={r.case_id:r for r in run.case_results}
    if set(by_id)!={c.case_id for c in cases}: raise AssuranceContractError("evaluation case/result identity mismatch")
    total_weight=sum(c.weight_ppm for c in cases)
    if total_weight<=0: raise AssuranceContractError("invalid evaluation weight total")
    return sum(by_id[c.case_id].score_ppm*c.weight_ppm for c in cases)//total_weight


@dataclass(frozen=True)
class BenchmarkSpec:
    benchmark_id: str
    version: str
    manifest_digest: str
    heldout: bool
    contamination_scan_digest: str

    def __post_init__(self) -> None:
        require_id(self.benchmark_id,"benchmark_id"); require_id(self.version,"version")
        require_digest(self.manifest_digest,"manifest_digest"); require_digest(self.contamination_scan_digest,"contamination_scan_digest")
        if not isinstance(self.heldout,bool): raise AssuranceContractError("heldout must be boolean")

    @property
    def identity(self) -> tuple[str,str]: return (self.benchmark_id,self.version)


class BenchmarkRegistry:
    def __init__(self, benchmarks: Sequence[BenchmarkSpec]=()) -> None:
        if len(benchmarks)>MAX_BENCHMARKS: raise AssuranceContractError("benchmark registry budget exceeded")
        entries={}
        for item in benchmarks:
            if not isinstance(item,BenchmarkSpec): raise AssuranceContractError("BenchmarkSpec required")
            if item.identity in entries: raise AssuranceContractError("duplicate benchmark identity")
            entries[item.identity]=item
        self._entries=MappingProxyType(entries)

    def register(self,item: BenchmarkSpec) -> "BenchmarkRegistry":
        prior=self._entries.get(item.identity)
        if prior is not None:
            if prior!=item: raise AssuranceContractError("benchmark identity is immutable")
            return self
        return BenchmarkRegistry(tuple(self._entries.values())+(item,))

    def resolve(self,benchmark_id:str,version:str)->BenchmarkSpec:
        key=(require_id(benchmark_id,"benchmark_id"),require_id(version,"version"))
        try: return self._entries[key]
        except KeyError as exc: raise AssuranceContractError("unknown benchmark") from exc

    @property
    def digest(self)->str:
        return digest_json([x.__dict__ for x in sorted(self._entries.values(),key=lambda y:y.identity)])


@dataclass(frozen=True)
class GoldenFixture:
    fixture_id: str
    version: int
    input_digest: str
    expected_digest: str
    provenance_digest: str
    parent_digest: str | None = None

    def __post_init__(self)->None:
        require_id(self.fixture_id,"fixture_id")
        if not _is_int(self.version) or self.version<0: raise AssuranceContractError("invalid fixture version")
        for name in ("input_digest","expected_digest","provenance_digest"): require_digest(getattr(self,name),name)
        if self.parent_digest is not None: require_digest(self.parent_digest,"parent_digest")
        if self.version==0 and self.parent_digest is not None: raise AssuranceContractError("genesis fixture cannot have parent")
        if self.version>0 and self.parent_digest is None: raise AssuranceContractError("fixture update requires parent")

    @property
    def digest(self)->str: return digest_json(self.__dict__)

    def revise(self,expected_digest:str,provenance_digest:str)->"GoldenFixture":
        return GoldenFixture(self.fixture_id,self.version+1,self.input_digest,require_digest(expected_digest,"expected_digest"),require_digest(provenance_digest,"provenance_digest"),self.digest)


@dataclass(frozen=True)
class TraceEvent:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    sequence: int
    event_digest: str

    def __post_init__(self)->None:
        require_id(self.trace_id,"trace_id"); require_id(self.span_id,"span_id")
        if self.parent_span_id is not None: require_id(self.parent_span_id,"parent_span_id")
        if self.parent_span_id==self.span_id: raise AssuranceContractError("trace span cannot parent itself")
        if not _is_int(self.sequence) or self.sequence<0: raise AssuranceContractError("invalid trace sequence")
        require_digest(self.event_digest,"event_digest")


def correlate_trace(events: Sequence[TraceEvent]) -> tuple[TraceEvent,...]:
    if not events or len(events)>MAX_TRACE_EVENTS: raise AssuranceContractError("trace event count out of bounds")
    trace_ids={e.trace_id for e in events}
    if len(trace_ids)!=1: raise AssuranceContractError("cross-trace correlation forbidden")
    span_ids=[e.span_id for e in events]
    if len(set(span_ids))!=len(span_ids): raise AssuranceContractError("duplicate trace span")
    by_id={e.span_id:e for e in events}
    for e in events:
        if e.parent_span_id is not None and e.parent_span_id not in by_id: raise AssuranceContractError("orphan trace parent")
    ordered=tuple(sorted(events,key=lambda e:(e.sequence,e.span_id)))
    seen=set()
    for e in ordered:
        if e.parent_span_id is not None and e.parent_span_id not in seen: raise AssuranceContractError("parent span must precede child")
        seen.add(e.span_id)
    return ordered


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    unit: str
    direction: str
    aggregation: str
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self)->None:
        require_id(self.metric_id,"metric_id"); require_id(self.unit,"unit")
        if self.direction not in {"higher-better","lower-better","target"}: raise AssuranceContractError("invalid metric direction")
        if self.aggregation not in {"sum","mean","max","min","p95","p99","last"}: raise AssuranceContractError("invalid metric aggregation")
        if self.minimum is not None and not _is_int(self.minimum): raise AssuranceContractError("invalid metric minimum")
        if self.maximum is not None and not _is_int(self.maximum): raise AssuranceContractError("invalid metric maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum>self.maximum: raise AssuranceContractError("metric bounds inverted")

    def validate(self,value:int)->int:
        if not _is_int(value): raise AssuranceContractError("metric value must be integer")
        if self.minimum is not None and value<self.minimum: raise AssuranceContractError("metric below minimum")
        if self.maximum is not None and value>self.maximum: raise AssuranceContractError("metric above maximum")
        return value


@dataclass(frozen=True)
class SLOTarget:
    slo_id: str
    objective_ppm: int
    window_units: int

    def __post_init__(self)->None:
        require_id(self.slo_id,"slo_id")
        if not _is_int(self.objective_ppm) or not 1 <= self.objective_ppm <= MAX_SCORE_PPM: raise AssuranceContractError("invalid objective_ppm")
        if not _is_int(self.window_units) or self.window_units<=0: raise AssuranceContractError("invalid window_units")

    @property
    def error_budget_ppm(self)->int: return MAX_SCORE_PPM-self.objective_ppm


def error_budget_remaining(slo:SLOTarget,total:int,failed:int)->int:
    if not _is_int(total) or not _is_int(failed) or total<0 or failed<0 or failed>total: raise AssuranceContractError("invalid SLO counters")
    if total==0: return slo.error_budget_ppm
    consumed=(failed*MAX_SCORE_PPM)//total
    return max(0,slo.error_budget_ppm-consumed)


@dataclass(frozen=True)
class FaultDescriptor:
    fault_id: str
    category: str
    severity: str
    retryable: bool
    operator_action: str

    def __post_init__(self)->None:
        require_id(self.fault_id,"fault_id"); require_id(self.category,"category"); require_id(self.operator_action,"operator_action")
        if self.severity not in {"info","warning","error","critical"}: raise AssuranceContractError("invalid fault severity")
        if not isinstance(self.retryable,bool): raise AssuranceContractError("retryable must be boolean")
        if self.severity=="critical" and self.retryable: raise AssuranceContractError("critical fault cannot auto-retry")


class FaultTaxonomy:
    def __init__(self,faults:Sequence[FaultDescriptor]=())->None:
        if len(faults)>MAX_FAULTS: raise AssuranceContractError("fault taxonomy budget exceeded")
        entries={}
        for fault in faults:
            if fault.fault_id in entries: raise AssuranceContractError("duplicate fault id")
            entries[fault.fault_id]=fault
        self._entries=MappingProxyType(entries)

    def classify(self,fault_id:str)->FaultDescriptor:
        try:return self._entries[require_id(fault_id,"fault_id")]
        except KeyError as exc: raise AssuranceContractError("unclassified fault") from exc


@dataclass(frozen=True)
class RestoreReceipt:
    checkpoint_digest: str
    expected_state_digest: str
    restored_state_digest: str
    replay_cursor: int
    authority_digest: str

    def __post_init__(self)->None:
        for name in ("checkpoint_digest","expected_state_digest","restored_state_digest","authority_digest"): require_digest(getattr(self,name),name)
        if self.expected_state_digest!=self.restored_state_digest: raise AssuranceContractError("restored state digest mismatch")
        if not _is_int(self.replay_cursor) or self.replay_cursor<0: raise AssuranceContractError("invalid replay_cursor")

    @property
    def digest(self)->str: return digest_json(self.__dict__)


@dataclass(frozen=True)
class DisasterRecoveryPlan:
    plan_id: str
    rpo_ms: int
    rto_ms: int
    steps: tuple[str,...]
    evidence_digest: str

    def __post_init__(self)->None:
        require_id(self.plan_id,"plan_id"); require_digest(self.evidence_digest,"evidence_digest")
        for name in ("rpo_ms","rto_ms"):
            value=getattr(self,name)
            if not _is_int(value) or not 0 <= value <= MAX_TIME_MS: raise AssuranceContractError(f"invalid {name}")
        if not self.steps or len(self.steps)>MAX_STEPS or len(set(self.steps))!=len(self.steps): raise AssuranceContractError("invalid DR steps")
        for step in self.steps: require_id(step,"DR step")

    def meets(self,observed_rpo_ms:int,observed_rto_ms:int)->bool:
        if not _is_int(observed_rpo_ms) or not _is_int(observed_rto_ms) or observed_rpo_ms<0 or observed_rto_ms<0: raise AssuranceContractError("invalid observed recovery timing")
        return observed_rpo_ms<=self.rpo_ms and observed_rto_ms<=self.rto_ms


@dataclass(frozen=True)
class RollbackStep:
    sequence: int
    action_id: str
    forward_receipt_digest: str
    rollback_input_digest: str

    def __post_init__(self)->None:
        if not _is_int(self.sequence) or self.sequence<0: raise AssuranceContractError("invalid rollback sequence")
        require_id(self.action_id,"action_id"); require_digest(self.forward_receipt_digest,"forward_receipt_digest"); require_digest(self.rollback_input_digest,"rollback_input_digest")


def rollback_plan(forward_steps: Sequence[RollbackStep])->tuple[RollbackStep,...]:
    if len(forward_steps)>MAX_STEPS: raise AssuranceContractError("rollback step budget exceeded")
    for index,step in enumerate(forward_steps):
        if step.sequence!=index: raise AssuranceContractError("rollback source sequence drift")
    return tuple(reversed(tuple(forward_steps)))


@dataclass(frozen=True)
class DriftSignal:
    metric_id: str
    baseline_ppm: int
    observed_ppm: int
    threshold_ppm: int

    def __post_init__(self)->None:
        require_id(self.metric_id,"metric_id")
        for name in ("baseline_ppm","observed_ppm","threshold_ppm"):
            value=getattr(self,name)
            if not _is_int(value) or not 0 <= value <= MAX_SCORE_PPM: raise AssuranceContractError(f"invalid {name}")

    @property
    def delta_ppm(self)->int: return abs(self.observed_ppm-self.baseline_ppm)

    @property
    def drifted(self)->bool: return self.delta_ppm>self.threshold_ppm


@dataclass(frozen=True)
class QualificationGate:
    gate_id: str
    passed: bool
    critical: bool
    evidence_digest: str

    def __post_init__(self)->None:
        require_id(self.gate_id,"gate_id"); require_digest(self.evidence_digest,"evidence_digest")
        if not isinstance(self.passed,bool) or not isinstance(self.critical,bool): raise AssuranceContractError("qualification flags must be boolean")


@dataclass(frozen=True)
class ReleaseQualification:
    candidate_digest: str
    exact_head_commit: str
    gates: tuple[QualificationGate,...]
    independent_verifier: str

    def __post_init__(self)->None:
        require_digest(self.candidate_digest,"candidate_digest"); require_digest(self.exact_head_commit,"exact_head_commit"); require_id(self.independent_verifier,"independent_verifier")
        if not self.gates or len(self.gates)>MAX_METRICS: raise AssuranceContractError("qualification gate count out of bounds")
        ids=[g.gate_id for g in self.gates]
        if len(set(ids))!=len(ids): raise AssuranceContractError("duplicate qualification gate")

    @property
    def qualified(self)->bool:
        return all(g.passed for g in self.gates if g.critical) and all(g.passed for g in self.gates)

    @property
    def digest(self)->str:
        return digest_json({"candidate_digest":self.candidate_digest,"exact_head_commit":self.exact_head_commit,"gates":[g.__dict__ for g in self.gates],"independent_verifier":self.independent_verifier})
