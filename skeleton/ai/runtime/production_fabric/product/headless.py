"""Headless batch API for determinism and offline integration smoke."""
from ..planning.engine import ProductionEngine
from ..contracts.errors import ContractError

def run(world: dict, steps: list[dict], session: str='default') -> dict:
    if not isinstance(steps, list) or len(steps) > 10000:
        raise ContractError('batch exceeds action limit')
    with ProductionEngine(world) as engine:
        engine = ProductionEngine(world)
        results = []
        for step in steps:
            if set(step) != {'token', 'choice'}:
                raise ContractError('invalid batch step')
            revision = engine.inspect(session)['state']['revision']
            results.append(engine.play(session, step['token'], step['choice'], revision)['receipt'])
        return {'state': engine.inspect(session)['state'], 'receipts': results, 'verification': engine.verify(session)}
