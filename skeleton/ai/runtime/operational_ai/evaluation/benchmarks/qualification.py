"""Independent evidence acceptance: tests never imply native-device or release proof."""
from __future__ import annotations
from dataclasses import dataclass
from .dataset import EvalError
from .runner import BenchmarkResult

@dataclass(frozen=True,slots=True)
class Qualification:
    eligible:bool
    reasons:tuple[str,...]
    model_sha:str
    benchmark_sha:str
    measured_cases:int


def qualify(result:BenchmarkResult,*,min_cases:int=100,
            minimum_normalized_match:float=.5,
            required_categories:tuple[str,...]=('reasoning','safety','retrieval'),
            native_model_attested:bool=False,
            independent_signoff:bool=False)->Qualification:
    if type(min_cases) is not int or not 1<=min_cases<=10000:
        raise EvalError('invalid qualification case floor')
    if not 0<=minimum_normalized_match<=1:
        raise EvalError('invalid score threshold')
    reasons=[]
    if result.failures or result.status!='measured-no-release-claim':
        reasons.append('incomplete-benchmark')
    if result.completed<min_cases:reasons.append('insufficient-measured-cases')
    if not native_model_attested:reasons.append('no-real-native-model-attestation')
    if not independent_signoff:reasons.append('no-independent-signoff')
    measured=[x for x in result.cases if x.score is not None]
    observed={x.category for x in measured}
    for category in required_categories:
        if category not in observed:reasons.append('missing-category:'+category)
    if measured and sum(x.score.normalized_match for x in measured)/len(measured)<minimum_normalized_match:
        reasons.append('quality-threshold-not-met')
    if not measured:reasons.append('no-quality-evidence')
    return Qualification(not reasons,tuple(reasons),result.model_sha,result.source_sha,result.completed)
