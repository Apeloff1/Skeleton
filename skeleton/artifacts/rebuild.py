from dataclasses import dataclass
@dataclass(frozen=True)
class RebuildStep: artifact_id:str; producer_version:str; input_digests:tuple[str,...]; expected_digest:str
@dataclass(frozen=True)
class RebuildPlan: steps:tuple[RebuildStep,...]; max_steps:int=64
@dataclass(frozen=True)
class RebuildEvidence: artifact_id:str; expected_digest:str; actual_digest:str; verified:bool
def execute_rebuild(plan,verified_inputs,producer):
 if len(plan.steps)>plan.max_steps:raise ValueError("rebuild cascade exceeds bound")
 out=[]
 for s in plan.steps:
  if any(x not in verified_inputs for x in s.input_digests):raise PermissionError("unverified rebuild input")
  actual=producer(s.artifact_id,s.producer_version,s.input_digests)
  out.append(RebuildEvidence(s.artifact_id,s.expected_digest,actual,actual==s.expected_digest))
  if actual!=s.expected_digest:raise ValueError("rebuilt digest mismatch")
 return tuple(out)
