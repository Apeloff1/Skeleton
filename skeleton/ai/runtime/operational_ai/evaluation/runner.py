"""Real-model evaluation harness: per-case evidence without false certifications."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from ..authority.canonical import ContractViolation,digest,sha256
from ..authority.budgets import Limits
from ..model.gateway import ModelGateway
from .fixtures import Case,BASELINE


@dataclass(frozen=True,slots=True)
class Observation:
    case_id:str
    case_digest:str
    output_digest:str
    passed:bool
    missing:tuple[str,...]
    prompt_tokens:int
    generated_tokens:int


class EvaluationRunner:
    def __init__(self,gateway:ModelGateway):
        self.gateway=gateway

    def run(self,cases:Iterable[Case]=BASELINE,*,seed:int=0)->dict:
        observations=[]
        for case in cases:
            if not isinstance(case,Case):
                raise ContractViolation("evaluation requires reviewed case contract")
            limits=Limits(context_tokens=8192,output_tokens=case.max_tokens,
                          input_bytes=8192,output_bytes=8192)
            finished=self.gateway.complete([{"role":"user","content":case.prompt}],limits,seed=seed)
            result=finished.generation
            missing=tuple(marker for marker in case.expected_markers if marker.lower() not in result.text.lower())
            observations.append(Observation(case.case_id,case.version,result.output_digest,
                                            not missing,missing,result.prompt_tokens,result.generated_tokens))
        if not observations:
            raise ContractViolation("cannot qualify empty evaluation set")
        passes=sum(1 for o in observations if o.passed)
        data=[{"case_id":o.case_id,"case_sha256":o.case_digest,"output_sha256":o.output_digest,
               "passed":o.passed,"missing_markers":list(o.missing),
               "prompt_tokens":o.prompt_tokens,"generated_tokens":o.generated_tokens}
              for o in observations]
        return {"state":"measured-no-release-attestation","model_digest":self.gateway.backend.model_digest,
                "total":len(data),"passed":passes,"pass_fraction":passes/len(data),
                "observations":data,"suite_sha256":digest(data)}
