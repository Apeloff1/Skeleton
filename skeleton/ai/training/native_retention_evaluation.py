"""Actual local, token-aligned champion/challenger retention measurements.

Produces bounded quality evidence for the existing independent evaluation and
promotion owner. Never applies weights, chooses training data from heldout
cases, or approves a candidate. Inputs are explicitly evaluation-only and
must be pinned by their lawful dataset owner before execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import time
from typing import Callable

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.cortex.transformer import KVCache

from .flgb_training_runtime import DatasetRevision, DatasetRights, digest_json, require_digest, require_id
from .shadow_candidate_gate import ImprovementAxis, ImprovementDirection
from .contamination_scan import MaterializedExample, OverlapPolicy, scan_materialized_overlap

_MAX_CASES = 256
_MAX_STEPS = 16384
_MAX_CASE_BYTES = 16384
_MAX_VOCAB = 131072


def _bounded(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"invalid {label}")


@dataclass(frozen=True, slots=True)
class RetentionCase:
    case_id: str
    capability: str
    text: str
    content_sha256: str
    critical: bool = False

    def __post_init__(self):
        require_id(self.case_id, "case id")
        require_id(self.capability, "capability")
        if (type(self.text) is not str or not self.text.strip()
                or len(self.text) > _MAX_CASE_BYTES
                or len(self.text.encode("utf-8")) > _MAX_CASE_BYTES):
            raise ValueError("invalid bounded heldout text")
        require_digest(self.content_sha256, "heldout content")
        if sha256(self.text.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValueError("heldout source digest mismatch")
        if type(self.critical) is not bool:
            raise ValueError("explicit critical-case policy required")

    @property
    def identity(self):
        return digest_json([self.case_id,self.capability,self.content_sha256,self.critical])


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    max_steps: int = 2048
    max_case_tokens: int = 512
    minimum_cases_per_capability: int = 2
    max_case_nll_increase_ppm: int = 100000
    max_capability_nll_increase_ppm: int = 25000
    max_critical_top1_loss_ppm: int = 0
    max_mean_kl_micronats: int = 250000

    def __post_init__(self):
        for name,lo,hi in (
            ("max_steps",1,_MAX_STEPS),("max_case_tokens",2,4096),
            ("minimum_cases_per_capability",2,32),
            ("max_case_nll_increase_ppm",0,1_000_000),
            ("max_capability_nll_increase_ppm",0,1_000_000),
            ("max_critical_top1_loss_ppm",0,1_000_000),
            ("max_mean_kl_micronats",0,20_000_000),
        ):
            _bounded(getattr(self,name),lo,hi,name)

    @property
    def identity(self):
        return digest_json({k:getattr(self,k) for k in self.__dataclass_fields__})


def corpus_digest(cases: tuple[RetentionCase,...]) -> str:
    if type(cases) is not tuple or not 2 <= len(cases) <= _MAX_CASES:
        raise ValueError("bounded evaluation-only corpus required")
    if any(type(c) is not RetentionCase for c in cases):
        raise ValueError("typed heldout examples required")
    if len({c.case_id for c in cases}) != len(cases) or len({c.content_sha256 for c in cases}) != len(cases):
        raise ValueError("heldout duplicate identity")
    return digest_json([c.identity for c in sorted(cases,key=lambda c:c.case_id)])


@dataclass(frozen=True, slots=True)
class CaseMeasurement:
    case_sha256: str
    capability: str
    tokens: int
    baseline_nll_micronats: int
    candidate_nll_micronats: int
    baseline_correct: int
    candidate_correct: int
    kl_micronats: int
    critical: bool


@dataclass(frozen=True, slots=True)
class RetentionReport:
    baseline_sha256: str
    candidate_sha256: str
    dataset_sha256: str
    policy_sha256: str
    corpus_sha256: str
    training_inventory_sha256: str
    contamination_evidence_sha256: str
    observations: tuple[CaseMeasurement,...]
    axes: tuple[ImprovementAxis,...]
    holds: tuple[str,...]
    evidence_sha256: str

    @property
    def retention_supported(self):
        return not self.holds

    @property
    def promotion_authorized(self):
        return False


def _binding(runtime):
    return (runtime.model_digest,runtime.tokenizer.digest,runtime.architecture.digest,
            runtime.device.digest,runtime.limits,runtime.device_policy)


def _distribution(logits):
    if not logits or len(logits)>_MAX_VOCAB or any(not math.isfinite(x) for x in logits):
        raise ValueError("unqualified native vocabulary logits")
    maximum=max(logits)
    shifted=tuple(x-maximum for x in logits)
    if any(not math.isfinite(x) for x in shifted):
        raise ValueError("unrepresentable logit spread")
    logz=math.log(math.fsum(math.exp(x) for x in shifted))
    return tuple(x-logz for x in shifted)


def evaluate_retention(
    baseline: NativeLLMRuntime, candidate: NativeLLMRuntime,
    cases: tuple[RetentionCase,...], *, dataset: DatasetRevision,
    rights: DatasetRights, expected_baseline_sha256: str,
    expected_candidate_sha256: str, training_item_sha256: frozenset[str],
    expected_training_inventory_sha256: str,
    training_examples: tuple[MaterializedExample,...],
    policy: RetentionPolicy, deadline: float,
    overlap_policy: OverlapPolicy=OverlapPolicy(),
    interrupt: Callable[[],None] | None = None,
) -> RetentionReport:
    """Measure actual logits and heldout targets via the canonical native graph.

    Evaluation consumes exact same-token prefixes on both runtimes. Negative
    log likelihood, next-token accuracy, and forward KL are distinct signals;
    no perplexity-only quality claim. Exact overlap checks rely on an
    independently supplied complete training inventory, not magic leakage
    detection. No code from the texts is executed.
    """
    if type(baseline) is not NativeLLMRuntime or type(candidate) is not NativeLLMRuntime:
        raise ValueError("canonical native runtimes required")
    if baseline is candidate or baseline.model is candidate.model:
        raise ValueError("separate champion and candidate weight graphs required")
    if type(policy) is not RetentionPolicy or type(dataset) is not DatasetRevision or type(rights) is not DatasetRights:
        raise ValueError("explicit evaluation policy and lawful dataset revision required")
    if not rights.permits("evaluation") or rights.dataset_id!=dataset.dataset_id or rights.digest!=dataset.rights_digest:
        raise ValueError("heldout evaluation rights unresolved")
    pinned_corpus=corpus_digest(cases)
    if dataset.content_digest!=pinned_corpus:
        raise ValueError("heldout dataset revision does not bind cases")
    for v in (expected_baseline_sha256,expected_candidate_sha256,expected_training_inventory_sha256):
        require_digest(v,"evaluation identity")
    if (baseline.model_digest!=expected_baseline_sha256 or candidate.model_digest!=expected_candidate_sha256
            or expected_baseline_sha256==expected_candidate_sha256):
        raise ValueError("candidate or champion identity mismatch")
    if type(training_item_sha256) is not frozenset or not 1<=len(training_item_sha256)<=2_000_000:
        raise ValueError("explicit bounded training inventory required")
    for v in training_item_sha256:
        require_digest(v,"training item")
    inventory=digest_json(sorted(training_item_sha256))
    if inventory!=expected_training_inventory_sha256:
        raise ValueError("training inventory changed")
    if any(c.content_sha256 in training_item_sha256 for c in cases):
        raise ValueError("exact training/heldout contamination")
    if (isinstance(deadline,bool) or not isinstance(deadline,(int,float))
            or not math.isfinite(deadline)):
        raise ValueError("finite monotonic deadline required")
    def poll():
        if interrupt is not None:
            interrupt()
        if time.monotonic()>=deadline:
            raise TimeoutError("native retention evaluation deadline")
    poll()
    overlap=scan_materialized_overlap(training_examples,
            tuple(MaterializedExample(c.content_sha256,c.text) for c in cases),
            policy=overlap_policy,interrupt=poll)
    if overlap.training_inventory_sha256!=inventory:
        raise ValueError("materialized training inventory does not equal pinned inventory")
    if overlap.review_required:
        raise ValueError("heldout lexical contamination requires independent review")
    base_binding, candidate_binding=_binding(baseline),_binding(candidate)
    for runtime in (baseline,candidate):
        runtime.assert_model_unchanged()
        runtime.tokenizer.assert_unchanged()
        if (runtime.device.actual!="cpu" or runtime.device.resident
                or runtime.model._accel is not None or runtime.model.use_mod):
            raise ValueError("initial retention qualification requires exact native CPU graphs")
        if runtime.tokenizer.vocab_size>_MAX_VOCAB:
            raise ValueError("native vocabulary exceeds evaluation work bound")
    if (baseline.tokenizer.digest!=candidate.tokenizer.digest
            or baseline.architecture.digest!=candidate.architecture.digest):
        raise ValueError("unaligned tokenizer or architecture")
    prepared=[]
    coverage={}
    token_inventory=set()
    total=0
    for case in sorted(cases,key=lambda c:c.case_id):
        poll()
        a=baseline.encode(case.text)
        b=candidate.encode(case.text)
        if a.token_ids!=b.token_ids:
            raise ValueError("token trajectories do not align")
        ids=a.token_ids
        if (not 2<=len(ids)<=policy.max_case_tokens
                or len(ids)>min(baseline.limits.max_context,candidate.limits.max_context)):
            raise ValueError("heldout case exceeds admitted non-sliding context")
        if ids in token_inventory:
            raise ValueError("duplicate encoded heldout example")
        token_inventory.add(ids)
        total+=len(ids)-1
        if total>policy.max_steps:
            raise ValueError("evaluation token work budget exceeded")
        coverage[case.capability]=coverage.get(case.capability,0)+1
        prepared.append((case,ids))
    if len(coverage)>64 or any(n<policy.minimum_cases_per_capability for n in coverage.values()):
        raise ValueError("insufficient declared capability coverage")
    if not any(c.critical for c in cases):
        raise ValueError("critical heldout cases required")
    records=[]
    for case,ids in prepared:
        poll()
        ca=KVCache(baseline.model.n_layers,baseline.limits.max_context)
        cb=KVCache(candidate.model.n_layers,candidate.limits.max_context)
        nll_a=nll_b=kl=0.0
        correct_a=correct_b=0
        for i in range(1,len(ids)):
            poll()
            prefix=TokenSequence(baseline.tokenizer.digest,ids[:i],
                                 digest_json([case.identity,i]))
            ra=baseline.infer_sequence(prefix,cache=ca,interrupt=poll)
            rb=candidate.infer_sequence(prefix,cache=cb,interrupt=poll)
            pa,pb=_distribution(ra.logits),_distribution(rb.logits)
            target=ids[i]
            nll_a-=pa[target]; nll_b-=pb[target]
            correct_a+=int(ra.argmax_token_id==target)
            correct_b+=int(rb.argmax_token_id==target)
            kl+=max(0.0,math.fsum(math.exp(x)*(x-y) for x,y in zip(pa,pb)))
            poll()
        count=len(ids)-1
        measurements=(nll_a/count,nll_b/count,kl/count)
        if any(not math.isfinite(x) or x<0 or x>1e6 for x in measurements):
            raise ValueError("nonfinite or unrepresentable evaluation metric")
        records.append(CaseMeasurement(case.identity,case.capability,count,
                        round(measurements[0]*1e6),round(measurements[1]*1e6),
                        correct_a,correct_b,round(measurements[2]*1e6),case.critical))
    poll()
    for runtime,binding in ((baseline,base_binding),(candidate,candidate_binding)):
        runtime.assert_model_unchanged()
        runtime.tokenizer.assert_unchanged()
        if _binding(runtime)!=binding:
            raise ValueError("evaluation runtime binding changed")
    holds=[]
    axes=[]
    def relative_loss(old,new,tolerance):
        return (new-old)*1_000_000 > max(old,1)*tolerance
    for row in records:
        if relative_loss(row.baseline_nll_micronats,row.candidate_nll_micronats,
                         policy.max_case_nll_increase_ppm):
            holds.append("case_nll:"+row.case_sha256)
        if row.critical and (row.baseline_correct-row.candidate_correct)*1_000_000 > row.tokens*policy.max_critical_top1_loss_ppm:
            holds.append("critical_top1:"+row.case_sha256)
    for capability in sorted(coverage):
        rows=[r for r in records if r.capability==capability]
        # Use token-weighted NLL within capability; separate per-case gate
        # prevents a long easy sample concealing a short regression.
        tokens=sum(r.tokens for r in rows)
        old=sum(r.baseline_nll_micronats*r.tokens for r in rows)
        new=sum(r.candidate_nll_micronats*r.tokens for r in rows)
        if relative_loss(old,new,policy.max_capability_nll_increase_ppm):
            holds.append("capability_nll:"+capability)
        a=sum(r.baseline_correct for r in rows)*1_000_000//tokens
        b=sum(r.candidate_correct for r in rows)*1_000_000//tokens
        axes.append(ImprovementAxis("native-top1:"+digest_json(capability)[:32],
                                    ImprovementDirection.MAXIMIZE,a,b,
                                    tolerance_ppm=policy.max_critical_top1_loss_ppm,
                                    critical=any(r.critical for r in rows)))
    if sum(r.kl_micronats*r.tokens for r in records)>total*policy.max_mean_kl_micronats:
        holds.append("distribution_drift")
    records=tuple(records)
    evidence=digest_json({
        "baseline":expected_baseline_sha256,"candidate":expected_candidate_sha256,
        "tokenizer":base_binding[1],"architecture":base_binding[2],
        "baseline_device":base_binding[3],"candidate_device":candidate_binding[3],
        "baseline_limits":baseline.limits.to_dict(),"candidate_limits":candidate.limits.to_dict(),
        "dataset":dataset.digest,"rights":rights.digest,"policy":policy.identity,
        "corpus":pinned_corpus,"training_inventory":inventory,
        "contamination_evidence":overlap.evidence_sha256,
        "observations":[{k:getattr(r,k) for k in r.__dataclass_fields__} for r in records],
        "axes":[axis.as_dict() for axis in axes],"holds":sorted(holds),
    })
    return RetentionReport(expected_baseline_sha256,expected_candidate_sha256,
                           dataset.digest,policy.identity,pinned_corpus,inventory,
                           overlap.evidence_sha256,records,tuple(axes),tuple(sorted(holds)),evidence)


__all__=["RetentionCase","RetentionPolicy","CaseMeasurement","RetentionReport","corpus_digest","evaluate_retention"]
