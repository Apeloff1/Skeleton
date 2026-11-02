"""Compare reproducible candidate and incumbent metrics before review."""
from ..contracts.errors import ContractError

def compare(incumbent: dict[str, float], candidate: dict[str, float], tolerances: dict[str, float]) -> dict:
    if set(incumbent) != set(candidate) or set(incumbent) != set(tolerances):
        raise ContractError('metric contract drift')
    failures = []
    deltas = {}
    for metric in sorted(incumbent):
        import math
        old, new, tol = (incumbent[metric], candidate[metric], tolerances[metric])
        if not all((isinstance(v, (int, float)) and math.isfinite(v) for v in (old, new, tol))) or tol < 0:
            raise ContractError('nonfinite or invalid metric')
        deltas[metric] = round(new - old, 8)
        if new < old - tol:
            failures.append(metric)
    return {'status': 'hold' if failures else 'eligible-for-review', 'regressions': failures, 'deltas': deltas, 'promoted': False}
