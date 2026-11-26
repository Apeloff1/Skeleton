"""Exact and normalized shingle-based heldout contamination screening.

The existing exact-digest contract remains public. New materialized
screening catches copied, reformatted and substantially overlapping
evaluation passages without an external service. Findings only HOLD
examples for independent review; no training rights or quality claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import re
import unicodedata
from typing import Callable

from .flgb_training_runtime import (
    ContaminationFinding, TrainingContractError, scan_contamination,
    digest_json, require_digest,
)

_WORDS=re.compile(r"\w+|[^\s\w]",re.UNICODE)
_MAX_BYTES=16384
_MAX_TRAINING=4096
_MAX_BENCHMARK=256
_MAX_TOTAL_BYTES=32*1024**2
_MAX_POSTINGS=2_000_000
_MAX_HITS=250_000


@dataclass(frozen=True,slots=True)
class MaterializedExample:
    content_sha256:str
    text:str

    def __post_init__(self):
        require_digest(self.content_sha256,"materialized content")
        if type(self.text) is not str or not self.text.strip() or len(self.text)>_MAX_BYTES:
            raise TrainingContractError("invalid materialized contamination example")
        raw=self.text.encode("utf-8")
        if len(raw)>_MAX_BYTES or sha256(raw).hexdigest()!=self.content_sha256:
            raise TrainingContractError("materialized example hash or size mismatch")


@dataclass(frozen=True,slots=True)
class OverlapPolicy:
    shingle_width:int=5
    min_shared_shingles:int=8
    jaccard_floor_ppm:int=800000
    containment_floor_ppm:int=900000

    def __post_init__(self):
        for name,lo,hi in (("shingle_width",3,12),("min_shared_shingles",3,256),
                          ("jaccard_floor_ppm",500000,1000000),
                          ("containment_floor_ppm",500000,1000000)):
            value=getattr(self,name)
            if type(value) is not int or not lo<=value<=hi:
                raise TrainingContractError("invalid contamination screening policy")

    @property
    def digest(self):
        return digest_json({k:getattr(self,k) for k in self.__dataclass_fields__})


@dataclass(frozen=True,slots=True)
class OverlapFinding:
    training_sha256:str
    benchmark_sha256:str
    relation:str
    shared_shingles:int
    jaccard_ppm:int
    containment_ppm:int

    def as_contract(self):
        relation="exact" if self.relation=="exact" else (
            "derived" if self.relation in ("normalized","contained") else "near-duplicate")
        return ContaminationFinding(self.training_sha256,self.benchmark_sha256,relation)


@dataclass(frozen=True,slots=True)
class OverlapReport:
    training_inventory_sha256:str
    benchmark_inventory_sha256:str
    policy_sha256:str
    findings:tuple[OverlapFinding,...]
    examined_training:int
    examined_benchmark:int
    evidence_sha256:str

    @property
    def review_required(self):
        return bool(self.findings)


def _tokens(text):
    # This is only a screening surface. Original corpus bytes and source
    # identities are retained by the caller, not rewritten or normalized.
    return tuple(_WORDS.findall(unicodedata.normalize("NFKC",text).casefold()))


def _digest_tokens(tokens):
    return digest_json(tokens)


def _shingles(tokens,width):
    # Full tuples, not probabilistic hash equality. Distinct shingles avoid
    # artificially high overlap from repeated boilerplate.
    return {tokens[i:i+width] for i in range(len(tokens)-width+1)}


def _inventory(rows,maximum):
    if type(rows) is not tuple or not 1<=len(rows)<=maximum:
        raise TrainingContractError("explicit bounded complete corpus required")
    if any(type(row) is not MaterializedExample for row in rows):
        raise TrainingContractError("typed materialized examples required")
    hashes={row.content_sha256 for row in rows}
    if len(hashes)!=len(rows):
        raise TrainingContractError("duplicate materialized corpus identities")
    if sum(len(row.text.encode("utf-8")) for row in rows)>_MAX_TOTAL_BYTES:
        raise TrainingContractError("materialized contamination corpus exceeds byte budget")
    return digest_json(sorted(hashes))


def scan_materialized_overlap(
    training:tuple[MaterializedExample,...], benchmark:tuple[MaterializedExample,...],
    *, policy:OverlapPolicy=OverlapPolicy(),
    interrupt:Callable[[],None]|None=None,
)->OverlapReport:
    """Screen exact/normalized matches and word-shingle overlap.

    Build bounded postings only for heldout material. Score each training
    example against the subset of benchmark cases sharing exact shingles.
    No probabilistic LSH miss, partial result, or silent budget truncation.
    Repeated boilerplate may cause conservative holds, and paraphrases,
    translations or semantic leakage can still escape this lexical screen.
    """
    if type(policy) is not OverlapPolicy:
        raise TrainingContractError("typed overlap policy required")
    training_digest=_inventory(training,_MAX_TRAINING)
    benchmark_digest=_inventory(benchmark,_MAX_BENCHMARK)
    if interrupt is not None:
        interrupt()
    postings=defaultdict(list)
    normalized=defaultdict(list)
    exact={}
    sizes={}
    postings_count=0
    for row in sorted(benchmark,key=lambda r:r.content_sha256):
        if interrupt is not None:
            interrupt()
        digest=row.content_sha256
        tokens=_tokens(row.text)
        if not tokens:
            raise TrainingContractError("benchmark normalization produced no tokens")
        exact[digest]=digest
        normalized[_digest_tokens(tokens)].append(digest)
        shingles=_shingles(tokens,policy.shingle_width)
        sizes[digest]=len(shingles)
        postings_count+=len(shingles)
        if postings_count>_MAX_POSTINGS:
            raise TrainingContractError("benchmark shingle posting budget exceeded")
        for shingle in shingles:
            postings[shingle].append(digest)
    findings=[]
    work=0
    for row in sorted(training,key=lambda r:r.content_sha256):
        if interrupt is not None:
            interrupt()
        digest=row.content_sha256
        tokens=_tokens(row.text)
        if not tokens:
            raise TrainingContractError("training normalization produced no tokens")
        shingles=_shingles(tokens,policy.shingle_width)
        norm_matches=set(normalized.get(_digest_tokens(tokens),()))
        counts=Counter()
        for index,shingle in enumerate(shingles):
            if interrupt is not None and index%128==0:
                interrupt()
            batch=postings.get(shingle,())
            work+=len(batch)
            if work>_MAX_HITS:
                raise TrainingContractError("contamination intersection work budget exceeded")
            counts.update(batch)
        relevant=set(counts)|norm_matches
        if digest in exact:
            relevant.add(digest)
        for other in sorted(relevant):
            shared=counts[other]
            union=len(shingles)+sizes[other]-shared
            smaller=min(len(shingles),sizes[other])
            jac=shared*1_000_000//union if union else 0
            containment=shared*1_000_000//smaller if smaller else 0
            if digest==other:
                relation="exact"
            elif other in norm_matches:
                relation="normalized"
            elif shared<policy.min_shared_shingles:
                continue
            elif jac>=policy.jaccard_floor_ppm:
                relation="near-duplicate"
            elif containment>=policy.containment_floor_ppm:
                relation="contained"
            else:
                continue
            findings.append(OverlapFinding(digest,other,relation,shared,jac,containment))
            if len(findings)>_MAX_HITS:
                raise TrainingContractError("contamination finding budget exceeded")
    findings=tuple(findings)
    evidence=digest_json({
        "training":training_digest,"benchmark":benchmark_digest,"policy":policy.digest,
        "examined":[len(training),len(benchmark)],
        "findings":[[r.training_sha256,r.benchmark_sha256,r.relation,
                     r.shared_shingles,r.jaccard_ppm,r.containment_ppm] for r in findings],
    })
    if interrupt is not None:
        interrupt()
    return OverlapReport(training_digest,benchmark_digest,policy.digest,findings,
                         len(training),len(benchmark),evidence)


__all__=[
    "ContaminationFinding","TrainingContractError","scan_contamination",
    "MaterializedExample","OverlapPolicy","OverlapFinding","OverlapReport",
    "scan_materialized_overlap",
]
