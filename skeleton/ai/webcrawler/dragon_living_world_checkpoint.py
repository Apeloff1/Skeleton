"""Owner-bound signed continuation checkpoints for genuinely long living worlds.

A world may continue after a 192-move request. The current game state is
authenticated using a server-configured 32+ byte secret, includes a fixed
source-world fingerprint and is bound to the authenticated owner; no user
can mint endings or invent items by submitting arbitrary JSON game state.

Checkpoints are renewable for 7 days; this stateless continuity is not
durable server-side archival storage, account sync or permanent persistence.
The user can intentionally branch from a prior checkpoint (save-scumming).
"""
from __future__ import annotations

from dataclasses import asdict,fields,replace
import base64
import hmac
import hashlib
import json
import os
import re
import time

from .dragon_living_world import (
    LivingWorld,LivingState,SCHEMA as GAME_SCHEMA,
    create_world,initial_state,validate_world,validate_state,replay,
    _canonical,_sha,
)

SCHEMA="skeleton.ai.dragon.living_world_checkpoint.v1"
MAX_TOKEN_CHARS=12000
MAX_BODY_BYTES=8000
TTL_SECONDS=7*24*60*60
SECRET_SETTING="SKL_DRAGON_LIVING_WORLD_SIGNING_KEY"
OPAQUE_OWNER=re.compile(r"[0-9a-f]{64}\Z")
HEX=re.compile(r"[0-9a-f]{64}\Z")
STATE_FIELDS={field.name for field in fields(LivingState)}
TUPLE_FIELDS=("discoveries","endings_seen","world_changes")


def _secret()->bytes:
    raw=os.environ.get(SECRET_SETTING,"")
    if type(raw) is not str or len(raw.encode("utf-8"))<32 or (
        len(raw.encode("utf-8"))>256
    ):
        raise RuntimeError("original world checkpoint signing key is not configured")
    return raw.encode("utf-8")


def _owner(owner:str):
    if type(owner) is not str or not OPAQUE_OWNER.fullmatch(owner):
        raise PermissionError("original world checkpoint lacks authenticated owner identity")


def _time(now:int|None)->int:
    when=int(time.time()) if now is None else now
    if type(when) is not int or not 1<=when<=2**31-1:
        raise ValueError("invalid bounded checkpoint issuance time")
    return when


def _b64(raw:bytes)->str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(raw:str)->bytes:
    return base64.b64decode(raw+"="*((-len(raw))%4),altchars=b"-_",
                            validate=True)


def _state(document:dict)->LivingState:
    if not isinstance(document,dict) or set(document)!=STATE_FIELDS:
        raise ValueError("original-world checkpoint contains missing or extra game fields")
    values=document.copy()
    for key in TUPLE_FIELDS:
        if not isinstance(values[key],list):
            raise ValueError("checkpoint inventory lists malformed")
        values[key]=tuple(values[key])
    return LivingState(**values)


def seal_checkpoint(world:LivingWorld,state:LivingState,owner:str,
                    *,now:int|None=None)->str:
    validate_world(world)
    validate_state(world,state)
    _owner(owner)
    stamp=_time(now)
    data={
        "schema":SCHEMA,"world_fingerprint":world.world_fingerprint,
        "world_id":world.world_id,"variation":world.variant,
        "style":world.style,"lifecycle":world.lifecycle,
        "owner":owner,"issued_at":stamp,
        "expires_at":stamp+TTL_SECONDS,
        "player":asdict(state),
        "current_history_digest":state.history_digest,
    }
    payload=_canonical(data)
    if len(payload)>MAX_BODY_BYTES:
        raise ValueError("original-world checkpoint payload exceeds limit")
    mac=hmac.new(_secret(),payload,hashlib.sha256).digest()
    result=_b64(payload)+"."+_b64(mac)
    if len(result)>MAX_TOKEN_CHARS:
        raise ValueError("sealed original-world checkpoint exceeds transport cap")
    return result


