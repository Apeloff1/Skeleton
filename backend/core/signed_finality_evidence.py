"""Portable verification of Ed25519-backed transparency finality.

The finality ledger alone proves that the server consistently recorded a quorum
digest. This bundle proves what that digest came from. Verification requires an
external trust registry (witness id -> pinned public key + independence group) and
an external quorum threshold; packet-carried trust metadata never grants authority.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import Any, Mapping

from core.signed_transparency_witness import verify_signed_statement
from core.transparency_finality_proof import verify_finality_record


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

def _sha(value: Any) -> str: return hashlib.sha256(_canonical(value)).hexdigest()

def build_signed_finality_evidence(runtime) -> dict[str, Any] | None:
    latest=runtime.finality.latest()
    if latest is None: return None
    when=datetime.fromisoformat(latest.finalized_at.replace("Z","+00:00")).astimezone(UTC)
    quorum=runtime.signed_witnesses.quorum(log_id=latest.log_id,tree_size=latest.tree_size,root_sha256=latest.root_sha256,now=when)
    # Export the complete target set, not only fresh statements, so an offline verifier
    # can reproduce trusted/fresh/stale counts and the exact quorum attestation.
    statements,_=runtime.signed_witnesses._target(log_id=latest.log_id,tree_size=latest.tree_size,root_sha256=latest.root_sha256)
    statements=sorted((dict(x) for x in statements),key=lambda x:str(x.get("witness_id","")))
    evidence={"quorum":asdict(quorum),"statements":statements}
    payload={"version":1,"finality":asdict(latest),"witness_evidence":evidence}
    payload["bundle_sha256"]=_sha(payload); return payload

def verify_signed_finality_evidence(bundle: Mapping[str,Any], *, trusted_witnesses: Mapping[str,Mapping[str,str]],
                                    required_groups:int,max_age_seconds:int,expected_finality_sha256:str|None=None)->bool:
    try:
        if int(bundle.get("version",0))!=1 or required_groups<1 or max_age_seconds<1:return False
        finality=bundle.get("finality"); evidence=bundle.get("witness_evidence")
        if not isinstance(finality,Mapping) or not isinstance(evidence,Mapping) or not verify_finality_record(finality):return False
        if expected_finality_sha256 is not None and not hmac.compare_digest(str(finality.get("sha256","")),str(expected_finality_sha256)):return False
        finality_time=datetime.fromisoformat(str(finality.get("finalized_at","")).replace("Z","+00:00"))
        if finality_time.tzinfo is None:return False
        finality_time=finality_time.astimezone(UTC); statements=evidence.get("statements")
        if not isinstance(statements,list):return False
        trusted_total:dict[str,Mapping[str,Any]]={}; fresh:dict[str,Mapping[str,Any]]={}; stale=0
        for raw in statements:
            if not isinstance(raw,Mapping):return False
            witness_id=str(raw.get("witness_id","")); trust=trusted_witnesses.get(witness_id)
            if not isinstance(trust,Mapping):continue
            public_key=str(trust.get("public_key_b64","")); group=str(trust.get("independence_group",""))
            if not public_key or not group or not verify_signed_statement(raw,public_key_b64=public_key,expected_group=group):continue
            if raw.get("log_id")!=finality.get("log_id") or int(raw.get("tree_size",-1))!=int(finality.get("tree_size",-2)):continue
            if raw.get("root_sha256")!=finality.get("root_sha256"):continue
            prior=trusted_total.get(witness_id)
            if prior is not None and prior.get("statement_sha256")!=raw.get("statement_sha256"):return False
            trusted_total[witness_id]=raw
            observed=datetime.fromisoformat(str(raw.get("observed_at","")).replace("Z","+00:00"))
            if observed.tzinfo is None:continue
            age=(finality_time-observed.astimezone(UTC)).total_seconds()
            if 0<=age<=max_age_seconds:fresh[witness_id]=raw
            else:stale+=1
        groups=tuple(sorted({str(trusted_witnesses[w]["independence_group"]) for w in fresh}))
        if len(groups)<required_groups:return False
        witness_ids=tuple(sorted(fresh))
        quorum_payload={"log_id":str(finality["log_id"]),"tree_size":int(finality["tree_size"]),"root_sha256":str(finality["root_sha256"]),
            "trusted_receipts":len(trusted_total),"fresh_receipts":len(fresh),"stale_receipts":stale,
            "independent_groups":len(groups),"required_groups":int(required_groups),"max_age_seconds":int(max_age_seconds),
            "reached":True,"frozen":False,"witness_ids":witness_ids,"groups":groups}
        if not hmac.compare_digest(_sha(quorum_payload),str(finality.get("witness_quorum_sha256",""))):return False
        if tuple(finality.get("witness_groups",()))!=groups:return False
        declared=evidence.get("quorum")
        if not isinstance(declared,Mapping) or not hmac.compare_digest(str(declared.get("attestation_sha256","")),_sha(quorum_payload)):return False
        raw_payload={"version":1,"finality":dict(finality),"witness_evidence":dict(evidence)}
        return hmac.compare_digest(_sha(raw_payload),str(bundle.get("bundle_sha256","")))
    except (KeyError,TypeError,ValueError):return False
