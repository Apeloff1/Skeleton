"""Durable execution attestations for accepted Dragon evidence receipts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,sqlite3

from .dragon_worker_leases import WorkerLease

@dataclass(frozen=True)
class ReceiptAttestation:
 owner:str;run_id:str;layer:str;output_fingerprint:str;worker_id:str
 implementation:str;version:str;lease_generation:int;lease_token_digest:str
 committed_revision:int;chain_fingerprint:str;attestation_fingerprint:str

class DragonReceiptAttestations:
 def __init__(self,db:sqlite3.Connection):
  self.db=db
  db.execute("""CREATE TABLE IF NOT EXISTS dragon_receipt_attestations(
   owner TEXT NOT NULL,run_id TEXT NOT NULL,layer TEXT NOT NULL,output_fingerprint TEXT NOT NULL,
   worker_id TEXT NOT NULL,implementation TEXT NOT NULL,version TEXT NOT NULL,
   lease_generation INTEGER NOT NULL,lease_token_digest TEXT NOT NULL,
   committed_revision INTEGER NOT NULL,chain_fingerprint TEXT NOT NULL,
   attestation_fingerprint TEXT NOT NULL,
   PRIMARY KEY(owner,run_id,layer),UNIQUE(owner,run_id,attestation_fingerprint))""");db.commit()
 def record(self,lease:WorkerLease,output_fingerprint:str,*,committed_revision:int,
            chain_fingerprint:str,authorized:bool)->ReceiptAttestation:
  if not authorized: raise PermissionError("receipt attestation requires authorization")
  for d in (output_fingerprint,chain_fingerprint):
   if len(d)!=64 or any(c not in "0123456789abcdef" for c in d):raise ValueError("invalid attestation fingerprint")
  token_digest=sha256(lease.token.encode()).hexdigest()
  body=[lease.owner,lease.run_id,lease.layer,output_fingerprint,lease.worker_id,
   lease.implementation,lease.version,lease.generation,token_digest,committed_revision,chain_fingerprint]
  fp=sha256(json.dumps(body,separators=(",",":")).encode()).hexdigest()
  value=ReceiptAttestation(*body,fp)
  with self.db:
   row=self.db.execute("""SELECT output_fingerprint,worker_id,implementation,version,
    lease_generation,lease_token_digest,committed_revision,chain_fingerprint,attestation_fingerprint
    FROM dragon_receipt_attestations WHERE owner=? AND run_id=? AND layer=?""",
    (lease.owner,lease.run_id,lease.layer)).fetchone()
   if row:
    if row!=(output_fingerprint,lease.worker_id,lease.implementation,lease.version,
      lease.generation,token_digest,committed_revision,chain_fingerprint,fp):
     raise ValueError("receipt attestation replay conflict")
    return value
   self.db.execute("INSERT INTO dragon_receipt_attestations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
    (lease.owner,lease.run_id,lease.layer,output_fingerprint,lease.worker_id,
     lease.implementation,lease.version,lease.generation,token_digest,
     committed_revision,chain_fingerprint,fp))
  return value
 def get(self,owner:str,run_id:str,layer:str,*,authorized:bool)->ReceiptAttestation:
  if not authorized:raise PermissionError("receipt attestation read requires authorization")
  row=self.db.execute("SELECT * FROM dragon_receipt_attestations WHERE owner=? AND run_id=? AND layer=?",
   (owner,run_id,layer)).fetchone()
  if not row:raise KeyError("receipt attestation not found")
  return ReceiptAttestation(*row)
