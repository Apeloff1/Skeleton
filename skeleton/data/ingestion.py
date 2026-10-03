"""Governed ingestion: immutable source identity, quarantine, idempotent replay."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from typing import Any, Callable, Mapping
class IngestionError(ValueError): pass
@dataclass(frozen=True, slots=True)
class IngestionJob:
    job_id:str; source_id:str; source_digest:str; acquired_at_ns:int; rights:str; classification:str; parser_version:str; trusted_source:bool
    def __post_init__(self):
        if not self.job_id or not self.source_id or len(self.source_digest)!=64: raise IngestionError("invalid source identity")
        if isinstance(self.acquired_at_ns,bool) or not isinstance(self.acquired_at_ns,int) or self.acquired_at_ns<0: raise IngestionError("invalid acquisition time")
@dataclass(frozen=True, slots=True)
class IngestedRecord:
    job_id:str; source_id:str; source_digest:str; parser_version:str; rights:str; classification:str; record_digest:str; value:Mapping[str,Any]
@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    job_id:str; source_id:str; source_digest:str; reason:str
class IngestionEngine:
    def __init__(self): self._outcomes={}
    def ingest(self,job:IngestionJob,payload:bytes,*,parser:Callable[[bytes],Mapping[str,Any]]):
        if not isinstance(payload,bytes): raise TypeError("payload must be bytes")
        old=self._outcomes.get(job.job_id)
        if old is not None:
            if old.source_id!=job.source_id or old.source_digest!=job.source_digest: raise IngestionError("job identity cannot be rebound")
            return old
        if hashlib.sha256(payload).hexdigest()!=job.source_digest: return self._q(job,"source_digest_mismatch")
        if not job.trusted_source: return self._q(job,"untrusted_source")
        try: value=parser(payload)
        except Exception: return self._q(job,"parser_rejected")
        if not isinstance(value,Mapping): return self._q(job,"parser_output_not_mapping")
        try: raw=json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        except (TypeError,ValueError): return self._q(job,"parser_output_not_canonical")
        out=IngestedRecord(job.job_id,job.source_id,job.source_digest,job.parser_version,job.rights,job.classification,hashlib.sha256(raw).hexdigest(),dict(value)); self._outcomes[job.job_id]=out; return out
    def _q(self,job,reason):
        out=QuarantineRecord(job.job_id,job.source_id,job.source_digest,reason); self._outcomes[job.job_id]=out; return out
