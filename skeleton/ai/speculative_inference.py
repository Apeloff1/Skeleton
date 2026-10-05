from dataclasses import dataclass
import math
@dataclass(frozen=True)
class DraftToken:
 token:int; probability:float
 def __post_init__(self):
  if isinstance(self.token,bool) or not isinstance(self.token,int) or isinstance(self.probability,bool) or not isinstance(self.probability,(int,float)) or not math.isfinite(self.probability) or not 0<=self.probability<=1:raise ValueError("invalid draft token")
@dataclass(frozen=True)
class SpeculativePlan:
 draft_model:str; target_model:str; max_tokens:int; fallback:bool=True
 def __post_init__(self):
  if not self.draft_model or not self.target_model or self.draft_model==self.target_model or isinstance(self.max_tokens,bool) or not isinstance(self.max_tokens,int) or self.max_tokens<=0:raise ValueError("invalid speculative plan")
@dataclass(frozen=True)
class VerificationStep: token:DraftToken; target_token:int; accepted:bool
def verify(plan,drafts,target_tokens):
 ds=tuple(drafts)[:plan.max_tokens];ts=tuple(target_tokens)
 if len(ts)<len(ds):raise ValueError("target verification incomplete")
 out=[]
 for d,t in zip(ds,ts):
  ok=d.token==t;out.append(VerificationStep(d,t,ok))
  if not ok:break
 return tuple(out)
def accepted_tokens(steps):return tuple(x.token.token for x in steps if x.accepted)
def fallback_required(plan,steps,drafts):
 attempted=min(len(tuple(drafts)),plan.max_tokens)
 return plan.fallback and (len(steps)<attempted or any(not x.accepted for x in steps))
