"""Deterministic inbound-message deduplication and causal processing."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class InboundMessage:
    message_id:str; producer_id:str; producer_epoch:int; sequence:int; payload_digest:str; causal_ids:tuple[str,...]
    @classmethod
    def create(cls,producer_id,producer_epoch,sequence,payload_digest,causal_ids=()):
        _id(producer_id,"producer_id");_u(producer_epoch,"producer_epoch");_u(sequence,"sequence");_id(payload_digest,"payload_digest")
        causal=tuple(sorted(causal_ids))
        if len(causal)!=len(set(causal)) or any(not isinstance(x,str) or not x.strip() for x in causal): raise ValueError("invalid causal identities")
        x={"producer_id":producer_id,"producer_epoch":producer_epoch,"sequence":sequence,"payload_digest":payload_digest,"causal_ids":causal}
        return cls(_h("inbound-sha256:",x),producer_id,producer_epoch,sequence,payload_digest,causal)

@dataclass(frozen=True)
class ProcessingReceipt:
    receipt_id:str; message_id:str; producer_id:str; producer_epoch:int; sequence:int; write_receipt_id:str; effect_record_ids:tuple[str,...]; outcome:str

@dataclass(frozen=True)
class QuarantineReceipt:
    receipt_id:str; message_id:str; reason:str; evidence_id:str

class InboxLedger:
    def __init__(self,replay_window=1024):
        _u(replay_window,"replay_window")
        if replay_window<1: raise ValueError("replay_window must be positive")
        self.replay_window=replay_window;self._processed={};self._highest={};self._epochs={};self._quarantine={}

    def admit(self,message):
        if not isinstance(message,InboundMessage): raise TypeError("invalid inbound message")
        existing=self._processed.get(message.message_id)
        if existing:return existing
        epoch=self._epochs.get(message.producer_id)
        if epoch is not None and message.producer_epoch<epoch: raise PermissionError("stale producer epoch")
        if epoch is not None and message.producer_epoch>epoch:
            self._highest[message.producer_id]=-1
        self._epochs[message.producer_id]=message.producer_epoch
        highest=self._highest.get(message.producer_id,-1)
        if message.sequence<=highest-self.replay_window: raise PermissionError("message outside replay window")
        if message.sequence>highest+1: raise PermissionError("producer sequence gap")
        return None

    def commit(self,message,write_receipt_id,effect_record_ids=()):
        _id(write_receipt_id,"write_receipt_id")
        effects=tuple(sorted(effect_record_ids))
        if len(effects)!=len(set(effects)) or any(not isinstance(x,str) or not x.strip() for x in effects): raise ValueError("invalid effect identities")
        existing=self._processed.get(message.message_id)
        if existing:
            if existing.write_receipt_id!=write_receipt_id or existing.effect_record_ids!=effects: raise PermissionError("duplicate message changed processing effect")
            return existing
        self.admit(message)
        highest=self._highest.get(message.producer_id,-1)
        if message.sequence<=highest: raise PermissionError("sequence already consumed by different message")
        x={"message_id":message.message_id,"producer_id":message.producer_id,"producer_epoch":message.producer_epoch,"sequence":message.sequence,"write_receipt_id":write_receipt_id,"effect_record_ids":effects,"outcome":"committed"}
        r=ProcessingReceipt(_h("processing-sha256:",x),message.message_id,message.producer_id,message.producer_epoch,message.sequence,write_receipt_id,effects,"committed")
        self._processed[message.message_id]=r;self._highest[message.producer_id]=message.sequence;return r

    def quarantine(self,message,reason,evidence_id):
        _id(reason,"reason");_id(evidence_id,"evidence_id")
        old=self._quarantine.get(message.message_id)
        x={"message_id":message.message_id,"reason":reason,"evidence_id":evidence_id}
        r=QuarantineReceipt(_h("inbox-quarantine-sha256:",x),message.message_id,reason,evidence_id)
        if old and old!=r: raise PermissionError("quarantine evidence changed")
        self._quarantine[message.message_id]=r;return r
