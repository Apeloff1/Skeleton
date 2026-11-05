"""Fail-closed scoring gate for independent human or deterministic evaluators."""
from ..core.canonical import uint
from ..core.errors import Invalid

def accept(scores:dict[str,float],thresholds:dict[str,float]):
    if not isinstance(scores,dict) or not isinstance(thresholds,dict) or set(scores)!=set(thresholds):
        raise Invalid('evaluation set does not match policy')
    import math
    failures=[]
    for key,threshold in sorted(thresholds.items()):
        if not isinstance(key,str) or not key.isidentifier():raise Invalid('invalid metric name')
        value=scores[key]
        if type(value) not in (int,float) or type(threshold) not in (int,float) or not math.isfinite(value) or not math.isfinite(threshold):
            raise Invalid('nonnumeric or nonfinite evaluation')
        if not 0<=value<=1 or not 0<=threshold<=1:raise Invalid('evaluation outside 0..1')
        if value<threshold:failures.append(key)
    return {'release_accepted':not failures,'failed_metrics':failures,'scope':'supplied-scores-only'}
