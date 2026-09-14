"""Strongest portable trust envelope: claim proof + signed transparency finality.

This wrapper leaves the compatibility PortableClaimProof format intact while adding
an independently verifiable witness layer. The verifier must receive witness public
keys, groups and quorum policy from outside the packet; self-declared trust is never
accepted.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
import hashlib,hmac,json
from typing import Any,Mapping
from core.portable_claim_proof import PortableClaimProof,build_portable_claim_proof,verify_portable_claim_proof
from core.signed_finality_evidence import build_signed_finality_evidence,verify_signed_finality_evidence
SIGNED_PORTABLE_VERSION=1
@dataclass(frozen=True,slots=True)
class SignedPortableClaimEnvelope:
    version:int;claim_packet:dict[str,Any];signed_finality_evidence:dict[str,Any];envelope_sha256:str
def _canonical(v:Any)->bytes:return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()
def _sha(v:Any)->str:return hashlib.sha256(_canonical(v)).hexdigest()
def build_signed_portable_claim_envelope(engine,claim:str,*,trust_runtime,generated_at:str|None=None,max_age_seconds:int=900)->SignedPortableClaimEnvelope:
    if not trust_runtime.policy.signed_finality_required:raise ValueError("signed portable envelope requires signed-finality policy")
    packet=build_portable_claim_proof(engine,claim,transparency=trust_runtime.transparency,finality=trust_runtime.finality,generated_at=generated_at,max_age_seconds=max_age_seconds)
    if packet.finality_anchor is None:raise ValueError("current transparency head is not finalized")
    evidence=build_signed_finality_evidence(trust_runtime)
    if evidence is None:raise ValueError("signed finality evidence unavailable")
    if evidence["finality"]["sha256"]!=packet.finality_anchor["sha256"]:raise ValueError("claim and witness finality anchors diverged")
    payload={"version":SIGNED_PORTABLE_VERSION,"claim_packet":asdict(packet),"signed_finality_evidence":evidence}
    return SignedPortableClaimEnvelope(**payload,envelope_sha256=_sha(payload))
def verify_signed_portable_claim_envelope(envelope:SignedPortableClaimEnvelope|Mapping[str,Any],*,trusted_witnesses:Mapping[str,Mapping[str,str]],required_groups:int,max_age_seconds:int,now=None,expected_transparency_root:str|None=None,expected_finality_sha256:str|None=None)->bool:
    try:
        raw=asdict(envelope) if isinstance(envelope,SignedPortableClaimEnvelope) else dict(envelope)
        if int(raw.get("version",0))!=SIGNED_PORTABLE_VERSION:return False
        packet_raw=raw.get("claim_packet");evidence=raw.get("signed_finality_evidence")
        if not isinstance(packet_raw,dict) or not isinstance(evidence,dict):return False
        packet=PortableClaimProof(**packet_raw);finality_sha=str(evidence.get("finality",{}).get("sha256",""))
        if expected_finality_sha256 is not None and not hmac.compare_digest(finality_sha,str(expected_finality_sha256)):return False
        if not verify_portable_claim_proof(packet,now=now,expected_transparency_root=expected_transparency_root,expected_finality_sha256=finality_sha,require_transparency=True,require_finality=True):return False
        if not verify_signed_finality_evidence(evidence,trusted_witnesses=trusted_witnesses,required_groups=required_groups,max_age_seconds=max_age_seconds,expected_finality_sha256=finality_sha):return False
        if packet.finality_anchor is None or packet.finality_anchor.get("sha256")!=finality_sha:return False
        payload={"version":SIGNED_PORTABLE_VERSION,"claim_packet":packet_raw,"signed_finality_evidence":evidence}
        return hmac.compare_digest(_sha(payload),str(raw.get("envelope_sha256","")))
    except (KeyError,TypeError,ValueError):return False
