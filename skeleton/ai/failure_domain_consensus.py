"""Failure-domain-aware coordination and split-brain fencing."""
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
class Replica:
    replica_id:str; failure_domain:str; generation:int
    def __post_init__(self): _id(self.replica_id,"replica_id");_id(self.failure_domain,"failure_domain");_uint(self.generation,"generation")

@dataclass(frozen=True)
class ConsensusConfig:
    cluster_id:str; replicas:tuple[Replica,...]; quorum:int; min_failure_domains:int; degraded_quorum:int|None=None
    def __post_init__(self):
        _id(self.cluster_id,"cluster_id");_uint(self.quorum,"quorum");_uint(self.min_failure_domains,"min_failure_domains")
        ids=[r.replica_id for r in self.replicas]
        if len(ids)<3 or len(ids)!=len(set(ids)): raise ValueError("cluster requires at least three unique replicas")
        n=len(ids)
        if self.quorum<=n//2 or self.quorum>n: raise ValueError("quorum must be a strict majority")
        if 2*self.quorum<=n: raise ValueError("quorum intersection is not guaranteed")
        domains={r.failure_domain for r in self.replicas}
        if self.min_failure_domains<2 or self.min_failure_domains>len(domains): raise ValueError("invalid failure-domain requirement")
        if self.degraded_quorum is not None:
            _uint(self.degraded_quorum,"degraded_quorum")
            if self.degraded_quorum<=n//2 or self.degraded_quorum>self.quorum: raise ValueError("degraded quorum must remain a strict majority")
    @property
    def config_id(self):
        return _digest("consensus-config-sha256:",{"cluster_id":self.cluster_id,"quorum":self.quorum,"min_failure_domains":self.min_failure_domains,"degraded_quorum":self.degraded_quorum,"replicas":[{"replica_id":r.replica_id,"failure_domain":r.failure_domain,"generation":r.generation} for r in sorted(self.replicas,key=lambda x:x.replica_id)]})

@dataclass(frozen=True)
class CoordinatorLease:
    lease_id:str; config_id:str; term:int; leader_id:str; issued_at_ns:int; expires_at_ns:int
    def __post_init__(self):
        _id(self.lease_id,"lease_id");_id(self.config_id,"config_id");_uint(self.term,"term");_id(self.leader_id,"leader_id");_uint(self.issued_at_ns,"issued_at_ns");_uint(self.expires_at_ns,"expires_at_ns")
        if self.expires_at_ns<=self.issued_at_ns: raise ValueError("lease expiry must follow issue")

def elect(config,term,candidate_id,voter_ids,now_ns,expires_at_ns):
    _uint(term,"term");_uint(now_ns,"now_ns");_uint(expires_at_ns,"expires_at_ns")
    by_id={r.replica_id:r for r in config.replicas}
    if candidate_id not in by_id: raise PermissionError("foreign coordinator candidate")
    voters=tuple(sorted(set(voter_ids)))
    if len(voters)!=len(tuple(voter_ids)): raise ValueError("duplicate voter")
    if any(v not in by_id for v in voters): raise PermissionError("foreign voter")
    domains={by_id[v].failure_domain for v in voters}
    if len(voters)<config.quorum or len(domains)<config.min_failure_domains: raise PermissionError("insufficient quorum diversity")
    if expires_at_ns<=now_ns: raise ValueError("coordinator lease must be live")
    payload={"config_id":config.config_id,"term":term,"leader_id":candidate_id,"voters":voters,"issued_at_ns":now_ns,"expires_at_ns":expires_at_ns}
    return CoordinatorLease(_digest("coordinator-lease-sha256:",payload),config.config_id,term,candidate_id,now_ns,expires_at_ns)

def validate_leader(config,lease,term,now_ns):
    _uint(term,"term");_uint(now_ns,"now_ns")
    if lease.config_id!=config.config_id: raise PermissionError("coordinator lease crossed configuration")
    if term!=lease.term: raise PermissionError("coordinator term mismatch")
    if now_ns<lease.issued_at_ns or now_ns>=lease.expires_at_ns: raise PermissionError("coordinator lease is not live")
    if lease.leader_id not in {r.replica_id for r in config.replicas}: raise PermissionError("foreign coordinator")
    return True

def handoff(config,current,new_term,candidate_id,voter_ids,now_ns,expires_at_ns):
    if new_term<=current.term: raise PermissionError("handoff must advance coordinator term")
    if now_ns<current.expires_at_ns: raise PermissionError("live coordinator prevents competing handoff")
    return elect(config,new_term,candidate_id,voter_ids,now_ns,expires_at_ns)

def degraded_admissible(config,available_ids):
    ids=set(available_ids);by_id={r.replica_id:r for r in config.replicas}
    if any(x not in by_id for x in ids): return False
    required=config.degraded_quorum
    if required is None or len(ids)<required: return False
    return len({by_id[x].failure_domain for x in ids})>=config.min_failure_domains

def reconcile_terms(leases):
    leases=tuple(leases)
    if not leases: raise ValueError("leases are required")
    config_ids={x.config_id for x in leases}
    if len(config_ids)!=1: raise PermissionError("cannot reconcile different configurations")
    by_term={}
    for x in leases:
        if x.term in by_term and by_term[x.term].leader_id!=x.leader_id: raise PermissionError("split-brain leaders in same term")
        by_term[x.term]=x
    return by_term[max(by_term)]