def open_checkpoint(world:LivingWorld,token:str,owner:str,
                    *,now:int|None=None)->LivingState:
    validate_world(world)
    _owner(owner)
    stamp=_time(now)
    if (type(token) is not str or not 100<=len(token)<=MAX_TOKEN_CHARS or
            token.count(".")!=1):
        raise ValueError("original-world checkpoint token malformed or oversized")
    b64,signature=token.split(".",1)
    if not re.fullmatch(r"[A-Za-z0-9_-]+",b64) or (
        not re.fullmatch(r"[A-Za-z0-9_-]+",signature)):
        raise ValueError("original-world checkpoint encoding invalid")
    try:
        payload=_unb64(b64)
        authenticated=_unb64(signature)
    except (ValueError,TypeError) as exc:
        raise ValueError("original-world checkpoint base64 invalid") from exc
    if len(payload)>MAX_BODY_BYTES or len(authenticated)!=32:
        raise ValueError("original-world checkpoint cryptographic envelope invalid")
    expected=hmac.new(_secret(),payload,hashlib.sha256).digest()
    if not hmac.compare_digest(expected,authenticated):
        raise PermissionError("original-world checkpoint signature or account differs")
    def reject_duplicate(pairs):
        answer={}
        for k,v in pairs:
            if k in answer:
                raise ValueError("checkpoint has duplicate untrusted keys")
            answer[k]=v
        return answer
    try:
        row=json.loads(payload.decode("utf-8"),object_pairs_hook=reject_duplicate)
    except (UnicodeError,json.JSONDecodeError,ValueError) as exc:
        raise ValueError("original-world checkpoint document invalid") from exc
    if not isinstance(row,dict) or set(row)!={
        "schema","world_fingerprint","world_id","variation","style",
        "lifecycle","owner","issued_at","expires_at","player",
        "current_history_digest",
    }:
        raise ValueError("checkpoint lacks canonical original-game fields")
    if (row["schema"]!=SCHEMA or row["world_fingerprint"]!=world.world_fingerprint
        or row["world_id"]!=world.world_id or row["variation"]!=world.variant
        or row["style"]!=world.style or row["lifecycle"]!=world.lifecycle):
        raise PermissionError("checkpoint cannot cross world or style boundaries")
    if not hmac.compare_digest(row["owner"],owner):
        raise PermissionError("checkpoint cannot cross owner/tenant boundaries")
    if (type(row["issued_at"]) is not int or
            type(row["expires_at"]) is not int or
            row["expires_at"]-row["issued_at"]!=TTL_SECONDS or
            not row["issued_at"]<=stamp<=row["expires_at"]):
        raise PermissionError("original-world checkpoint is expired or future-dated")
    state=_state(row["player"])
    validate_state(world,state)
    if state.history_digest!=row["current_history_digest"]:
        raise ValueError("checkpoint player evidence chain differs from source")
    return state


def continue_world(
    world:LivingWorld,owner:str,
    *,previous_token:str|None=None,
    actions:tuple[str,...]=(),
    now:int|None=None,
)->dict:
    validate_world(world);_owner(owner)
    previous=(initial_state(world) if previous_token is None
              else open_checkpoint(world,previous_token,owner,now=now))
    advanced=replay(world,actions,starting_state=previous)
    new_token=seal_checkpoint(world,advanced,owner,now=now)
    return {
        "schema":SCHEMA,"world_fingerprint":world.world_fingerprint,
        "new_checkpoint":new_token,
        "steps_this_request":len(actions),
        "cumulative_actions":advanced.actions_played,
        "prior_history_digest":previous.history_digest,
        "current_history_digest":advanced.history_digest,
        "player":asdict(advanced),
        "expires_after_seconds":TTL_SECONDS,
        "scope":"renewable signed original game state, not durable backend archival storage",
    }
