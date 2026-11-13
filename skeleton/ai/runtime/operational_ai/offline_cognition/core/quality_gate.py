"""Finite, exact-source offline AI evaluation; no self-certification.

Quality and latency signals bind immutable model/source/evaluator identities.
A hash-matching quote is never treated as semantic entailment or model truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from .contracts import Scope,sha,identifier,integer,number,text,loads,exact,fingerprint,refuse
from .evaluation import EvaluationCase,evaluate,confusion
from .receipts import NativeReceipt
from .evidence_pipeline import EvidenceIndex,EvidenceSpan

MAX_CASES=10000
MAX_SAMPLES=100000
MAX_CITATIONS=128

@dataclass(frozen=True, slots=True)
class BenchmarkBinding:
    scope: Scope
    benchmark_id: str
    dataset_sha256: str
    evaluator_sha256: str
    policy_sha256: str
    code_sha256: str
    environment_sha256: str
    token_ceiling: int
    approved_sources_declared: bool

    def __post_init__(self):
        if type(self.scope) is not Scope:
            refuse("model and caller scope required")
        identifier(self.benchmark_id)
        for h in (self.dataset_sha256,self.evaluator_sha256,self.policy_sha256,
                  self.code_sha256,self.environment_sha256):
            sha(h)
        integer(self.token_ceiling,minimum=1,maximum=262144)
        if type(self.approved_sources_declared) is not bool:
            refuse("explicit rights assertion required")

    def digest(self):
        return fingerprint({"schema":"offline-benchmark-binding.v1",
            "scope":self.scope.receipt(),"benchmark_id":self.benchmark_id,
            "dataset_sha256":self.dataset_sha256,"evaluator_sha256":self.evaluator_sha256,
            "policy_sha256":self.policy_sha256,"code_sha256":self.code_sha256,
            "environment_sha256":self.environment_sha256,
            "token_ceiling":self.token_ceiling,
            "approved_sources_declared":self.approved_sources_declared})

def evaluate_exact(binding, cases, *, min_cases=100,min_lower_bound=0.95):
    if type(binding) is not BenchmarkBinding or not binding.approved_sources_declared:
        refuse("independently scoped benchmark input required")
    integer(min_cases,minimum=1,maximum=MAX_CASES)
    number(min_lower_bound,minimum=0,maximum=1)
    if type(cases) not in (tuple,list) or len(cases)>MAX_CASES:
        refuse("bounded independent case list required")
    for case in cases:
        if type(case) is not EvaluationCase:
            refuse("typed, externally scored case required")
    scores=evaluate(cases,min_cases=min_cases,min_lower_bound=min_lower_bound)
    return {**scores,"binding_sha256":binding.digest(),
            "evaluator_identity_declared":True,
            "independent_evaluator_execution_proved":False,
            "native_gguf_qualified":False,
            "release_certified":False}

@dataclass(frozen=True, slots=True)
class LatencySample:
    task_id: str
    elapsed_ms: int
    first_token_ms: int
    output_tokens: int
    successful: bool

    def __post_init__(self):
        identifier(self.task_id)
        integer(self.elapsed_ms,minimum=1,maximum=3_600_000)
        integer(self.first_token_ms,minimum=0,maximum=self.elapsed_ms)
        integer(self.output_tokens,maximum=8192)
        if type(self.successful) is not bool:
            refuse("exact outcome bit required")

def distribution(samples, *, min_samples=100):
    integer(min_samples,minimum=1,maximum=MAX_SAMPLES)
    if type(samples) not in (tuple,list) or not 1<=len(samples)<=MAX_SAMPLES:
        refuse("bounded independent latency sample list required")
    if any(type(s) is not LatencySample for s in samples):
        refuse("typed latency record required")
    if len({s.task_id for s in samples})!=len(samples):
        refuse("duplicate latency sample identity")
    ordered=sorted(s.elapsed_ms for s in samples)
    first=sorted(s.first_token_ms for s in samples)
    def p(array, n):
        # Nearest-rank empirical quantile; no invented distribution.
        return array[max(0,(len(array)*n+99)//100-1)]
    total=len(samples)
    successes=sum(s.successful for s in samples)
    return {"samples":total,"successes":successes,"failures":total-successes,
            "latency_ms_p50":p(ordered,50),"latency_ms_p95":p(ordered,95),
            "latency_ms_p99":p(ordered,99),
            "first_token_ms_p95":p(first,95),
            "sample_floor_met":total>=min_samples,
            "p99_evidence_sufficient":total>=100,
            "hardware_benchmark_attested":False}

def inspect_envelope(payload, *, expected_schema):
    """Syntax/shape admission only; LLM content is never authority."""
    identifier(expected_schema)
    value=loads(payload,maximum=262144)
    exact(value,("schema","answer","citations","refusal"))
    if value["schema"]!=expected_schema:
        refuse("unknown response envelope schema")
    text(value["answer"],maximum=131072,allow_empty=True)
    if type(value["refusal"]) is not bool:
        refuse("explicit refusal required")
    if not value["refusal"] and not value["answer"].strip():
        refuse("non-refusal answer cannot be blank")
    citations=value["citations"]
    if type(citations) is not list or len(citations)>MAX_CITATIONS:
        refuse("finite citation array required")
    seen=set()
    for item in citations:
        exact(item,("source_id","source_sha256","start","end","passage_sha256"))
        s=EvidenceSpan(item["source_id"],item["source_sha256"],item["start"],
                       item["end"],item["passage_sha256"])
        key=(s.source_id,s.source_sha256,s.start,s.end)
        if key in seen:
            refuse("duplicate citation must be deduplicated")
        seen.add(key)
    return {"schema":value["schema"],"answer":value["answer"],
            "citation_count":len(citations),"refusal":value["refusal"],
            "model_generated_content_is_policy":False,
            "citations_verified_by_shape_only":False}

def verify_reply_evidence(receipt, index, spans, *, grounding_required):
    """Exact-byte citation proof; separate semantic evaluator still required."""
    if type(receipt) is not NativeReceipt or type(index) is not EvidenceIndex:
        refuse("native output and scoped original index required")
    if type(grounding_required) is not bool:
        refuse("explicit grounding policy required")
    if (receipt.scope.tenant,receipt.scope.subject)!=(index.tenant,index.subject):
        refuse("cross-principal answer-source citation")
    if type(spans) not in (tuple,list) or len(spans)>MAX_CITATIONS:
        refuse("finite evidence span list required")
    if any(type(s) is not EvidenceSpan for s in spans):
        refuse("typed original-byte span required")
    if grounding_required and not spans:
        refuse("grounded reply lacks original source citations")
    proof=index.attribution(spans)
    return {"request_id":receipt.request_id,"output_sha256":receipt.output_sha256,
            "source_receipt_sha256":proof["receipt_sha256"],
            "source_count":len(proof["citations"]),
            "byte_provenance_verified":True,
            "semantic_entailment_proved":False,
            "human_or_independent_evaluator_required":True,
            "automatic_publication_authorized":False}

def refusal_statistics(rows):
    """Evaluate explicit externally scored refusal labels only."""
    if type(rows) not in (tuple,list) or not 1<=len(rows)<=MAX_CASES:
        refuse("bounded referee labels required")
    stats=confusion(rows)
    return {**stats,"independent_referee_proved":False,
            "automatic_promotion":False}

def guarded_review(binding, benchmark, latencies, grounding, *,
                   benchmark_threshold=0.95):
    """Review packet, not a deployment decision or trust promotion."""
    if type(binding) is not BenchmarkBinding:
        refuse("typed benchmark owner required")
    if type(benchmark) is not dict or type(latencies) is not dict or type(grounding) is not dict:
        refuse("typed independent evidence records required")
    if benchmark.get("binding_sha256")!=binding.digest():
        refuse("benchmark source/evaluator/model identity differs")
    if grounding.get("semantic_entailment_proved") is not False:
        refuse("unearned semantic trust assertion")
    threshold=number(benchmark_threshold,minimum=0,maximum=1)
    held=[]
    if benchmark.get("wilson_lower",0)<threshold:
        held.append("quality-floor")
    if not benchmark.get("sample_floor_met",False):
        held.append("benchmark-sample-floor")
    if not latencies.get("sample_floor_met",False):
        held.append("latency-sample-floor")
    if not latencies.get("p99_evidence_sufficient",False):
        held.append("latency-p99-evidence")
    if not grounding.get("byte_provenance_verified",False):
        held.append("source-provenance")
    held.append("independent-semantic-review")
    held.append("real-native-device-rights-and-security")
    return {"binding_sha256":binding.digest(),"state":"review-held",
            "holds":tuple(held),"release_accepted":False,
            "automatic_model_promotion":False}
