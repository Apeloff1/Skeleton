"""Bounded metadata-only reconciliation of existing owner quota reservations.

A missing row is not a proven deletion: an admitted create may be in flight.
Only a permanent, exact scoped tombstone with a valid deletion receipt is
eligible for automatic quota release. No source bytes or permissions change.
"""
from __future__ import annotations

from .dragon_treasury_vault import identity,hash_identity,validate_marker,MAX_VAULT_SESSIONS

MAX_ACTIVE=32
MAX_RESERVED=MAX_ACTIVE+MAX_VAULT_SESSIONS
CATEGORIES=("active","vaulted","in_transit","tombstoned","missing","integrity_held")


def quota_lists(document):
    if document is None:
        return [],[]
    if not isinstance(document,dict):
        raise ValueError("invalid quota document")
    active=document.get("session_ids",[])
    vault=document.get("vault_ids",[])
    for values,limit in ((active,MAX_ACTIVE),(vault,MAX_VAULT_SESSIONS)):
        if (not isinstance(values,list) or len(values)>limit
                or not all(identity(x) for x in values) or len(set(values))!=len(values)):
            raise ValueError("invalid bounded quota reservation list")
    return active,vault


def quota_fence(document,scope):
    """Exact arrays, including absent fields; never overwrite worker accounting."""
    quota_lists(document)
    return {"_id":document["_id"],**scope,
            **{name:document[name] if name in document else {"$exists":False}
               for name in ("session_ids","vault_ids")}}


def tombstone(row):
    if not isinstance(row,dict) or row.get("status")!="deleted":
        return False
    receipt=row.get("deletion")
    # Deletion publication removes the primary witness and vault marker.
    # Reject partially erased rows rather than guessing their authority.
    return (isinstance(receipt,dict) and set(receipt)=={"operation","request_digest"}
            and hash_identity(receipt["operation"]) and hash_identity(receipt["request_digest"])
            and "checkpoint_identity" not in row and "treasury_vault" not in row)


def classify_quota(document,rows,scope):
    active,vault=quota_lists(document)
    a,z=set(active),set(vault)
    ids=a|z
    if not isinstance(rows,list) or len(rows)>MAX_RESERVED:
        raise ValueError("quota audit exceeds bound")
    indexed={}
    for row in rows:
        if (not isinstance(row,dict) or row.get("_id") not in ids
                or row["_id"] in indexed or any(row.get(k)!=val for k,val in scope.items())
                or type(row.get("version")) is not int or row["version"]<1):
            raise ValueError("quota audit scope or identity mismatch")
        indexed[row["_id"]]=row
    counts=dict.fromkeys(CATEGORIES,0)
    releasable=[]
    for sid in sorted(ids):
        row=indexed.get(sid)
        if row is None:
            counts["missing"]+=1
            continue
        if tombstone(row):
            counts["tombstoned"]+=1
            releasable.append(sid)
            continue
        if row["status"] not in {"queued","ready","running","paused","completed",
                                 "budget_exhausted","cancelled","failed","interrupted"}:
            counts["integrity_held"]+=1
            continue
        marker=row.get("treasury_vault")
        if marker is None:
            counts["active" if sid in a and sid not in z else "integrity_held"]+=1
            continue
        try:
            mark=validate_marker(marker)
            witness=row.get("checkpoint_identity")
            if (row["status"] not in {"completed","budget_exhausted"} or not isinstance(witness,dict)
                    or witness.get("snapshot_digest")!=mark["snapshot_digest"]):
                raise ValueError("retirement witness mismatch")
        except (ValueError,KeyError,TypeError):
            counts["integrity_held"]+=1
            continue
        if mark["state"]=="pending" and sid in a:
            counts["in_transit"]+=1
        elif mark["state"]=="vaulted" and sid in z and not mark["active_slot_released"]:
            counts["in_transit"]+=1
        elif mark["state"]=="vaulted" and mark["active_slot_released"] and sid in z and sid not in a:
            counts["vaulted"]+=1
        else:
            counts["integrity_held"]+=1
    return {"active_reserved":len(active),"vault_reserved":len(vault),"distinct_reserved":len(ids),
            "dual_reserved":len(a&z),"active_capacity":MAX_ACTIVE,"vault_capacity":MAX_VAULT_SESSIONS,
            **counts},releasable
