"""Read-only restart diagnosis and stale-operation quarantine suggestions."""
from __future__ import annotations
from ...persistence.durable.database import DurableDatabase,DurableError
from ...persistence.durable.operations import OperationRepository


def diagnose_incomplete(db:DurableDatabase,*,tenant:str,owner:str,
                        maximum:int=100)->tuple[dict,...]:
    active=OperationRepository(db).list_active(tenant,owner,limit=maximum)
    return tuple({'operation':op.operation,'state':op.state,
                  'version':op.version,'disposition':'manual-reconcile-no-automatic-replay',
                  'request_sha':op.request_sha} for op in active)
