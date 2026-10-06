"""Evidence-bound read consistency for replicated AI runtime state."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class ReadIndexProof:
    proof_id:str; cluster_id:str; term:int; commit_index:int; leader_id:str; voter_ids:tuple[str,...]; quorum:int
    @classmethod
    def create(cls,cluster_id,term,commit_index,leader_id,voter_ids,quorum):
        _id(cluster_id,"cluster_id");_u(term,"term");_u(commit_index,"commit_index");_id(leader_id,"leader_id");_u(quorum,"quorum")
        voters=tuple(sorted(voter_ids))
        if len(voters)!=len(set(voters)) or quorum<1 or len(voters)<quorum: raise ValueError("read proof lacks unique quorum")
        if any(not isinstance(x,str) or not x.strip() for x in voters): raise ValueError("invalid voter")
        x={"cluster_id":cluster_id,"term":term,"commit_index":commit_index,"leader_id":leader_id,"voter_ids":voters,"quorum":quorum}
        return cls(_h("read-index-sha256:",x),cluster_id,term,commit_index,leader_id,voters,quorum)

@dataclass(frozen=True)
class LeaderLease:
    lease_id:str; cluster_id:str; term:int; leader_id:str; commit_index:int; issued_at_ns:int; expires_at_ns:int; max_clock_skew_ns:int
    def __post_init__(self):
        for n in ("lease_id","cluster_id","leader_id"):_id(getattr(self,n),n)
        for n in ("term","commit_index","issued_at_ns","expires_at_ns","max_clock_skew_ns"):_u(getattr(self,n),n)
        if self.expires_at_ns<=self.issued_at_ns+self.max_clock_skew_ns: raise ValueError("lease window is unsafe")

@dataclass(frozen=True)
class FreshnessToken:
    token_id:str; cluster_id:str; term:int; applied_index:int; observed_at_ns:int
    @classmethod
    def create(cls,cluster_id,term,applied_index,observed_at_ns):
        _id(cluster_id,"cluster_id");_u(term,"term");_u(applied_index,"applied_index");_u(observed_at_ns,"observed_at_ns")
        x={"cluster_id":cluster_id,"term":term,"applied_index":applied_index,"observed_at_ns":observed_at_ns}
        return cls(_h("freshness-sha256:",x),cluster_id,term,applied_index,observed_at_ns)

@dataclass(frozen=True)
class ReadReceipt:
    receipt_id:str; mode:str; cluster_id:str; term:int; read_index:int; session_id:str; evidence_id:str

def linearizable_read(proof,current_term,applied_index,session_id,session_floor=0):
    _u(current_term,"current_term");_u(applied_index,"applied_index");_u(session_floor,"session_floor");_id(session_id,"session_id")
    if proof.term!=current_term: raise PermissionError("stale leader read proof")
    if applied_index<proof.commit_index: raise PermissionError("state has not applied read index")
    if proof.commit_index<session_floor: raise PermissionError("read violates monotonic session")
    return _receipt("linearizable",proof.cluster_id,proof.term,proof.commit_index,session_id,proof.proof_id)

def lease_read(lease,current_term,applied_index,now_ns,session_id,session_floor=0):
    _u(current_term,"current_term");_u(applied_index,"applied_index");_u(now_ns,"now_ns");_u(session_floor,"session_floor");_id(session_id,"session_id")
    if lease.term!=current_term: raise PermissionError("stale leader lease")
    safe_expiry=lease.expires_at_ns-lease.max_clock_skew_ns
    if now_ns<lease.issued_at_ns or now_ns>=safe_expiry: raise PermissionError("leader lease is not safely live")
    if applied_index<lease.commit_index or lease.commit_index<session_floor: raise PermissionError("lease read is not sufficiently fresh")
    return _receipt("lease",lease.cluster_id,lease.term,lease.commit_index,session_id,lease.lease_id)

def follower_read(token,cluster_id,current_term,max_staleness_ns,now_ns,session_id,session_floor=0):
    _id(cluster_id,"cluster_id");_u(current_term,"current_term");_u(max_staleness_ns,"max_staleness_ns");_u(now_ns,"now_ns");_u(session_floor,"session_floor");_id(session_id,"session_id")
    if token.cluster_id!=cluster_id or token.term!=current_term: raise PermissionError("foreign or stale freshness token")
    if now_ns<token.observed_at_ns or now_ns-token.observed_at_ns>max_staleness_ns: raise PermissionError("follower freshness bound exceeded")
    if token.applied_index<session_floor: raise PermissionError("follower read violates monotonic session")
    return _receipt("bounded-stale",cluster_id,current_term,token.applied_index,session_id,token.token_id)

def _receipt(mode,cluster_id,term,index,session_id,evidence_id):
    x={"mode":mode,"cluster_id":cluster_id,"term":term,"read_index":index,"session_id":session_id,"evidence_id":evidence_id}
    return ReadReceipt(_h("read-receipt-sha256:",x),mode,cluster_id,term,index,session_id,evidence_id)
