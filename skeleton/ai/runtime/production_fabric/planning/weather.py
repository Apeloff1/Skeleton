"""Reproducible weather transitions using explicit integer PRNG state."""
from ..contracts.errors import ContractError
STATES = ('clear', 'cloudy', 'wind', 'rain', 'storm', 'snow')

def evolve(state: str, seed: int, *, temperature: int=15) -> tuple[str, int]:
    if state not in STATES or type(seed) is not int or (not 0 <= seed < 2 ** 64) or (type(temperature) is not int) or (not -80 <= temperature <= 80):
        raise ContractError('invalid environment state')
    next_seed = (6364136223846793005 * seed + 1442695040888963407) % 2 ** 64
    drift = (next_seed >> 33) % 5 - 2
    index = max(0, min(len(STATES) - 1, STATES.index(state) + drift))
    if temperature < 0 and STATES[index] == 'rain':
        index = 5
    return (STATES[index], next_seed)
