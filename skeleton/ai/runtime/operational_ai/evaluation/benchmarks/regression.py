"""Must-not-regress evaluation baselines with explicit failure budgets."""
from __future__ import annotations
from dataclasses import dataclass
from .runner import BenchmarkResult
from .dataset import EvalError

@dataclass(frozen=True,slots=True)
class RegressionResult:
    accepted:bool
    failure_cases:tuple[str,...]
    missing_cases:tuple[str,...]


def check_regression(baseline:BenchmarkResult,current:BenchmarkResult,
                     *,tolerance:float=0.02)->RegressionResult:
    if baseline.source_sha!=current.source_sha:
        raise EvalError('regression baseline source identity drift')
    a={x.case_id:x for x in baseline.cases};b={x.case_id:x for x in current.cases}
    missing=tuple(sorted(set(a)-set(b)))
    failures=[]
    for key in sorted(set(a)&set(b)):
        old=a[key];now=b[key]
        if now.score is None or (old.score is not None and now.score.token_f1+tolerance<old.score.token_f1):
            failures.append(key)
    return RegressionResult(not failures and not missing,tuple(failures),missing)
