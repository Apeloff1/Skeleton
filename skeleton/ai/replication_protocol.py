"""Term-fenced deterministic replication protocol contracts."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _digest(prefix,payload): return prefix+sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
    return v
def _uint(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be a non-negative integer")
    return v

@dataclass(frozen=True)
class ReplicatedEntry:
    entry_id:str; index:int; term:int; payload_digest:str
    def __post_init__(self): _id(self.entry_id,"entry_id");_uint(self.index,"index");_uint(self.term,"term");_id(self.payload_digest,"payload_digest")

@dataclass(frozen=True)
class AppendRequest:
    request_id:str; leader_id:str; term:int; prev_log_index:int; prev_log_term:int; entries:tuple[ReplicatedEntry,...]; leader_commit:int
    @classmethod
    def create(cls,leader_id,term,prev_log_index,prev_log_term,entries,leader_commit):
        _id(leader_id,"leader_id");_uint(term,"term");_uint(prev_log_index,"prev_log_index");_uint(prev_log_term,"prev_log_term");_uint(leader_commit,"leader_commit")
        entries=tuple(entries)
        expected=prev_log_index+1
        for e in entries:
            if e.index!=expected: raise ValueError("replication entries must be contiguous")
            if e.term>term: raise ValueError("entry term exceeds leader term")
            expected+=1
        payload={"leader_id":leader_id,"term":term,"prev_log_index":prev_log_index,"prev_log_term":prev_log_term,"entries":[e.__dict__ for e in entries],"leader_commit":leader_commit}
        return cls(_digest("append-request-sha256:",payload),leader_id,term,prev_log_index,prev_log_term,entries,leader_commit)

@dataclass(frozen=True)
class FollowerState:
    current_term:int; entries:tuple[ReplicatedEntry,...]; commit_index:int
    def __post_init__(self):
        _uint(self.current_term,"current_term");_uint(self.commit_index,"commit_index")
        if self.commit_index>len(self.entries): raise ValueError("commit index exceeds follower log")
        for i,e in enumerate(self.entries,1):
            if e.index!=i: raise ValueError("follower log must be contiguous")

@dataclass(frozen=True)
class AppendResponse:
    response_id:str; request_id:str; term:int; accepted:bool; match_index:int; conflict_index:int|None; conflict_term:int|None

def apply_append(state,request,max_batch=256):
    _uint(max_batch,"max_batch")
    if max_batch<1: raise ValueError("max_batch must be positive")
    if request.term<state.current_term: return _response(request,state.current_term,False,state.commit_index,len(state.entries)+1,None)
    if len(request.entries)>max_batch: raise ValueError("append batch exceeds catch-up bound")
    entries=list(state.entries)
    if request.prev_log_index>len(entries): return _response(request,max(state.current_term,request.term),False,state.commit_index,len(entries)+1,None)
    if request.prev_log_index:
        prev=entries[request.prev_log_index-1]
        if prev.term!=request.prev_log_term:
            first=next(e.index for e in entries if e.term==prev.term)
            return _response(request,max(state.current_term,request.term),False,state.commit_index,first,prev.term)
    for incoming in request.entries:
        pos=incoming.index-1
        if pos<len(entries):
            existing=entries[pos]
            if existing.entry_id==incoming.entry_id: continue
            if incoming.index<=state.commit_index: raise PermissionError("leader conflicts with committed follower history")
            entries=entries[:pos]
        entries.append(incoming)
    commit=min(request.leader_commit,len(entries))
    if commit<state.commit_index: commit=state.commit_index
    new=FollowerState(max(state.current_term,request.term),tuple(entries),commit)
    match=request.prev_log_index+len(request.entries)
    return new,_response(request,new.current_term,True,match,None,None)

def _response(req,term,accepted,match,conflict_index,conflict_term):
    payload={"request_id":req.request_id,"term":term,"accepted":accepted,"match_index":match,"conflict_index":conflict_index,"conflict_term":conflict_term}
    return AppendResponse(_digest("append-response-sha256:",payload),req.request_id,term,accepted,match,conflict_index,conflict_term)

@dataclass(frozen=True)
class SnapshotChunk:
    snapshot_id:str; ordinal:int; total:int; data_digest:str
    def __post_init__(self):
        _id(self.snapshot_id,"snapshot_id");_uint(self.ordinal,"ordinal");_uint(self.total,"total");_id(self.data_digest,"data_digest")
        if self.total<1 or self.ordinal>=self.total: raise ValueError("invalid snapshot chunk position")

def verify_snapshot_chunks(snapshot_id,chunks):
    _id(snapshot_id,"snapshot_id");chunks=tuple(chunks)
    if not chunks: raise ValueError("snapshot chunks required")
    total=chunks[0].total
    if len(chunks)!=total: raise ValueError("incomplete snapshot transfer")
    ordered=sorted(chunks,key=lambda c:c.ordinal)
    if [c.ordinal for c in ordered]!=list(range(total)): raise ValueError("snapshot chunk sequence invalid")
    if any(c.snapshot_id!=snapshot_id or c.total!=total for c in ordered): raise PermissionError("snapshot chunk identity mismatch")
    return _digest("snapshot-transfer-sha256:",{"snapshot_id":snapshot_id,"chunks":[c.data_digest for c in ordered]})
