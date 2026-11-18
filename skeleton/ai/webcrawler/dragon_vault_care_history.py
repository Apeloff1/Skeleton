"""Bounded care receipts, atomically published with local custody commands.

This hash chain detects accidental corruption within the retained window;
it is not an independent audit authority or a source-use grant.
"""
from __future__ import annotations

import hashlib
import json
from .dragon_treasury_vault import finite,hash_identity

SCHEMA="skeleton.dragon.vault-care-history.v1"
MAX_EVENTS=16
ZERO="0"*64
KINDS={"grant","withdraw","auto_primary","auto_replica"}


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


def validate_history(value,*,witness,version):
    if (not hash_identity(witness) or type(version) is not int or version<1
            or not isinstance(value,dict) or set(value)!={"schema","witness","prefix_unknown","omitted","anchor","entries","head"}
            or value["schema"]!=SCHEMA or value["witness"]!=witness
            or type(value["prefix_unknown"]) is not bool or type(value["omitted"]) is not int
            or not 0<=value["omitted"]<=2**31-1 or not hash_identity(value["anchor"])
            or not hash_identity(value["head"]) or (value["omitted"]==0)!=(value["anchor"]==ZERO)
            or not isinstance(value["entries"],list) or not 1<=len(value["entries"])<=MAX_EVENTS):
        raise ValueError("invalid care history envelope")
    previous=value["anchor"]
    old_version=0
    old_at=0
    active=None
    for seq,entry in enumerate(value["entries"],value["omitted"]+1):
        if (not isinstance(entry,dict) or set(entry)!={"sequence","version","at","kind","operation","budget","used","previous","digest"}
                or type(entry["sequence"]) is not int or entry["sequence"]!=seq
                or type(entry["version"]) is not int or not old_version<entry["version"]<=version
                or not finite(entry["at"]) or entry["at"]<old_at
                or not isinstance(entry["kind"],str) or entry["kind"] not in KINDS
                or not hash_identity(entry["operation"]) or not hash_identity(entry["digest"])
                or entry["previous"]!=previous or type(entry["budget"]) is not int or not 1<=entry["budget"]<=3
                or type(entry["used"]) is not int or not 0<=entry["used"]<=entry["budget"]
                or _digest({k:v for k,v in entry.items() if k!="digest"})!=entry["digest"]):
            raise ValueError("invalid care history receipt")
        kind=entry["kind"]
        if kind in {"grant","withdraw"}:
            if entry["used"]!=0:
                raise ValueError("new grant has consumed repair credit")
            active=(kind,entry["operation"],entry["budget"],0)
        else:
            if entry["used"]<1 or (active is None and not (value["omitted"] or value["prefix_unknown"])):
                raise ValueError("repair lacks a recorded grant")
            if active is not None and active!=("grant",entry["operation"],entry["budget"],entry["used"]-1):
                raise ValueError("repair credit or grant discontinuity")
            active=("grant",entry["operation"],entry["budget"],entry["used"])
        previous=entry["digest"]
        old_at=entry["at"]
        old_version=entry["version"]
    if previous!=value["head"]:
        raise ValueError("care history head mismatch")
    return value


def append_history(prior,*,witness,version,at,kind,operation,budget,used,prefix_unknown=False):
    if prior is None:
        value={"schema":SCHEMA,"witness":witness,"prefix_unknown":prefix_unknown,
               "omitted":0,"anchor":ZERO,"entries":[],"head":ZERO}
    else:
        value=validate_history(prior,witness=witness,version=version-1)
    entries=list(value["entries"])
    event={"sequence":value["omitted"]+len(entries)+1,"version":version,"at":at,"kind":kind,
           "operation":operation,"budget":budget,"used":used,"previous":value["head"]}
    event["digest"]=_digest(event)
    entries.append(event)
    dropped=max(0,len(entries)-MAX_EVENTS)
    return validate_history({**value,"entries":entries[dropped:],"omitted":value["omitted"]+dropped,
          "anchor":entries[dropped-1]["digest"] if dropped else value["anchor"],"head":event["digest"]},
          witness=witness,version=version)


def public_history(value,*,witness,version):
    if value is None:
        return {"state":"unrecorded","prefix_unknown":True,"omitted":0,"events":[]}
    value=validate_history(value,witness=witness,version=version)
    return {"state":"recorded","prefix_unknown":value["prefix_unknown"],"omitted":value["omitted"],
            "events":[{k:e[k] for k in ("sequence","version","at","kind","budget","used")} for e in value["entries"]]}
