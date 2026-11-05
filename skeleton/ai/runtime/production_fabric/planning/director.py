"""Bounded pacing director chooses next permissible encounter by fatigue."""
from ..contracts.errors import ContractError

def next_encounter(options: list[dict], fatigue: int, seed: int) -> dict:
    if not 0 <= fatigue <= 100 or type(seed) is not int or (not isinstance(options, list)) or (not 1 <= len(options) <= 128):
        raise ContractError('invalid director context')
    admitted = []
    for item in options:
        if set(item) != {'id', 'intensity', 'cooldown'} or type(item['intensity']) is not int or type(item['cooldown']) is not int:
            raise ContractError('invalid encounter record')
        if item['cooldown'] <= 0:
            admitted.append(item)
    if not admitted:
        raise ContractError('no available director encounters')
    scored = sorted(admitted, key=lambda x: (abs(x['intensity'] - (100 - fatigue)), x['id']))
    return dict(scored[seed % min(3, len(scored))])
