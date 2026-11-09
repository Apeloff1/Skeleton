"""Enumerate only currently valid choices from the immutable game-state projection."""
from ..contracts.spec import World
from ..contracts.state import GameState, allowed
from ..contracts.errors import ContractError

def available(world: World, state: GameState) -> list[dict]:
    if state.world != world.id or state.scene not in world.scenes:
        raise ContractError('world/state mismatch')
    if state.ended:
        return []
    return [{'id': c.id, 'text': c.text, 'destination': c.destination, 'grants': list(c.grants), 'costs': list(c.costs)} for c in world.scenes[state.scene].choices if allowed(state, c)]
