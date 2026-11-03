"""Actually execute policy constructor decisions for all source-fixed vectors."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import GenesisRejected, refuse
from .policy import GenesisPolicy
from .vector_catalog import PolicyVector, iter_vectors, TOTAL_VECTORS
from .canonical import digest


@dataclass(frozen=True,slots=True)
class VectorOutcome:
    vector_id:str
    category:str
    expected:str
    observed:str
    passed:bool
    diagnosis:str

    def record(self)->dict:
        return {k:getattr(self,k) for k in self.__dataclass_fields__}


def evaluate(vector:PolicyVector)->VectorOutcome:
    if type(vector) is not PolicyVector:
        refuse("vector-test-required")
    record={"operator_approved":True}
    record.update(vector.overrides)
    try:
        GenesisPolicy.from_record(record)
    except GenesisRejected as error:
        observed="denied"
        diagnosis=error.code
    else:
        observed="allowed"
        diagnosis="policy-admitted"
    return VectorOutcome(vector.vector_id,vector.category,vector.expected,
                         observed,observed==vector.expected,diagnosis)


def run_all()->dict:
    vectors=tuple(iter_vectors())
    if len(vectors)!=TOTAL_VECTORS:
        refuse("vector-suite-incomplete")
    outcomes=tuple(evaluate(vector) for vector in vectors)
    misses=tuple(x.vector_id for x in outcomes if not x.passed)
    return {
        "schema":"skeleton.native-genesis.policy-results.v1",
        "cases":len(outcomes),
        "passed":sum(x.passed for x in outcomes),
        "failed":len(misses),"failed_ids":list(misses),
        "outcomes":{x.vector_id:x.record() for x in outcomes},
        "source_digest":digest([v.record() for v in vectors]),
        "native_training_executed":False,
        "model_quality_verified":False,
        "release_certified":False,
    }
