"""Original 24-domain policy decision vectors, strict source IDs and group counts."""
from __future__ import annotations
from dataclasses import dataclass
from importlib import resources
from ..native_candidate.strict import decode
from .errors import refuse
from .canonical import digest, required_id

CATEGORIES=(
    "seed","dim","ctx","heads","layers","feed_forward","max_vocab",
    "min_frequency","model_budget","step_budget","learning_rate","batch_lines",
    "known_fraction","wall_budget","license","scope","approval",
    "candidate_only","device","position_mode","norm","ffn","run_id","reserved",
)
PER_CATEGORY=12
TOTAL_VECTORS=288
SCHEMA="skeleton.native-genesis.policy-vector.v1"


@dataclass(frozen=True,slots=True)
class PolicyVector:
    vector_id:str
    category:str
    overrides:dict
    expected:str
    reason:str

    @classmethod
    def from_record(cls,record:dict)->"PolicyVector":
        if type(record) is not dict or set(record)!={
            "schema","id","category","overrides","expected","reason",
        } or record["schema"]!=SCHEMA:
            refuse("policy-vector-schema")
        required_id(record["id"],"vector")
        if record["category"] not in CATEGORIES:
            refuse("policy-vector-category")
        if type(record["overrides"]) is not dict or len(record["overrides"])>4:
            refuse("policy-vector-overrides")
        if record["expected"] not in ("allowed","denied"):
            refuse("policy-vector-outcome")
        if type(record["reason"]) is not str or not 8 <= len(record["reason"]) <= 192:
            refuse("policy-vector-reason")
        if not record["id"].startswith(record["category"]+"_"):
            refuse("policy-vector-identity")
        return cls(record["id"],record["category"],record["overrides"],
                   record["expected"],record["reason"])

    def record(self)->dict:
        return {
            "schema":SCHEMA,"id":self.vector_id,"category":self.category,
            "overrides":self.overrides,"expected":self.expected,
            "reason":self.reason,
        }

    @property
    def digest(self)->str:
        return digest(self.record())


def iter_vectors():
    root=resources.files(__package__)/"vectors"/"v1"
    ids=set()
    for category in CATEGORIES:
        folder=root/category
        count=0
        for path in sorted(folder.iterdir(),key=lambda p:p.name):
            if path.suffix!=".json" or not path.stem.startswith(category+"_"):
                refuse("policy-vector-unexpected-path")
            raw=path.read_bytes()
            if len(raw)>4096:
                refuse("policy-vector-oversize")
            vec=PolicyVector.from_record(decode(raw))
            if vec.vector_id!=path.stem or vec.category!=category:
                refuse("policy-vector-file-mismatch")
            if vec.vector_id in ids:
                refuse("policy-vector-duplicate")
            ids.add(vec.vector_id)
            count+=1
            yield vec
        if count!=PER_CATEGORY:
            refuse("policy-vector-incomplete")
    if len(ids)!=TOTAL_VECTORS:
        refuse("policy-vector-total")


def inventory()->dict:
    items=tuple(iter_vectors())
    return {
        "schema":"skeleton.native-genesis.policy-inventory.v1",
        "count":len(items),"domains":list(CATEGORIES),
        "source_digest":digest([x.record() for x in items]),
        "entries":{x.vector_id:x.digest for x in items},
        "model_trained":False,
    }
