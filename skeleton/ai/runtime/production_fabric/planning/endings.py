"""Compare ending conditions against reachable flags without claiming exhaustive gameplay quality."""
from collections import deque
from ..contracts.spec import World
from ..contracts.state import initial, advance, allowed
from ..contracts.errors import ContractError

def discover(world: World, *, max_states: int=100000) -> dict:
    if not 1 <= max_states <= 1000000:
        raise ContractError('invalid state search bound')
    first = initial(world)
    queue = deque([first])
    seen = {(first.scene, first.flags)}
    found = set()
    while queue:
        state = queue.popleft()
        if state.ended:
            found.add(state.scene)
            continue
        for c in world.scenes[state.scene].choices:
            if not allowed(state, c):
                continue
            nxt = advance(world, state, c.id)
            key = (nxt.scene, nxt.flags)
            if key not in seen:
                seen.add(key)
                queue.append(nxt)
                if len(seen) > max_states:
                    raise ContractError('ending state search exceeds budget')
    return {'reachable_endings': sorted(found), 'missing_endings': sorted(set(world.endings) - found), 'states_explored': len(seen)}
