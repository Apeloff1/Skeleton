"""Joint-consensus membership reconfiguration with rollback-safe receipts."""
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
def _majority(n): return n//2+1

@dataclass(frozen=True)
class Member:
    member_id:str; generation:int; failure_domain:str
    def __post_init__(self): _id(self.member_id,"member_id");_uint(self.generation,"generation");_id(self.failure_domain,"failure_domain")

@dataclass(frozen=True)
class Membership:
    cluster_id:str; epoch:int; members:tuple[Member,...]
    def __post_init__(self):
        _id(self.cluster_id,"cluster_id");_uint(self.epoch,"epoch")
        ids=[m.member_id for m in self.members]
        if len(ids)<3 or len(ids)!=len(set(ids)): raise ValueError("membership requires at least three unique members")
    @property
    def membership_id(self):
        return _digest("membership-sha256:",{"cluster_id":self.cluster_id,"epoch":self.epoch,"members":[{"member_id":m.member_id,"generation":m.generation,"failure_domain":m.failure_domain} for m in sorted(self.members,key=lambda x:x.member_id)]})

@dataclass(frozen=True)
class ReconfigurationPlan:
    plan_id:str; old_membership_id:str; new_membership_id:str; from_epoch:int; to_epoch:int; operation_id:str

def plan_reconfiguration(old,new,operation_id):
    _id(operation_id,"operation_id")
    if old.cluster_id!=new.cluster_id: raise PermissionError("membership crossed cluster")
    if new.epoch!=old.epoch+1: raise PermissionError("membership epoch must advance exactly once")
    old_by={m.member_id:m for m in old.members};new_by={m.member_id:m for m in new.members}
    for mid in set(old_by)&set(new_by):
        if new_by[mid].generation<old_by[mid].generation: raise PermissionError("member generation regressed")
    payload={"old_membership_id":old.membership_id,"new_membership_id":new.membership_id,"from_epoch":old.epoch,"to_epoch":new.epoch,"operation_id":operation_id}
    return ReconfigurationPlan(_digest("reconfig-plan-sha256:",payload),**payload)

@dataclass(frozen=True)
class JointAck:
    ack_id:str; plan_id:str; member_id:str; generation:int; evidence_id:str

def acknowledge(plan,old,new,member_id,generation,evidence_id):
    _id(evidence_id,"evidence_id");_uint(generation,"generation")
    if plan.old_membership_id!=old.membership_id or plan.new_membership_id!=new.membership_id: raise PermissionError("plan membership mismatch")
    candidates={m.member_id:m for m in old.members+new.members}
    if member_id not in candidates: raise PermissionError("foreign reconfiguration voter")
    gens={m.generation for m in old.members+new.members if m.member_id==member_id}
    if generation!=max(gens): raise PermissionError("stale member generation")
    payload={"plan_id":plan.plan_id,"member_id":member_id,"generation":generation,"evidence_id":evidence_id}
    return JointAck(_digest("joint-ack-sha256:",payload),plan.plan_id,member_id,generation,evidence_id)

@dataclass(frozen=True)
class ReconfigurationReceipt:
    receipt_id:str; plan_id:str; decision:str; old_voters:tuple[str,...]; new_voters:tuple[str,...]; evidence_ids:tuple[str,...]

def decide(plan,old,new,acks):
    if plan.old_membership_id!=old.membership_id or plan.new_membership_id!=new.membership_id: raise PermissionError("plan membership mismatch")
    acks=tuple(acks);seen=set();valid={}
    old_by={m.member_id:m for m in old.members};new_by={m.member_id:m for m in new.members}
    for a in acks:
        if a.plan_id!=plan.plan_id: raise PermissionError("foreign acknowledgement")
        if a.member_id in seen: raise ValueError("duplicate acknowledgement")
        seen.add(a.member_id)
        gens={m.generation for m in old.members+new.members if m.member_id==a.member_id}
        if not gens or a.generation!=max(gens): raise PermissionError("stale acknowledgement generation")
        valid[a.member_id]=a
    ov=tuple(sorted(set(valid)&set(old_by)));nv=tuple(sorted(set(valid)&set(new_by)))
    decision="commit" if len(ov)>=_majority(len(old_by)) and len(nv)>=_majority(len(new_by)) else "pending"
    evidence=tuple(sorted(a.evidence_id for a in valid.values()))
    payload={"plan_id":plan.plan_id,"decision":decision,"old_voters":ov,"new_voters":nv,"evidence_ids":evidence}
    return ReconfigurationReceipt(_digest("reconfig-receipt-sha256:",payload),plan.plan_id,decision,ov,nv,evidence)

def rollback_plan(committed_plan,old,new,operation_id):
    if new.epoch!=old.epoch+1: raise PermissionError("invalid committed epoch relation")
    restored=Membership(old.cluster_id,new.epoch+1,old.members)
    return plan_reconfiguration(new,restored,operation_id)

def drain_safe(membership,draining_ids,live_ids):
    draining=set(draining_ids);live=set(live_ids);members={m.member_id:m for m in membership.members}
    if not draining<=set(members) or not live<=set(members) or draining&live: return False
    remaining=set(members)-draining
    if not remaining<=live: return False
    if len(remaining)<_majority(len(members)): return False
    return len({members[x].failure_domain for x in remaining})>=2
