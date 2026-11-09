"""Deterministic write-session semantics and retry fencing."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class CausalToken:
    token_id:str; stream_id:str; revision:int
    @classmethod
    def create(cls,stream_id,revision):
        _id(stream_id,"stream_id");_u(revision,"revision")
        x={"stream_id":stream_id,"revision":revision}
        return cls(_h("causal-sha256:",x),stream_id,revision)

@dataclass(frozen=True)
class WriteIntent:
    intent_id:str; stream_id:str; session_id:str; session_sequence:int; idempotency_key:str; expected_revision:int; payload_digest:str; causal_tokens:tuple[CausalToken,...]
    @classmethod
    def create(cls,stream_id,session_id,session_sequence,idempotency_key,expected_revision,payload_digest,causal_tokens=()):
        for v,n in ((stream_id,"stream_id"),(session_id,"session_id"),(idempotency_key,"idempotency_key"),(payload_digest,"payload_digest")):_id(v,n)
        _u(session_sequence,"session_sequence");_u(expected_revision,"expected_revision")
        tokens=tuple(sorted(causal_tokens,key=lambda x:(x.stream_id,x.revision,x.token_id)))
        streams=[x.stream_id for x in tokens]
        if len(streams)!=len(set(streams)): raise ValueError("duplicate causal stream")
        x={"stream_id":stream_id,"session_id":session_id,"session_sequence":session_sequence,"idempotency_key":idempotency_key,"expected_revision":expected_revision,"payload_digest":payload_digest,"causal_tokens":[t.__dict__ for t in tokens]}
        return cls(_h("write-intent-sha256:",x),stream_id,session_id,session_sequence,idempotency_key,expected_revision,payload_digest,tokens)

@dataclass(frozen=True)
class WriteReceipt:
    receipt_id:str; intent_id:str; stream_id:str; session_id:str; session_sequence:int; revision:int; log_index:int; outcome:str

class WriteLedger:
    """Receipt ledger; durability adapter must persist receipts atomically with the governed effect."""
    def __init__(self,receipts=()):
        self._by_key={};self._session_seq={};self._revision={};self._receipts=[]
        for r in receipts:self._replay(r)

    def _replay(self,r):
        if not isinstance(r,WriteReceipt): raise TypeError("invalid write receipt")
        if r.outcome!="committed": raise ValueError("only committed receipts are replayable")
        key=(r.stream_id,r.session_id,r.session_sequence)
        if key in self._session_seq: raise ValueError("duplicate session sequence")
        self._session_seq[key]=r.intent_id;self._revision[r.stream_id]=max(self._revision.get(r.stream_id,0),r.revision);self._receipts.append(r)

    def apply(self,intent,current_revision,log_index,observed_revisions):
        _u(current_revision,"current_revision");_u(log_index,"log_index")
        existing=self._by_key.get(intent.idempotency_key)
        if existing:
            if existing.intent_id!=intent.intent_id: raise PermissionError("idempotency key reused for different write")
            return existing
        key=(intent.stream_id,intent.session_id,intent.session_sequence)
        prior=self._session_seq.get(key)
        if prior and prior!=intent.intent_id: raise PermissionError("session sequence reused for different write")
        previous=max((s for st,sess,s in self._session_seq if st==intent.stream_id and sess==intent.session_id),default=-1)
        if intent.session_sequence<=previous: raise PermissionError("write session sequence regressed")
        if current_revision!=intent.expected_revision: raise PermissionError("compare-and-swap revision mismatch")
        for token in intent.causal_tokens:
            if observed_revisions.get(token.stream_id,-1)<token.revision: raise PermissionError("causal dependency is not visible")
        revision=current_revision+1
        x={"intent_id":intent.intent_id,"stream_id":intent.stream_id,"session_id":intent.session_id,"session_sequence":intent.session_sequence,"revision":revision,"log_index":log_index,"outcome":"committed"}
        r=WriteReceipt(_h("write-receipt-sha256:",x),intent.intent_id,intent.stream_id,intent.session_id,intent.session_sequence,revision,log_index,"committed")
        self._by_key[intent.idempotency_key]=r;self._session_seq[key]=intent.intent_id;self._revision[intent.stream_id]=revision;self._receipts.append(r);return r

    def receipts(self): return tuple(self._receipts)
