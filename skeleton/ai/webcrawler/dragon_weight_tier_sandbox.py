"""Two independent, signed sandboxes before routing-weight and hyper-overlay use.

No neural-model parameters are rewritten. Hyperweights here mean compact,
pre-indexed, rollbackable retrieval overlays, activated only with separately
authenticated review and out-of-sample measured gains.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
import re
from threading import RLock
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json
from .dragon_hundred_matrix_scrutiny import SignedMatrixFinding,scrutinize_one_hundred

HEX=re.compile(r"[0-9a-f]{64}\Z")
WORD=re.compile(r"[a-z0-9]{2,40}")
TIERS=("shadow_to_weight","weight_to_hyper")
def _hash(x):
    if type(x) is not str or HEX.fullmatch(x) is None:
        raise ValueError("canonical digest required")
    return x

@dataclass(frozen=True)
class HoldoutTrial:
    case_id: str
    task_family: str
    source_group: str
    expected_digest: str
    baseline_correct: bool
    candidate_correct: bool
    baseline_latency_ms: float
    candidate_latency_ms: float
    baseline_peak_kib: int
    candidate_peak_kib: int

    def __post_init__(self):
        if (not isinstance(self.case_id,str) or not 2<=len(self.case_id)<=100
            or not isinstance(self.task_family,str) or not 2<=len(self.task_family)<=60
            or not isinstance(self.source_group,str) or not 2<=len(self.source_group)<=100
            or type(self.baseline_correct) is not bool
            or type(self.candidate_correct) is not bool
            or type(self.baseline_peak_kib) is not int or self.baseline_peak_kib<0
            or type(self.candidate_peak_kib) is not int or self.candidate_peak_kib<0):
            raise ValueError("bounded typed holdout observation required")
        _hash(self.expected_digest)
        for x in (self.baseline_latency_ms,self.candidate_latency_ms):
            if type(x) not in (float,int) or not isfinite(x) or x<=0 or x>60000:
                raise ValueError("finite measured benchmark latency required")

@dataclass(frozen=True)
class SealedTierEvaluation:
    owner: str
    candidate_digest: str
    prior_digest: str
    matrix_report_digest: str
    tier: str
    suite_digest: str
    trials: tuple[HoldoutTrial,...]
    holdout_excluded_from_training: bool
    evaluator: str
    key_id: str
    issued_at: int
    expires_at: int
    signature_hex: str

    def body(self):
        return {
            "schema":"skeleton.dragon.tier_evaluation.v1",
            "owner":self.owner,"candidate_digest":self.candidate_digest,
            "prior_digest":self.prior_digest,
            "matrix_report_digest":self.matrix_report_digest,
            "tier":self.tier,"suite_digest":self.suite_digest,
            "trials":[vars(x) for x in self.trials],
            "holdout_excluded_from_training":self.holdout_excluded_from_training,
            "evaluator":self.evaluator,"key_id":self.key_id,
            "issued_at":self.issued_at,"expires_at":self.expires_at,
        }

def qualify_tier(evaluation:SealedTierEvaluation,*,evaluator_public_key:bytes,
                 evaluator:str,key_id:str,now:int,
                 mother_findings:tuple[SignedMatrixFinding,...],
                 mother_public_key:bytes,mother_reviewer:str,mother_key_id:str,
                 mother_knowledge_digest:str,
                 max_latency_ratio:float=1.05,max_memory_ratio:float=1.10)->dict:
    if not isinstance(evaluation,SealedTierEvaluation):
        raise TypeError("sealed independent tier-evaluation required")
    if (type(evaluator_public_key) is not bytes or len(evaluator_public_key)!=32
        or evaluation.evaluator!=evaluator or evaluation.key_id!=key_id
        or evaluation.tier not in TIERS or type(now) is not int
        or evaluation.issued_at>now or now>=evaluation.expires_at
        or evaluation.expires_at-evaluation.issued_at>7*86400
        or evaluation.holdout_excluded_from_training is not True
        or type(max_latency_ratio) not in (float,int) or not 1<=max_latency_ratio<=1.2
        or type(max_memory_ratio) not in (float,int) or not 1<=max_memory_ratio<=1.3):
        raise PermissionError("tier evidence identity/holdout/budget invalid")
    mother=scrutinize_one_hundred(
        evaluation.owner,mother_knowledge_digest,mother_findings,
        public_key=mother_public_key,trusted_reviewer=mother_reviewer,
        key_id=mother_key_id,now=now)
    if (mother["shadow_review_proposal_eligible"] is not True
        or mother["report_digest"]!=evaluation.matrix_report_digest):
        raise PermissionError("100 independently signed fact-check matrices required")
    for x in (evaluation.candidate_digest,evaluation.prior_digest,
              evaluation.matrix_report_digest,evaluation.suite_digest):
        _hash(x)
    if evaluation.candidate_digest==evaluation.prior_digest:
        raise ValueError("no distinct candidate to evaluate")
    trials=evaluation.trials
    if (type(trials) is not tuple or not 12<=len(trials)<=512
        or any(not isinstance(x,HoldoutTrial) for x in trials)):
        raise ValueError("at least 12 actual bounded holdout trials required")
    ids={x.case_id for x in trials}
    families={x.task_family for x in trials}
    groups={x.source_group for x in trials}
    if len(ids)!=len(trials) or len(families)<3 or len(groups)<3:
        raise ValueError("independent holdout variety or unique trials missing")
    if canonical_digest([vars(x) for x in trials])!=evaluation.suite_digest:
        raise ValueError("holdout transcript fingerprint mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(evaluator_public_key).verify(
            bytes.fromhex(evaluation.signature_hex),
            canonical_json(evaluation.body()).encode())
    except (InvalidSignature,ValueError,TypeError) as exc:
        raise PermissionError("tier suite not signed by independent evaluator") from exc
    base=sum(t.baseline_correct for t in trials)
    candidate=sum(t.candidate_correct for t in trials)
    regressions=sum(t.baseline_correct and not t.candidate_correct for t in trials)
    increases=sum(t.candidate_correct and not t.baseline_correct for t in trials)
    baseline_latency=sorted(t.baseline_latency_ms for t in trials)
    candidate_latency=sorted(t.candidate_latency_ms for t in trials)
    ix=(95*len(trials)+99)//100-1
    p95_ratio=candidate_latency[ix]/baseline_latency[ix]
    peak_ratio=max(t.candidate_peak_kib for t in trials)/max(
        1,max(t.baseline_peak_kib for t in trials))
    by_family={
        name: (sum(t.candidate_correct for t in trials if t.task_family==name),
               sum(t.baseline_correct for t in trials if t.task_family==name))
        for name in families
    }
    # A real improvement must be demonstrated, not merely precision at
    # the expense of an existing task or intolerable peak memory/latency.
    qualified=(candidate>base and increases>=2 and regressions==0
        and all(a>=b for a,b in by_family.values())
        and p95_ratio<=max_latency_ratio and peak_ratio<=max_memory_ratio)
    core={
        "schema":"skeleton.dragon.tier_sandbox_verdict.v1",
        "owner":evaluation.owner,"tier":evaluation.tier,
        "candidate_digest":evaluation.candidate_digest,
        "prior_digest":evaluation.prior_digest,
        "matrix_report_digest":evaluation.matrix_report_digest,
        "suite_digest":evaluation.suite_digest,
        "trial_count":len(trials),"task_families":len(families),
        "source_groups":len(groups),"baseline_correct":base,
        "candidate_correct":candidate,"newly_correct":increases,
        "regressions":regressions,
        "p95_latency_ratio":round(p95_ratio,6),
        "peak_memory_ratio":round(peak_ratio,6),
        "promotion_review_eligible":qualified,
        "operator_approval_still_required":True,
        "model_parameters_modified":False,
        "neural_training_authorized":False,
    }
    return {**core,"verdict_digest":canonical_digest(core)}

@dataclass(frozen=True)
class SignedOverlayApproval:
    owner: str
    tier: str
    candidate_digest: str
    verdict_digest: str
    operator: str
    key_id: str
    expires_at: int
    signature_hex: str

    def body(self):
        return {
            "schema":"skeleton.dragon.overlay_approval.v1",
            "owner":self.owner,"tier":self.tier,
            "candidate_digest":self.candidate_digest,
            "verdict_digest":self.verdict_digest,
            "operator":self.operator,"key_id":self.key_id,
            "expires_at":self.expires_at,
        }

class JeevesWeightOverlay:
    """O(1) generation switching, immutable postings, quick rollback.

    Real neural model weights are never mutated; these are bounded
    application-level retrieval routes for the Jeeves runtime.
    """
    def __init__(self,owner:str,*,max_terms:int=4096,max_entries:int=512):
        if not isinstance(owner,str) or not 1<=len(owner)<=128:
            raise ValueError("tenant identity required")
        if not 1<=max_terms<=8192 or not 1<=max_entries<=1024:
            raise ValueError("consumer-grade retrieval budget exceeded")
        self.owner=owner
        self._lock=RLock()
        self._generation=0
        self._active=()
        self._postings={}
        self._active_digest="0"*64
        self._history=[]
        self._term_budget=max_terms
        self._entry_budget=max_entries

    def snapshot(self):
        with self._lock:
            return self._generation,self._postings

    def activate(self,*,entries:tuple[tuple[str,tuple[str,...]],...],
                 verdict:dict,approval:SignedOverlayApproval,
                 evaluation:SealedTierEvaluation,
                 evaluator_public_key:bytes,evaluator:str,evaluator_key_id:str,
                 mother_findings:tuple[SignedMatrixFinding,...],
                 mother_public_key:bytes,mother_reviewer:str,mother_key_id:str,
                 mother_knowledge_digest:str,
                 operator_public_key:bytes,operator:str,key_id:str,
                 now:int,expected_generation:int)->dict:
        if (type(entries) is not tuple or len(entries)>self._entry_budget
            or not entries or not isinstance(verdict,dict)
            or not isinstance(approval,SignedOverlayApproval)
            or type(operator_public_key) is not bytes or len(operator_public_key)!=32
            or approval.owner!=self.owner or verdict.get("owner")!=self.owner
            or approval.tier not in TIERS or approval.tier!=verdict.get("tier")
            or approval.verdict_digest!=verdict.get("verdict_digest")
            or approval.candidate_digest!=verdict.get("candidate_digest")
            or verdict.get("promotion_review_eligible") is not True
            or verdict.get("operator_approval_still_required") is not True
            or verdict.get("neural_training_authorized") is not False
            or approval.operator!=operator or approval.key_id!=key_id
            or type(now) is not int or now>=approval.expires_at):
            raise PermissionError("explicit measured and authorized overlay required")
        checked=qualify_tier(
            evaluation,evaluator_public_key=evaluator_public_key,
            evaluator=evaluator,key_id=evaluator_key_id,now=now,
            mother_findings=mother_findings,mother_public_key=mother_public_key,
            mother_reviewer=mother_reviewer,mother_key_id=mother_key_id,
            mother_knowledge_digest=mother_knowledge_digest)
        if checked!=verdict or not checked["promotion_review_eligible"]:
            raise PermissionError("independently signed sandbox verdict required")
        verified={k:v for k,v in verdict.items() if k!="verdict_digest"}
        if canonical_digest(verified)!=approval.verdict_digest:
            raise ValueError("tampered evaluation verdict")
        normalized=[]
        seen=set()
        for item in entries:
            if (not isinstance(item,tuple) or len(item)!=2
                or type(item[0]) is not str
                or not HEX.fullmatch(item[0])
                or type(item[1]) is not tuple
                or not 1<=len(item[1])<=64
                or any(type(w) is not str or not WORD.fullmatch(w)
                       for w in item[1])
                or len(set(item[1]))!=len(item[1])
                or item[0] in seen):
                raise ValueError("duplicate/invalid bounded retrieval index entry")
            seen.add(item[0]);normalized.append(item)
        if sum(len(x[1]) for x in entries)>self._term_budget:
            raise ValueError("retrieval index too large")
        if canonical_digest([[x,list(words)] for x,words in entries])!=approval.candidate_digest:
            raise ValueError("candidate retrieval index not bound to test verdict")
        try:
            Ed25519PublicKey.from_public_bytes(operator_public_key).verify(
                bytes.fromhex(approval.signature_hex),
                canonical_json(approval.body()).encode())
        except (ValueError,TypeError,InvalidSignature) as exc:
            raise PermissionError("independent operator approval signature invalid") from exc
        postings={}
        for identity,words in normalized:
            for word in words:
                postings.setdefault(word,[]).append(identity)
        immutable_postings={term:tuple(sorted(ids))
                            for term,ids in postings.items()}
        with self._lock:
            if type(expected_generation) is not int or expected_generation!=self._generation:
                raise PermissionError("stale overlay compare-and-swap")
            if evaluation.prior_digest!=self._active_digest:
                raise PermissionError("tier baseline does not match active rollback head")
            if approval.tier=="weight_to_hyper" and self._generation==0:
                raise PermissionError("normal routing weights must precede hyperweights")
            self._history.append((self._generation,self._active,
                                  self._active_digest,self._postings))
            self._history=self._history[-4:]
            self._active=tuple(normalized)
            self._postings=immutable_postings
            self._active_digest=approval.candidate_digest
            self._generation+=1
            return {"generation":self._generation,
                    "index_digest":approval.candidate_digest,
                    "entries":len(self._active),"neural_weights_changed":False,
                    "rollback_available":True}

    def route(self,query:str,*,limit:int=5)->dict:
        if type(query) is not str or len(query)>600 or not 1<=limit<=20:
            raise ValueError("bounded query required")
        terms=set(WORD.findall(query.casefold()))
        generation,postings=self.snapshot()
        scores={}
        for term in terms:
            for identifier in postings.get(term,()):
                scores[identifier]=scores.get(identifier,0)+1
        ranked=sorted(scores,key=lambda identity:(-scores[identity],identity))
        return {"generation":generation,
                "bookmarked_retrieval_ids":ranked[:limit],
                "read_only":True,"neural_weights_changed":False}

    def rollback(self,*,expected_generation:int,authorized:bool)->int:
        if authorized is not True:
            raise PermissionError("trusted rollback required")
        with self._lock:
            if expected_generation!=self._generation or not self._history:
                raise PermissionError("stale or missing rollback target")
            _,self._active,self._active_digest,self._postings=self._history.pop()
            self._generation+=1
            return self._generation
