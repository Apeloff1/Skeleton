"""Detect contradictory canonical character/location assertions before publication."""
from ..contracts.errors import ContractError

def audit(statements: list[dict]) -> list[dict]:
    if not isinstance(statements, list) or len(statements) > 10000:
        raise ContractError('canon inventory unbounded')
    seen = {}
    conflicts = []
    for offset, item in enumerate(statements):
        if not isinstance(item, dict) or set(item) != {'entity', 'property', 'value', 'valid_from', 'valid_to', 'source'}:
            raise ContractError('invalid bitemporal statement')
        begin, end = (item['valid_from'], item['valid_to'])
        if type(begin) is not int or (end is not None and (type(end) is not int or end <= begin)):
            raise ContractError('invalid effective time interval')
        key = (item['entity'], item['property'])
        for previous in seen.get(key, []):
            if begin < (previous['valid_to'] if previous['valid_to'] is not None else 2 ** 63) and previous['valid_from'] < (end if end is not None else 2 ** 63) and (item['value'] != previous['value']):
                conflicts.append({'entity': key[0], 'property': key[1], 'first_source': previous['source'], 'second_source': item['source']})
        seen.setdefault(key, []).append(item)
    return conflicts
