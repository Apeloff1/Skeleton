"""Data quality gates retaining raw observations and blocking critical failures."""
from dataclasses import dataclass
class DataQualityError(ValueError): pass
@dataclass(frozen=True, slots=True)
class DataQualityRule: rule_id:str; metric:str; comparator:str; threshold:float; critical:bool=True
@dataclass(frozen=True, slots=True)
class QualityObservation: metric:str; value:float; sample_count:int
@dataclass(frozen=True, slots=True)
class QualityFailure: rule_id:str; metric:str; critical:bool; reason:str
@dataclass(frozen=True, slots=True)
class QualityReport: dataset_id:str; version:int; observations:tuple; failures:tuple; promotion_allowed:bool
class DataQualityEngine:
    def __init__(self,rules):
        self.rules=tuple(rules)
        if not self.rules or len({r.rule_id for r in self.rules})!=len(self.rules) or any(r.comparator not in {"gte","lte","eq"} for r in self.rules): raise DataQualityError("invalid rules")
    def evaluate(self,*,dataset_id,version,observations):
        if not dataset_id or isinstance(version,bool) or version<1: raise DataQualityError("invalid dataset")
        obs=tuple(observations); by={o.metric:o for o in obs}
        if len(by)!=len(obs) or any(o.sample_count<1 for o in obs): raise DataQualityError("invalid observations")
        failures=[]
        for r in self.rules:
            o=by.get(r.metric)
            if o is None: failures.append(QualityFailure(r.rule_id,r.metric,r.critical,"missing_observation")); continue
            ok={"gte":o.value>=r.threshold,"lte":o.value<=r.threshold,"eq":o.value==r.threshold}[r.comparator]
            if not ok: failures.append(QualityFailure(r.rule_id,r.metric,r.critical,"threshold_violation"))
        return QualityReport(dataset_id,version,obs,tuple(failures),not any(f.critical for f in failures))
