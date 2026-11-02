"""Read-only runtime doctor; distinguishes assembled code from qualified model."""
from __future__ import annotations
from ..authority.canonical import ContractViolation
from ..orchestration.service import OfflineAIService
from ..orchestration.readiness import readiness
from ..evaluation.fixtures import BASELINE


def inspect(service:OfflineAIService,*,session:str|None=None)->dict:
    report=readiness(service)
    report["model_identity"]={"model_sha256":service.actor.model_digest,
                              "tokenizer_sha256":service.actor.tokenizer_digest}
    report["registered_readonly_tools"]=[row["name"] for row in service.catalog.describe()
                                               if row["risk"]=="readonly"]
    report["benchmark_case_count"]=len(BASELINE)
    report["inference_circuit"]=service.gateway.circuit.health
    if session is not None:
        report["session"]=service.status(session)
    report["proof_holds"]=["real-model-quality-evaluation","clean-machine-install",
                           "exact-head-ci-and-security-gates","portable-model-licensing"]
    return report
