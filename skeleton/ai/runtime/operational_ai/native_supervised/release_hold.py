"""Require exact-head evidence but never self-certify user-facing model release."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import require_sha,require_id
from .errors import reject

REQUIRED=(
    "source_rights","challenge_integrity","no_contamination",
    "training_token_coverage","completion_only_sgd","validation_loss",
    "challenge_768","no_critical_regressions",
    "independent_replay","rollback_verified","device_qualification",
    "clean_installer","merge_readiness","backend_quality","app_e2e",
    "workflow_input_security","sealed_context_guard","malware_gate",
    "artifact_policy","repository_hygiene","secret_scanning","dependency_review",
)


@dataclass(frozen=True,slots=True)
class Gate:
    name:str
    succeeded:bool
    git_sha256:str|None=None
    evidence_sha256:str|None=None

    def __post_init__(self):
        if self.name not in REQUIRED:
            reject("gate-name")
        if type(self.succeeded) is not bool:
            reject("gate-status")
        if self.succeeded:
            if self.git_sha256 is None or self.evidence_sha256 is None:
                reject("gate-proofs-required")
        for key in ("git_sha256","evidence_sha256"):
            val=getattr(self,key)
            if val is not None:
                require_sha(val,key)


def review(gates:tuple[Gate,...],*,exact_head:str)->dict:
    require_sha(exact_head,"exact-head")
    if type(gates) is not tuple or len(gates)>len(REQUIRED):
        reject("gate-set")
    ids=[g.name for g in gates]
    if len(ids)!=len(set(ids)):
        reject("gate-duplicate")
    states={gate.name:gate for gate in gates}
    missing=[name for name in REQUIRED if name not in states]
    mismatched=[name for name in REQUIRED if name in states and
                (not states[name].succeeded or states[name].git_sha256!=exact_head)]
    return {
        "schema":"skeleton.native-supervised.release-hold.v1",
        "exact_head":exact_head,"required":len(REQUIRED),
        "missing":missing,"failed_or_wrong_head":mismatched,
        "all_attested":not missing and not mismatched,
        "automatic_merge":False,
        "automatic_model_promotion":False,
        "release_certified":False,
    }
