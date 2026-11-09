"""Deterministic batch scenario runner; preserve every observed failure."""
from ..planning.simulator import simulate
from ..contracts.errors import ContractError

def execute(world, cases: list[dict]) -> dict:
    if not isinstance(cases, list) or len(cases) > 10000:
        raise ContractError('scenario budget exceeded')
    results = []
    for case in cases:
        try:
            result = simulate(world, case['choices'])
            passed = result['state']['scene'] == case['expected_scene']
            results.append({'id': case['id'], 'passed': passed, 'observed': result['state']['scene']})
        except (ContractError, KeyError) as exc:
            results.append({'id': case.get('id', 'unknown'), 'passed': False, 'error': str(exc)})
    return {'passed': sum((x['passed'] for x in results)), 'total': len(results), 'cases': results}
