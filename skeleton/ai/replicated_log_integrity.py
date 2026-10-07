"""Content-addressed replicated log integrity and snapshot recovery."""
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
class LogEntry:
    entry_id:str; index:int; term:int; command_digest:str; previous_entry_id:str|None
    @classmethod
    def create(cls,index,term,command_digest,previous_entry_id):
        _uint(index,"index");_uint(term,"term");_id(command_digest,"command_digest")
        if index<1: raise ValueError("log index must be positive")
        if previous_entry_id is not None:_id(previous_entry_id,"previous_entry_id")
        payload={"index":index,"term":term,"command_digest":command_digest,"previous_entry_id":previous_entry_id}
        return cls(_digest("log-entry-sha256:",payload),index,term,command_digest,previous_entry_id)

@dataclass(frozen=True)
class Snapshot:
    snapshot_id:str; last_index:int; last_term:int; last_entry_id:str; state_digest:str
    @classmethod
    def create(cls,last_index,last_term,last_entry_id,state_digest):
        _uint(last_index,"last_index");_uint(last_term,"last_term");_id(last_entry_id,"last_entry_id");_id(state_digest,"state_digest")
        if last_index<1: raise ValueError("snapshot index must be positive")
        payload={"last_index":last_index,"last_term":last_term,"last_entry_id":last_entry_id,"state_digest":state_digest}
        return cls(_digest("log-snapshot-sha256:",payload),last_index,last_term,last_entry_id,state_digest)

class ReplicatedLog:
    def __init__(self,entries=(),commit_index=0,snapshot=None):
        _uint(commit_index,"commit_index");self.snapshot=snapshot;self._entries=[];self.commit_index=snapshot.last_index if snapshot else 0
        for e in entries:self.append_existing(e)
        if commit_index<self.commit_index or commit_index>self.last_index: raise ValueError("invalid commit index")
        self.commit_index=commit_index

    @property
    def last_index(self): return self._entries[-1].index if self._entries else (self.snapshot.last_index if self.snapshot else 0)
    @property
    def last_term(self): return self._entries[-1].term if self._entries else (self.snapshot.last_term if self.snapshot else 0)
    @property
    def head_id(self): return self._entries[-1].entry_id if self._entries else (self.snapshot.last_entry_id if self.snapshot else None)
    def entries(self): return tuple(self._entries)

    def append(self,term,command_digest):
        _uint(term,"term")
        if term<self.last_term: raise PermissionError("log term regressed")
        e=LogEntry.create(self.last_index+1,term,command_digest,self.head_id);self._entries.append(e);return e

    def append_existing(self,e):
        if not isinstance(e,LogEntry): raise TypeError("invalid log entry")
        expected=LogEntry.create(e.index,e.term,e.command_digest,e.previous_entry_id)
        if e!=expected: raise ValueError("log entry identity mismatch")
        if e.index!=self.last_index+1 or e.previous_entry_id!=self.head_id: raise ValueError("log chain discontinuity")
        if e.term<self.last_term: raise ValueError("log term regression")
        self._entries.append(e)

    def commit(self,index):
        _uint(index,"index")
        if index<self.commit_index: raise PermissionError("commit index cannot regress")
        if index>self.last_index: raise PermissionError("cannot commit beyond log")
        self.commit_index=index;return index

    def truncate_uncommitted(self,from_index):
        _uint(from_index,"from_index")
        if from_index<=self.commit_index: raise PermissionError("cannot truncate committed history")
        self._entries=[e for e in self._entries if e.index<from_index]
        return self.head_id

    def install_snapshot(self,snapshot):
        if not isinstance(snapshot,Snapshot): raise TypeError("invalid snapshot")
        if snapshot.last_index<self.commit_index: raise PermissionError("snapshot is behind committed history")
        match=next((e for e in self._entries if e.index==snapshot.last_index),None)
        if match is not None and (match.term!=snapshot.last_term or match.entry_id!=snapshot.last_entry_id): raise PermissionError("snapshot conflicts with local log")
        self.snapshot=snapshot
        self._entries=[e for e in self._entries if e.index>snapshot.last_index]
        self.commit_index=max(self.commit_index,snapshot.last_index)
        return snapshot.snapshot_id

def common_prefix(a,b):
    amap={e.index:e for e in a.entries()};bmap={e.index:e for e in b.entries()};last=0
    for i in sorted(set(amap)&set(bmap)):
        if amap[i].entry_id!=bmap[i].entry_id: break
        if i==last+1:last=i
    return last

def replay_digest(snapshot,entries):
    state=snapshot.state_digest if snapshot else "state:genesis"
    start=snapshot.last_index if snapshot else 0
    for e in entries:
        if e.index<=start: continue
        state=_digest("state-replay-sha256:",{"prior_state":state,"entry_id":e.entry_id,"command_digest":e.command_digest})
    return state
