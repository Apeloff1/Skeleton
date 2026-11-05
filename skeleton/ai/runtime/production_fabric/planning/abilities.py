"""Action points and cooldown fences that prevent repeated free powers."""
from ..contracts.errors import ContractError, ConflictError

def activate(ability: str, cost: int, cooldown: int, state: dict, *, tick: int) -> dict:
    if not isinstance(ability, str) or not ability or type(cost) is not int or (cost < 0) or (type(cooldown) is not int) or (cooldown < 0) or (type(tick) is not int) or (tick < 0):
        raise ContractError('invalid ability')
    points = state.get('points', 0)
    next_ready = state.get('ready', {}).get(ability, 0)
    if type(points) is not int or points < cost or tick < next_ready:
        raise ConflictError('ability not ready or insufficient resources')
    output = {'points': points - cost, 'ready': dict(state.get('ready', {}))}
    output['ready'][ability] = tick + cooldown + 1
    return output
