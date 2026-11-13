"""Prevent accidental overlarge PR batches without hiding test or release debt."""
from ..contracts.errors import BudgetError, ContractError

def admit(files: list[dict], *, max_file_bytes: int=100000000, max_total_bytes: int=2000000000) -> dict:
    if not isinstance(files, list):
        raise ContractError('files must be listed')
    total = 0
    for file in files:
        size = file.get('bytes')
        if type(size) is not int or size < 0:
            raise ContractError('invalid file size')
        if size >= max_file_bytes:
            raise BudgetError('single file ceiling exceeded')
        total += size
        if total >= max_total_bytes:
            raise BudgetError('PR byte ceiling exceeded')
    return {'files': len(files), 'bytes': total, 'remaining': max_total_bytes - total}
