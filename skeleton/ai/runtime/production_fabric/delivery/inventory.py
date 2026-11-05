"""Immutable inventory diff for changed/removed source objects."""
from ..contracts.errors import ContractError

def compare(old: dict[str, str], new: dict[str, str]) -> dict:
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ContractError('invalid inventories')
    return {'added': sorted(set(new) - set(old)), 'removed': sorted(set(old) - set(new)), 'changed': sorted((k for k in set(old) & set(new) if old[k] != new[k]))}
