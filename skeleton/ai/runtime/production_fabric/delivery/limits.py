"""Target package admission is based on actual content bytes, never filler."""
from ..contracts.errors import BudgetError, ContractError

def check(*, archive_bytes: int, source_bytes: int, target: int=1900000000) -> dict:
    if type(archive_bytes) is not int or type(source_bytes) is not int or source_bytes < 0 or (archive_bytes < source_bytes):
        raise ContractError('invalid package byte provenance')
    if not target - 20000000 <= archive_bytes <= target + 20000000 or source_bytes < target - 50000000:
        raise BudgetError('real 1.9GB target not met')
    return {'bytes': archive_bytes, 'source_bytes': source_bytes, 'target': target, 'releasable': False}
