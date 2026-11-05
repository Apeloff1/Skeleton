"""Session lifecycle and input permission checks independent from model output."""
from __future__ import annotations
from .contracts import identifier,refuse

def session_access(*,caller_tenant,caller_subject,session_tenant,session_subject):
    for entry in (caller_tenant,caller_subject,session_tenant,session_subject):
        identifier(entry)
    if caller_tenant!=session_tenant or caller_subject!=session_subject:
        refuse("cross-principal session access")
    return True

def new_session_id():
    import secrets
    return "s_"+secrets.token_hex(16)

def new_request_id():
    import secrets
    return "r_"+secrets.token_hex(16)
