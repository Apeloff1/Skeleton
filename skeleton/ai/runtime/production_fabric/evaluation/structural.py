"""Static world reachability and ending coverage with explicit blocked dispositions."""
from ..contracts.spec import World
from ..planning.worlds import structural_reachability
from ..planning.endings import discover

def evaluate(world: World, *, max_states: int=100000) -> dict:
    topo = structural_reachability(world)
    states = discover(world, max_states=max_states)
    failures = []
    if topo['unreachable']:
        failures.append('unreachable-scene')
    if states['missing_endings']:
        failures.append('ending-not-actually-playable')
    return {'status': 'pass' if not failures else 'fail', 'failures': failures, 'structure': topo, 'state_search': states, 'quality_attested': False}
