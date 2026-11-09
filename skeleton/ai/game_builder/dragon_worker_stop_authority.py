"""Lease-bound external proof that a crashed Dragon worker is stopped.

Only an independent sealed OS/process/resource supervisor may issue this
signature. The verifier cannot itself inspect processes. Boolean caller
assertions alone never clear a quarantine.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
from secrets import token_hex

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import _auth
from .reviewed_knowledge import _id, _integer

MAX_EPOCH=4_102_444_800


@dataclass(frozen=True, slots=True)
class SignedWorkerStop:
    owner: str
    source_id: str
    host: str
    ticket_digest: str
    quarantine_digest: str
    process_stop_digest: str
    resource_reconciliation_digest: str
    supervisor: str
    issuer: str
    issued_at: int
    expires_at: int
    nonce: str
    signature: str

    def body(self)->dict:
        return {
            "schema":"skeleton.dragon.external_worker_stop.v1",
            "owner":self.owner,"source_id":self.source_id,"host":self.host,
            "ticket_digest":self.ticket_digest,
            "quarantine_digest":self.quarantine_digest,
            "process_stop_digest":self.process_stop_digest,
            "resource_reconciliation_digest":self.resource_reconciliation_digest,
            "supervisor":self.supervisor,"issuer":self.issuer,
            "issued_at":self.issued_at,"expires_at":self.expires_at,
            "nonce":self.nonce,
            "worker_confirmed_stopped":True,
            "resource_grant_reconciled":True,
            "network_authorized":False,"training_authorized":False,
        }

    @property
    def digest(self)->str:
        return canonical_digest({**self.body(),"signature":self.signature})


class DragonWorkerStopAuthority:
    """Key-isolated supervisor issuer/verifier; NEVER give keys to hatchlings."""

    def __init__(self,*,key:bytes,issuer:str):
        if type(key) is not bytes or len(key)<32:
            raise ValueError("separate 256-bit worker-stop signing key required")
        _id(issuer,"stop issuer")
        self.key=key
        self.issuer=issuer

    def _mac(self,body:dict)->str:
        return hmac.new(
            self.key,canonical_json(body).encode("utf-8"),sha256
        ).hexdigest()

    def issue(self,*,owner:str,source_id:str,host:str,
              ticket_digest:str,quarantine_digest:str,
              process_stop_digest:str,resource_reconciliation_digest:str,
              supervisor:str,now:int,expires_at:int,
              trusted_external_supervisor:bool,process_stopped:bool,
              global_resources_reconciled:bool)->SignedWorkerStop:
        # Signals must come from a real independent OS/scheduler observer,
        # never a browser, crawler result, or model-generated message.
        if (trusted_external_supervisor is not True or process_stopped is not True
            or global_resources_reconciled is not True):
            raise PermissionError("external process and resource proof required")
        _id(owner,"owner");_id(source_id,"source");_id(supervisor,"supervisor")
        if type(host) is not str or not host or len(host)>255:
            raise ValueError("canonical host required")
        for label,val in (
            ("ticket",ticket_digest),("quarantine",quarantine_digest),
            ("process",process_stop_digest),
            ("resource reconciliation",resource_reconciliation_digest)
        ):
            if type(val) is not str or len(val)!=64 or any(
                c not in "0123456789abcdef" for c in val
            ):
                raise ValueError(f"canonical {label} digest required")
        _integer(now,"external stop time",0,MAX_EPOCH)
        _integer(expires_at,"external stop expiry",now+1,MAX_EPOCH)
        if expires_at>now+600:
            raise ValueError("external stop receipt expires within ten minutes")
        base={
            "schema":"skeleton.dragon.external_worker_stop.v1",
            "owner":owner,"source_id":source_id,"host":host,
            "ticket_digest":ticket_digest,
            "quarantine_digest":quarantine_digest,
            "process_stop_digest":process_stop_digest,
            "resource_reconciliation_digest":resource_reconciliation_digest,
            "supervisor":supervisor,"issuer":self.issuer,
            "issued_at":now,"expires_at":expires_at,
            "nonce":token_hex(16),
            "worker_confirmed_stopped":True,
            "resource_grant_reconciled":True,
            "network_authorized":False,"training_authorized":False,
        }
        return SignedWorkerStop(
            owner,source_id,host,ticket_digest,quarantine_digest,
            process_stop_digest,resource_reconciliation_digest,
            supervisor,self.issuer,now,expires_at,
            base["nonce"],self._mac(base)
        )

    def verify(self,receipt:SignedWorkerStop,*,owner:str,source_id:str,
               host:str,ticket_digest:str,quarantine_digest:str,
               now:int,authorized:bool)->str:
        _auth(owner,authorized)
        _integer(now,"stop receipt verification clock",0,MAX_EPOCH)
        if not isinstance(receipt,SignedWorkerStop):
            raise PermissionError("typed independent stop receipt required")
        if (receipt.owner!=owner or receipt.source_id!=source_id
            or receipt.host!=host or receipt.ticket_digest!=ticket_digest
            or receipt.quarantine_digest!=quarantine_digest
            or receipt.issuer!=self.issuer
            or type(receipt.signature) is not str
            or type(receipt.nonce) is not str
            or len(receipt.nonce)!=32
            or not receipt.issued_at<=now<receipt.expires_at
            or receipt.expires_at>receipt.issued_at+600):
            raise PermissionError("stop proof is stale, misbound, or malformed")
        if not hmac.compare_digest(
            receipt.signature,self._mac(receipt.body())
        ):
            raise PermissionError("stop evidence signature invalid")
        return receipt.digest
