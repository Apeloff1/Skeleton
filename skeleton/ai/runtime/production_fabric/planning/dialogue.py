"""Bounded dialogue graph with explicit state-dependent choices and terminal nodes."""
from ..contracts.errors import ContractError

def validate(nodes: dict[str, dict], start: str) -> dict:
    if not isinstance(nodes, dict) or not 1 <= len(nodes) <= 1000 or start not in nodes:
        raise ContractError('invalid dialogue graph')
    for node, item in nodes.items():
        if set(item) != {'speaker', 'text', 'options'} or not isinstance(item['options'], list) or len(item['options']) > 16:
            raise ContractError('invalid dialogue node')
        for option in item['options']:
            if set(option) != {'id', 'to', 'requires', 'grants'} or option['to'] not in nodes or (not isinstance(option['requires'], list)) or (not isinstance(option['grants'], list)):
                raise ContractError('dangling dialogue option')
    terminal = [key for key, value in nodes.items() if not value['options']]
    if not terminal:
        raise ContractError('dialogue must admit terminal states')
    return {'start': start, 'terminals': sorted(terminal), 'nodes': len(nodes)}

def next_options(nodes: dict, state: str, flags: set[str]) -> list[dict]:
    if state not in nodes:
        raise ContractError('unknown dialogue state')
    return [item for item in nodes[state]['options'] if set(item['requires']).issubset(flags)]
