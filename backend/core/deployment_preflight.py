"""Attested deployment preflight over assurance and epistemic trust."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib,hmac,json
from typing import Any,Mapping
PREFLIGHT_VERSION=1
@dataclass(frozen=True,slots=True)
class PreflightFinding: id:str; severity:str; detail:str
@dataclass(frozen=True,slots=True)
class DeploymentPreflight:
    version:int; allowed:bool; posture:str; blockers:tuple[PreflightFinding,...]; warnings:tuple[PreflightFinding,...]
    assurance_attestation_sha256:str; system_root_sha256:str; trust_state_sha256:str
    finality_required:bool; finality_satisfied:bool; attestation_sha256:str
def _canonical(v:Any)->bytes:return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()
def _sha(v:Any)->str:return hashlib.sha256(_canonical(v)).hexdigest()
def evaluate_deployment_preflight(*,assurance:Mapping[str,Any],trust:Mapping[str,Any],system_root_sha256:str)->DeploymentPreflight:
    b=[];w=[]; hard=int(assurance.get("hard_failures",0) or 0); posture=str(assurance.get("posture") or "unknown"); aa=str(assurance.get("attestation_sha256") or "")
    if hard or posture=="blocked":b.append(PreflightFinding("assurance.blocked","hard",f"assurance posture={posture}, hard_failures={hard}"))
    if trust.get("integrity_healthy") is not True:b.append(PreflightFinding("trust.integrity","hard","epistemic trust integrity is not healthy"))
    gossip=trust.get("gossip") if isinstance(trust.get("gossip"),Mapping) else {}; split=int(gossip.get("split_views",0) or 0); rollback=int(gossip.get("rollbacks",0) or 0)
    if split:b.append(PreflightFinding("trust.split-view","hard",f"{split} split-view incident(s)"))
    if rollback:b.append(PreflightFinding("trust.rollback","hard",f"{rollback} rollback incident(s)"))
    witnesses=trust.get("witnesses") if isinstance(trust.get("witnesses"),Mapping) else {}; eq=int(witnesses.get("equivocations",0) or 0)
    if eq:b.append(PreflightFinding("trust.witness-equivocation","hard",f"{eq} trusted witness equivocation incident(s)"))
    signed=trust.get("signed_witnesses") if isinstance(trust.get("signed_witnesses"),Mapping) else {}; seq=int(signed.get("equivocations",0) or 0)
    if seq:b.append(PreflightFinding("trust.signed-witness-equivocation","hard",f"{seq} signed witness equivocation incident(s)"))
    policy=trust.get("policy") if isinstance(trust.get("policy"),Mapping) else {}
    normal_required=policy.get("finality_required") is True; signed_required=policy.get("signed_finality_required") is True
    finality_required=normal_required or signed_required; quorum=policy.get("quorum_capable") is True; signed_quorum=policy.get("signed_quorum_capable") is True
    finality_satisfied=trust.get("finality_satisfied") is True
    if normal_required and not quorum:b.append(PreflightFinding("finality.quorum-capability","hard","configured witness groups cannot satisfy required quorum"))
    if signed_required and not signed_quorum:b.append(PreflightFinding("finality.signed-quorum-capability","hard","pinned Ed25519 witness groups cannot satisfy required signed quorum"))
    if finality_required and not finality_satisfied:b.append(PreflightFinding("finality.current-head","hard","current epistemic transparency head is not required-finality complete"))
    elif not finality_required and not finality_satisfied:w.append(PreflightFinding("finality.current-head","warning","current epistemic transparency head is published but not quorum-finalized"))
    if not finality_required and not quorum:w.append(PreflightFinding("finality.quorum-capability","warning","configured witness groups cannot currently satisfy finality quorum"))
    current=trust.get("current_head") if isinstance(trust.get("current_head"),Mapping) else {}
    if int(current.get("current_tree_size",0) or 0)<1:w.append(PreflightFinding("transparency.empty","warning","no epistemic transparency checkpoint has been published"))
    aw=int(assurance.get("warnings",0) or 0)
    if aw:w.append(PreflightFinding("assurance.warnings","warning",f"assurance reports {aw} warning invariant(s)"))
    allowed=not b; p="blocked" if b else ("degraded" if w else "ready"); trust_sha=_sha(dict(trust))
    payload={"version":PREFLIGHT_VERSION,"allowed":allowed,"posture":p,"blockers":[asdict(x) for x in b],"warnings":[asdict(x) for x in w],"assurance_attestation_sha256":aa,"system_root_sha256":str(system_root_sha256),"trust_state_sha256":trust_sha,"finality_required":finality_required,"finality_satisfied":finality_satisfied}
    return DeploymentPreflight(PREFLIGHT_VERSION,allowed,p,tuple(b),tuple(w),aa,str(system_root_sha256),trust_sha,finality_required,finality_satisfied,_sha(payload))
def verify_deployment_preflight(r:DeploymentPreflight)->bool:
    payload={"version":r.version,"allowed":r.allowed,"posture":r.posture,"blockers":[asdict(x) for x in r.blockers],"warnings":[asdict(x) for x in r.warnings],"assurance_attestation_sha256":r.assurance_attestation_sha256,"system_root_sha256":r.system_root_sha256,"trust_state_sha256":r.trust_state_sha256,"finality_required":r.finality_required,"finality_satisfied":r.finality_satisfied}
    return r.version==PREFLIGHT_VERSION and hmac.compare_digest(_sha(payload),r.attestation_sha256)
