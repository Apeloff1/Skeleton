from dataclasses import dataclass
@dataclass(frozen=True)
class RebuildStep: artifact_id:str; producer_version:str; input_digests:tuple[str,...]; expected_digest:str
@dataclass(frozen=True)
class RebuildPlan: steps:tuple[RebuildStep,...]; max_steps:int=64
@dataclass(frozen=True)
class RebuildEvidence: artifact_id:str; expected_digest:str; actual_digest:str; verified:bool
def execute_rebuild(plan,verified_inputs,producer):
 if isinstance(plan.max_steps,bool) or not isinstance(plan.max_steps,int) or plan.max_steps<=0:raise ValueError("positive rebuild bound required")
 ids=[s.artifact_id for s in plan.steps]
 if len(ids)!=len(set(ids)):raise ValueError("duplicate rebuild artifact")
 if len(plan.steps)>plan.max_steps:raise ValueError("rebuild cascade exceeds bound")
 out=[]
 for s in plan.steps:
  if any(x not in verified_inputs for x in s.input_digests):raise PermissionError("unverified rebuild input")
  if not s.artifact_id or not s.producer_version or not s.expected_digest or not s.input_digests:raise ValueError("complete rebuild step identity required")
  try: actual=producer(s.artifact_id,s.producer_version,s.input_digests)
  except Exception as exc: raise RuntimeError("artifact producer failed") from exc
  out.append(RebuildEvidence(s.artifact_id,s.expected_digest,actual,actual==s.expected_digest))
  if actual!=s.expected_digest:raise ValueError("rebuilt digest mismatch")
 return tuple(out)
