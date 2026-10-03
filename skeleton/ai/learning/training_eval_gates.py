"""Versioned training evaluation gates with independent verifier and explicit regression disposition."""
from dataclasses import dataclass
class TrainingEvalError(ValueError): pass
@dataclass(frozen=True, slots=True)
class EvaluationSuite: suite_id:str; version:int; thresholds:tuple[tuple[str,float],...]
@dataclass(frozen=True, slots=True)
class CheckpointEvaluation: checkpoint_digest:str; suite_id:str; suite_version:int; metrics:tuple[tuple[str,float],...]; verifier_id:str; uncertainty:float
@dataclass(frozen=True, slots=True)
class ModelPromotion: checkpoint_digest:str; allowed:bool; regressions:tuple[str,...]; disposition:str
class TrainingEvalGate:
    def __init__(self,suite:EvaluationSuite):
        if not suite.suite_id or suite.version<1 or not suite.thresholds: raise TrainingEvalError("invalid evaluation suite")
        self.suite=suite
    def evaluate(self,*,checkpoint_digest:str,producer_id:str,verifier_id:str,metrics:dict[str,float],uncertainty:float,disposition:str="")->ModelPromotion:
        if len(checkpoint_digest)!=64 or not verifier_id or verifier_id==producer_id: raise TrainingEvalError("independent verifier required")
        if not 0<=uncertainty<=1: raise TrainingEvalError("uncertainty out of range")
        regressions=tuple(name for name,threshold in self.suite.thresholds if name not in metrics or metrics[name]<threshold)
        if regressions and not disposition: raise TrainingEvalError("regressions require explicit disposition")
        allowed=not regressions and uncertainty<=0.2
        return ModelPromotion(checkpoint_digest,allowed,regressions,disposition or "no_regressions")
