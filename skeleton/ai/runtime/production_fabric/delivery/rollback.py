"""Rollback plan is an explicit source/version map, never an automatic overwrite."""
from ..contracts.errors import ContractError

def plan(installed: dict, candidate: dict) -> dict:
    if installed.get('source_ref') == candidate.get('source_ref'):
        raise ContractError('rollback requires distinct source identities')
    return {'from': candidate.get('source_ref'), 'to': installed.get('source_ref'), 'execution': 'manual-approval-required', 'integrity_reverification_required': True, 'performed': False}
