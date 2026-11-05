"""Reproducible directional champion/challenger metrics; no silent promotion."""
import math
from ..contracts.errors import ContractError

def compare(incumbent: dict[str, float], candidate: dict[str, float], tolerances: dict[str, float], *, directions: dict[str, str]) -> dict:
    if set(incumbent) != set(candidate) or set(incumbent) != set(tolerances) or set(incumbent) != set(directions):
        raise ContractError('metric contract drift or missing direction')
    failures = []
    deltas = {}
    for metric in sorted(incumbent):
        old, new, tol = (incumbent[metric], candidate[metric], tolerances[metric])
        if directions[metric] not in {'higher', 'lower'} or not all((type(v) in (int, float) and math.isfinite(v) for v in (old, new, tol))) or tol < 0:
            raise ContractError('nonfinite, undirected or invalid metric')
        deltas[metric] = round(new - old, 8)
        if directions[metric] == 'higher' and new < old - tol or (directions[metric] == 'lower' and new > old + tol):
            failures.append(metric)
    return {'status': 'hold' if failures else 'eligible-for-review', 'regressions': failures, 'deltas': deltas, 'promoted': False}
