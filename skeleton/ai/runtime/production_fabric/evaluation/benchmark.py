"""Typed reproducible benchmark cases and conservative quantitative scoring."""
from dataclasses import dataclass
from ..contracts.errors import ContractError

@dataclass(frozen=True)
class Case:
    id: str
    expected: dict
    observed: dict
    category: str

def score(cases: list[Case]) -> dict:
    if not isinstance(cases, list) or not cases or len(cases) > 100000 or (len({c.id for c in cases}) != len(cases)):
        raise ContractError('invalid benchmark corpus')
    passed = sum((case.expected == case.observed for case in cases))
    buckets = {}
    for case in cases:
        row = buckets.setdefault(case.category, {'passed': 0, 'total': 0})
        row['total'] += 1
        row['passed'] += int(case.expected == case.observed)
    return {'passed': passed, 'total': len(cases), 'percent': round(100 * passed / len(cases), 4), 'by_category': dict(sorted(buckets.items())), 'release_certified': False}
