"""Deterministic bounded playable session runner with explicit choice receipts."""
from ..contracts.spec import World
from ..contracts.state import initial, advance
from ..contracts.errors import ContractError
from .choices import available

def simulate(world: World, choices: list[str], *, max_steps: int=10000) -> dict:
    if not isinstance(choices, list) or len(choices) > max_steps:
        raise ContractError('simulation length exceeded')
    state = initial(world)
    trace = [state.as_data()]
    for choice in choices:
        if choice not in {c['id'] for c in available(world, state)}:
            raise ContractError('unavailable choice during simulation')
        state = advance(world, state, choice)
        trace.append(state.as_data())
    return {'state': state.as_data(), 'trace': trace, 'steps': len(choices), 'terminal': state.ended}
