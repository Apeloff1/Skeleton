"""Persistent operator pause/resume; no model-generated administrative rights."""
from __future__ import annotations
from .contracts import FlightConflict,FlightBusy
from ..execution_spine.chain import append as audit_append


MODES=frozenset(('running','paused'))


def mode(conn)->str:
    row=conn.execute("SELECT value FROM controls WHERE control='flight_mode'").fetchone()
    status='running' if row is None else row[0]
    if status not in MODES:raise FlightConflict('unknown persisted flight mode')
    return status


def require_running(conn)->None:
    if mode(conn)!='running':raise FlightBusy('flight admissions are paused')


def configure(ledger,target:str,*,approved:bool=False)->dict:
    if approved is not True:raise FlightConflict('independent operator approval required')
    if target not in MODES:raise FlightConflict('invalid flight operation mode')
    with ledger.db.transaction() as conn:
        before=mode(conn)
        if before==target:return {'before':before,'after':target,'changed':False}
        conn.execute("""INSERT INTO controls(control,value) VALUES ('flight_mode',?)
            ON CONFLICT(control) DO UPDATE SET value=excluded.value""",(target,))
        # Shared authoritative chain is transactionally recorded, no inference.
        audit_append(conn,'flight_control','operator_mode',
                     {'schema':'skeleton.ai.flight-mode.v1','before':before,'after':target})
        return {'before':before,'after':target,'changed':True}
