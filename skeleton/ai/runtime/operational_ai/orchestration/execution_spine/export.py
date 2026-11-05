"""Conversation export is explicit, owner-bound and integrity verified."""
from __future__ import annotations
from hashlib import sha256
from .history import load
from .principal import require_session
from .contracts import Identity,SpineLimits,canonical,SpineError

def export_conversation(conn,identity:Identity,session:str,limits:SpineLimits)->bytes:
    state=require_session(conn,identity,session)
    history=load(conn,identity,session,limits)
    raw=canonical({'schema':'spine.conversation.export.v1','subject_key':identity.key(),
                   'session':session,'revision':state['revision'],'messages':history},
                   ceiling=2_097_152)
    return raw
