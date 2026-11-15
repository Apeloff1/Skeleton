"""Finite owner-authorized maintenance of exact retired copies, not source use."""
from __future__ import annotations

from .dragon_treasury_vault import finite,hash_identity

SCHEMA="skeleton.dragon.vault-care.v1"
MAX_DAYS=7
MAX_REPAIRS=3
DAY=86400


def validate_care(value):
    if (not isinstance(value,dict) or set(value)!={"schema","operation","request_digest","snapshot_digest",
            "issued_at","expires_at","enabled","budget","used","last_repair","principal_email"}
            or value["schema"]!=SCHEMA
            or not all(hash_identity(value[k]) for k in ("operation","request_digest","snapshot_digest"))
            or not isinstance(value["principal_email"],str) or not 3<=len(value["principal_email"])<=200
            or value["principal_email"]!=value["principal_email"].strip().lower()
            or not finite(value["issued_at"]) or not finite(value["expires_at"])
            or not 0<value["expires_at"]-value["issued_at"]<=MAX_DAYS*DAY
            or type(value["enabled"]) is not bool
            or type(value["budget"]) is not int or not 1<=value["budget"]<=MAX_REPAIRS
            or type(value["used"]) is not int or not 0<=value["used"]<=value["budget"]):
        raise ValueError("invalid custody care grant")
    last=value["last_repair"]
    if value["used"]==0:
        if last is not None:
            raise ValueError("unexpected repair receipt")
    elif (not isinstance(last,dict) or set(last)!={"side","at","version"}
            or last["side"] not in ("primary","replica") or not finite(last["at"])
            or not value["issued_at"]<=last["at"]<value["expires_at"]
            or type(last["version"]) is not int or last["version"]<2):
        raise ValueError("invalid repair receipt")
    return value


def issue_care(*,operation,request_digest,snapshot_digest,principal_email,now,days,budget,enabled=True):
    if type(days) is not int or not 1<=days<=MAX_DAYS:
        raise ValueError("care duration out of range")
    return validate_care({"schema":SCHEMA,"operation":operation,"request_digest":request_digest,
        "snapshot_digest":snapshot_digest,"issued_at":now,"expires_at":now+days*DAY,
        "enabled":enabled,"budget":budget,"used":0,"last_repair":None,"principal_email":principal_email})


def public_care(value,*,now,version,witness):
    grant=validate_care(value)
    if (grant["snapshot_digest"]!=witness or grant["last_repair"] is not None
            and grant["last_repair"]["version"]>version):
        raise ValueError("care witness or version mismatch")
    remaining=grant["budget"]-grant["used"]
    active=grant["enabled"] and grant["issued_at"]<=now<grant["expires_at"] and remaining>0
    return {"enabled":grant["enabled"],"active":active,"issued_at":grant["issued_at"],
        "expires_at":grant["expires_at"],"budget":grant["budget"],"used":grant["used"],
        "remaining":remaining,"last_repair":grant["last_repair"],
        "source_use_authorized":False,"network_authorized":False}


def consume_care(value,*,now,version,witness,side):
    if side not in ("primary","replica") or type(version) is not int or version<1:
        raise ValueError("invalid repair target")
    grant=validate_care(value)
    if not public_care(grant,now=now,version=version,witness=witness)["active"]:
        raise ValueError("maintenance grant unavailable")
    return validate_care({**grant,"used":grant["used"]+1,
        "last_repair":{"side":side,"at":now,"version":version+1}})
