"""Evidence and budget gate for speculative inference."""
from dataclasses import dataclass
from skeleton.ai.speculative_inference import SpeculativePlan
@dataclass(frozen=True)
class SpeculationEvidence:
 pair:str; evaluated:bool; quality_delta:float; cost_ratio:float
def admit_speculation(plan:SpeculativePlan,evidence:SpeculationEvidence,*,max_quality_loss:float,max_cost_ratio:float):
 pair=f"{plan.draft_model}->{plan.target_model}"
 if evidence.pair!=pair or evidence.evaluated is not True:raise PermissionError("model pair lacks evaluation evidence")
 if evidence.quality_delta < -max_quality_loss:raise PermissionError("speculative quality gate")
 if evidence.cost_ratio>max_cost_ratio:raise PermissionError("speculative cost gate")
 return plan
