"""Finite resource and custody introspection, safe for authenticated operators."""
from __future__ import annotations
from .contracts import Identity,SpineError
from .chain import verify
from .doctor import inspect
from .recovery import inspect as pending_recovery
from .stream import committed_events

def report(db,identity:Identity,*,maximum_entries:int=50_000)->dict:
    integrity=inspect(db,maximum_entries=maximum_entries)
    with db.snapshot() as conn:
        sessions=conn.execute('SELECT COUNT(*) FROM sessions WHERE principal=?',(identity.key(),)).fetchone()[0]
        turns=conn.execute('SELECT COUNT(*) FROM turns WHERE session IN (SELECT session FROM sessions WHERE principal=?)',(identity.key(),)).fetchone()[0]
        queued=conn.execute("SELECT COUNT(*) FROM requests WHERE state='pending' AND session IN (SELECT session FROM sessions WHERE principal=?)",(identity.key(),)).fetchone()[0]
    return {'status':'owner-custody-inspected','identity_key':identity.key(),
        'sessions':sessions,'turns':turns,'pending':queued,
        'integrity_head':integrity['chain']['head']}
