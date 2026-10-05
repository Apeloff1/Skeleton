from dataclasses import dataclass
@dataclass(frozen=True)
class DraftToken: token:int; probability:float
@dataclass(frozen=True)
class SpeculativePlan: draft_model:str; target_model:str; max_tokens:int; fallback:bool=True
@dataclass(frozen=True)
class VerificationStep: token:DraftToken; target_token:int; accepted:bool
def verify(plan,drafts,target_tokens):
 out=[]
 for d,t in zip(drafts,target_tokens):
  ok=d.token==t;out.append(VerificationStep(d,t,ok))
  if not ok:break
 return tuple(out)
def accepted_tokens(steps):return tuple(x.token.token for x in steps if x.accepted)
