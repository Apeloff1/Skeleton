"""Bounded deterministic reputation deltas with optional rival-faction spillover."""
from ..contracts.errors import ContractError

def revise(scores: dict[str, int], faction: str, delta: int, *, rivals: dict[str, list[str]] | None=None) -> dict[str, int]:
    if faction not in scores or type(delta) is not int or (not -100 <= delta <= 100):
        raise ContractError('invalid faction reputation change')
    result = dict(scores)
    result[faction] = max(-100, min(100, scores[faction] + delta))
    for rival in (rivals or {}).get(faction, []):
        if rival not in result:
            raise ContractError('unknown rival faction')
        result[rival] = max(-100, min(100, result[rival] - int(delta / 2)))
    return result
