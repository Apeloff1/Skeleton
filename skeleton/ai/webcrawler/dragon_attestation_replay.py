"""Receipt attestation replay verification."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,sqlite3

from .dragon_analysis_runtime import DragonAnalysisRuntime
from .dragon_analysis_chains import DEFAULT_CHAIN,validate_chain
from .dragon_receipt_attestation import DragonReceiptAttestations
from .dragon_worker_leases import DragonWorkerLeases

@dataclass(frozen=True)
class AttestationReplay:
 layer:str;valid:bool;reason:str

def verify_receipt_attestation(db:sqlite3.Connection,owner:str,run_id:str,layer:str,*,
                               authorized:bool)->AttestationReplay:
 if not authorized:raise PermissionError("attestation replay requires authorization")
 att=DragonReceiptAttestations(db).get(owner,run_id,layer,authorized=True)
 rows=db.execute("""SELECT output_fingerprint FROM dragon_analysis_run_receipts
  WHERE owner=? AND run_id=? AND layer=?""",(owner,run_id,layer)).fetchall()
 if len(rows)!=1:return AttestationReplay(layer,False,"accepted receipt missing or ambiguous")
 if rows[0][0]!=att.output_fingerprint:return AttestationReplay(layer,False,"receipt fingerprint mismatch")
 body=[att.owner,att.run_id,att.layer,att.output_fingerprint,att.worker_id,
  att.implementation,att.version,att.lease_generation,att.lease_token_digest,
  att.committed_revision,att.chain_fingerprint]
 fp=sha256(json.dumps(body,separators=(",",":")).encode()).hexdigest()
 if fp!=att.attestation_fingerprint:return AttestationReplay(layer,False,"attestation fingerprint mismatch")
 try:
  history=DragonWorkerLeases(db).history(owner,run_id,layer,att.lease_generation,authorized=True)
 except KeyError:
  return AttestationReplay(layer,False,"historical worker lease missing")
 worker_id,implementation,version,token_digest,leased_at,expires_at,released_at=history
 if (worker_id,implementation,version,token_digest)!=(att.worker_id,att.implementation,att.version,att.lease_token_digest):
  return AttestationReplay(layer,False,"historical worker lease identity mismatch")
 if not leased_at<=released_at<expires_at:
  return AttestationReplay(layer,False,"historical worker lease validity mismatch")
 audit=db.execute("""SELECT occurred_at FROM dragon_runtime_events
  WHERE owner=? AND run_id=? AND event_type='worker_receipt' AND layer=?
    AND outcome='accepted' AND evidence_fingerprint=?""",
  (owner,run_id,layer,att.output_fingerprint)).fetchall()
 if len(audit)!=1:return AttestationReplay(layer,False,"worker receipt audit event missing or ambiguous")
 if audit[0][0]!=released_at:return AttestationReplay(layer,False,"lease release/audit time mismatch")
 runtime=DragonAnalysisRuntime(db)
 cp=runtime.checkpoint(owner,run_id,authorized=True)
 if cp.revision<att.committed_revision:return AttestationReplay(layer,False,"runtime revision precedes attestation")
 if not 1<=att.committed_revision<=len(DEFAULT_CHAIN):
  return AttestationReplay(layer,False,"invalid attested revision")
 expected_layer=DEFAULT_CHAIN[att.committed_revision-1].layer.value
 if layer!=expected_layer:return AttestationReplay(layer,False,"attested layer/revision mismatch")
 by_layer={r.layer:r for r in runtime._receipts(owner,run_id)}
 historical=[]
 for spec in DEFAULT_CHAIN[:att.committed_revision]:
  receipt=by_layer.get(spec.layer)
  if receipt is None:return AttestationReplay(layer,False,"historical receipt prefix incomplete")
  historical.append(receipt)
 historical_verdict=validate_chain(tuple(historical),authorized=True)
 if historical_verdict.rejected_layers:
  return AttestationReplay(layer,False,"historical receipt prefix invalid")
 if historical_verdict.fingerprint!=att.chain_fingerprint:
  return AttestationReplay(layer,False,"historical chain fingerprint mismatch")
 return AttestationReplay(layer,True,"verified")
