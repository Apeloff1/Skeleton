"""Canonical eight-wave dependency order; no silent skipping of foundation gates."""
from ..contracts.graph import topological
from ..contracts.errors import ContractError
REQUIRED = {'MBW-00': [], 'MBW-01': ['MBW-00'], 'MBW-02': ['MBW-00', 'MBW-01'], 'MBW-03': ['MBW-00', 'MBW-01'], 'MBW-04': ['MBW-02', 'MBW-03'], 'MBW-05': ['MBW-01', 'MBW-03', 'MBW-04'], 'MBW-06': ['MBW-02', 'MBW-03', 'MBW-04'], 'MBW-07': ['MBW-05', 'MBW-06']}

def validate(waves: list[dict]) -> list[str]:
    graph = {w['id']: w['hard_dependencies'] for w in waves}
    if graph != REQUIRED:
        raise ContractError('canonical build wave graph changed')
    return topological(graph)
