"""Opaque server-generated sessions, always delegated to authoritative SQLite."""
from __future__ import annotations
from .session_policy import new_session_id
from .contracts import identifier,refuse

def create(worker):
    session=new_session_id()
    result=worker.spine.create(session)
    if result!=session:refuse("durable session allocation disagreed")
    return session

def close(worker,session):
    result=worker.spine.close(identifier(session))
    if type(result) is not bool:refuse("invalid durable session close state")
    return result

def get_history(worker,session,*,maximum=128):
    identifier(session)
    if type(maximum) is not int or not 1<=maximum<=128:
        refuse("invalid transcript ceiling")
    result=worker.spine.history(session)
    if type(result) not in (tuple,list) or len(result)>maximum:
        refuse("invalid authoritative transcript")
    return tuple(result)
