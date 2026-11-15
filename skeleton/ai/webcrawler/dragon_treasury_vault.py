"""Cold-custody retirement contract. Storage classification is not source-use authority."""
from __future__ import annotations

import math
import re

SCHEMA="skeleton.dragon.vault.v1"
MAX_VAULT_SESSIONS=1024
MAX_WINDOW=32
TERMINAL=frozenset({"completed","budget_exhausted"})
_HASH=re.compile(r"[a-f0-9]{64}\Z")
_ID=re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def identity(value):
    return isinstance(value,str) and _ID.fullmatch(value) is not None


def hash_identity(value):
    return isinstance(value,str) and _HASH.fullmatch(value) is not None


def finite(value):
    return type(value) in (float,int) and math.isfinite(value) and value>=0


def selected_ids(values):
    if (not isinstance(values,list) or not 1<=len(values)<=MAX_WINDOW
            or not all(identity(x) for x in values) or len(set(values))!=len(values)):
        raise ValueError("invalid explicit vault search window")
    return tuple(sorted(values))


def make_marker(*,operation,request_digest,snapshot_digest,now):
    return validate_marker({"schema":SCHEMA,"operation":operation,"request_digest":request_digest,
        "snapshot_digest":snapshot_digest,"accepted_at":now,"state":"pending",
        "active_slot_released":False,"retry_at":now})


def validate_marker(marker):
    if (not isinstance(marker,dict) or set(marker)!={"schema","operation","request_digest",
            "snapshot_digest","accepted_at","state","active_slot_released","retry_at"}
            or marker["schema"]!=SCHEMA
            or not all(hash_identity(marker[k]) for k in ("operation","request_digest","snapshot_digest"))
            or not all(finite(marker[k]) for k in ("accepted_at","retry_at"))
            or marker["retry_at"]<marker["accepted_at"]
            or marker["state"] not in {"pending","vaulted"}
            or type(marker["active_slot_released"]) is not bool
            or marker["state"]=="pending" and marker["active_slot_released"]):
        raise ValueError("invalid vault marker")
    return marker


def public_marker(marker):
    m=validate_marker(marker)
    return {"state":m["state"],"accepted_at":m["accepted_at"],
            "active_slot_released":m["active_slot_released"],"snapshot_digest":m["snapshot_digest"],
            "execution_authorized":False,"historical_grant_extended":False}


def reserve_filter(scope,quota_id,identifier):
    if not identity(identifier) or not hash_identity(quota_id):
        raise ValueError("invalid quota identity")
    return {"_id":quota_id,**scope,"$or":[{"vault_ids":identifier},
        {"session_ids":identifier,f"vault_ids.{MAX_VAULT_SESSIONS-1}":{"$exists":False}}]}


def release_active_filter(scope,quota_id,identifier):
    if not identity(identifier) or not hash_identity(quota_id):
        raise ValueError("invalid quota identity")
    return {"_id":quota_id,**scope,"vault_ids":identifier}
