"""Explicit operator runbook with predictable stages, holds and recovery gates."""
from .order import REQUIRED

def runbook() -> dict:
    return {'schema_version': 1, 'stages': [{'id': wave, 'depends_on': deps, 'operator_action': 'run focused acceptance, inspect exact-head gates before promotion'} for wave, deps in REQUIRED.items()], 'auto_promote': False, 'auto_merge': False, 'hardware_certified': False}
