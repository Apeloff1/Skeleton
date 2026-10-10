"""Key lifecycle and revocation policy for provenance verification."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Final

@dataclass(frozen=True,slots=True)
class KeyRecord:
    key_id:str
    algorithm:str
    valid_from:int
    valid_until:int|None=None
    revoked_at:int|None=None
    revocation_reason:str|None=None
    def __post_init__(self)->None:
        if not self.key_id.strip() or not self.algorithm.strip(): raise ValueError("key identity required")
        if self.valid_until is not None and self.valid_until<self.valid_from: raise ValueError("invalid key validity")
        if self.revoked_at is not None and self.revoked_at<self.valid_from: raise ValueError("revocation predates validity")
        if (self.revoked_at is None)!=(self.revocation_reason is None): raise ValueError("revocation timestamp and reason must be paired")
    def valid_for_issuance(self,at:int)->bool:
        return at>=self.valid_from and (self.valid_until is None or at<=self.valid_until) and (self.revoked_at is None or at<self.revoked_at)
    def valid_for_historical_verification(self,signed_at:int)->bool:
        return signed_at>=self.valid_from and (self.valid_until is None or signed_at<=self.valid_until) and (self.revoked_at is None or signed_at<self.revoked_at)

class KeyRegistry:
    def __init__(self)->None: self._records:dict[str,KeyRecord]={}
    def register(self,record:KeyRecord)->None:
        if record.key_id in self._records: raise ValueError("key_id already registered")
        self._records[record.key_id]=record
    def record(self,key_id:str)->KeyRecord:
        try: return self._records[key_id]
        except KeyError as exc: raise ValueError("unknown key_id") from exc
    def eligible(self,key_id:str,algorithm:str,signed_at:int)->bool:
        record=self.record(key_id)
        return record.algorithm==algorithm and record.valid_for_historical_verification(signed_at)

__all__=["KeyRecord","KeyRegistry"]
