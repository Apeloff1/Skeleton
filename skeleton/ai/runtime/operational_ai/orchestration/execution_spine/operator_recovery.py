"""Independent administrative recovery, never exposed to assistant tools."""
from __future__ import annotations
from .contracts import Identity,Conflict
from . import recovery
from .chain import verify

def hold_abandoned(db,identity:Identity,*,approved:bool,maximum:int=128)->dict:
    if approved is not True:raise Conflict('recovery must be independently approved')
    with db.transaction() as conn:
        # Only one principal may be held at a time. Never mutate another owner's
        # requests in a mixed-principal database.
        pending=conn.execute("SELECT COUNT(*) FROM requests r JOIN sessions s ON r.session=s.session WHERE r.state='pending' AND s.principal<>?",(identity.key(),)).fetchone()[0]
        if pending:raise Conflict('foreign owner pending operations: global recovery denied')
        verify(conn,limit=100_000)
        return recovery.hold_expired(conn,approved=True,limit=maximum)
