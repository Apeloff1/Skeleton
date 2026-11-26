"""Explicit owner-bound loopback-only local discourse for autonomous crawler pulses.

The crawler grant controls dispatch, not this advisor. No cloud fallback,
redirect handling, source bodies, target URLs or credentials enter model prompts.
An unavailable advisor holds the explicitly opted-in pulse.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import time

from skeleton.ai.webcrawler.navigation_semantics import validate_packet,digest,ADVICE_LIFETIME

HEX=re.compile(r"[a-f0-9]{64}\Z")
MAX_RESPONSE=256*1024


class DiscourseHeld(RuntimeError):
    pass


def owner_binding(scope):
    return digest(scope)


def config(scope):
    raw=os.getenv("SKL_DRAGON_AUTONOMOUS_DISCOURSE_JSON","")
    if not raw or len(raw)>4096:
        raise DiscourseHeld("local discourse configuration required")
    try:
        value=json.loads(raw)
        if (not isinstance(value,dict) or not {"owner_digest","port","token_file","model_digest"}<=set(value)
                or set(value)-{"owner_digest","port","token_file","model_digest","dragon_model_digest"}
                or "dragon_model_digest" in value and (not HEX.fullmatch(value["dragon_model_digest"])
                    or value["dragon_model_digest"]==value["model_digest"])
                or value["owner_digest"]!=owner_binding(scope)
                or not HEX.fullmatch(value["model_digest"])
                or type(value["port"]) is not int or not 1<=value["port"]<=65535
                or not isinstance(value["token_file"],str) or not Path(value["token_file"]).is_absolute()):
            raise ValueError("configuration")
    except (ValueError,TypeError,KeyError,RecursionError) as exc:
        raise DiscourseHeld("owner-bound local discourse configuration held") from exc
    return value


def _token(path):
    path=Path(path)
    before=path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_size>512
            or before.st_nlink!=1 or os.name=="posix" and
            (before.st_uid!=os.getuid() or before.st_mode&0o077)):
        raise DiscourseHeld("private local token file required")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    try:
        current=os.fstat(fd)
        if (before.st_dev,before.st_ino,before.st_size)!=(current.st_dev,current.st_ino,current.st_size):
            raise DiscourseHeld("local token identity changed")
        token=os.read(fd,513).decode("ascii").strip()
    finally:os.close(fd)
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}",token):
        raise DiscourseHeld("invalid local token")
    return token


def advise(scope,packet,*,grant_deadline):
    conf=config(scope)
    ids=set(validate_packet(packet))
    deadline=min(grant_deadline-15,packet["as_of"]+ADVICE_LIFETIME,time.time()+180)
    if deadline-time.time()<5:
        raise DiscourseHeld("local model deadline exhausted")
    connection=None
    try:
        token=_token(conf["token_file"])
        connection=http.client.HTTPConnection("127.0.0.1",conf["port"],timeout=max(1,deadline-time.time()))
        independent=conf.get("dragon_model_digest")
        body=json.dumps({"packet":packet,"approved":True,"deadline":deadline,
            **({"dragon_model_digest":independent} if independent else {})},ensure_ascii=True).encode()
        connection.request("POST","/v1/dragon/navigation-discourse",body=body,
            headers={"Content-Type":"application/json","Authorization":"Bearer "+token})
        response=connection.getresponse()
        raw=response.read(MAX_RESPONSE+1)
        if response.status!=200 or len(raw)>MAX_RESPONSE:
            raise DiscourseHeld("local discourse did not complete")
        value=json.loads(raw)
        advice=value["advice"]
        receipts=value["role_receipts"]
        if (value["model_digest"]!=conf["model_digest"] or value["network_authorized"] is not False
                or value["single_local_model_two_roles"] is not (independent is None) or value["candidate_count"]!=len(ids)
                or independent is not None and (value.get("dragon_model_digest")!=independent or value.get("distinct_role_weights") is not True)
                or set(advice)!={"snapshot_digest","as_of","packet_digest","jeeves_rank","dragon_rank"}
                or any(advice[k]!=packet[k] for k in ("snapshot_digest","as_of","packet_digest"))
                or not isinstance(receipts,list) or not 2<=len(receipts)<=18 or len(receipts)%2):
            raise DiscourseHeld("local inference identity differs")
        for key in ("jeeves_rank","dragon_rank"):
            rank=advice[key]
            if not isinstance(rank,list) or not 1<=len(rank)<=12 or len(set(rank))!=len(rank) or not set(rank)<=ids:
                raise DiscourseHeld("unbound local inference rank")
        for offset in range(0,len(receipts),2):
            a,b=receipts[offset:offset+2]
            if (a["role"],b["role"])!=("jeeves","dragon") or a["stage"]!=b["stage"] or a["group_digest"]!=b["group_digest"] or a["session_id"]==b["session_id"]:
                raise DiscourseHeld("local role custody differs")
            if independent is not None:
                proof=b["specialist_receipt"]
                if (a.get("model_digest")!=conf["model_digest"] or a.get("engine")!="native_jeeves"
                        or b.get("model_digest")!=independent or b.get("engine")!="dragon_neural_ranker"
                        or proof.get("schema")!="skeleton.dragon.specialist-execution.v1"
                        or proof.get("model_digest")!=independent or proof.get("packet_digest")!=b["group_digest"]
                        or proof.get("network_authorized") is not False or proof.get("output_digest")!=b["output_digest"]
                        or proof.get("execution_receipt_digest")!=b["execution_receipt_digest"]
                        or digest({k:v for k,v in proof.items() if k!="execution_receipt_digest"})!=b["execution_receipt_digest"]):
                    raise DiscourseHeld("independent Dragon execution witness differs")
            for row in (a,b):
                if any(not HEX.fullmatch(row[k]) for k in ("execution_receipt_digest","output_digest","group_digest")):
                    raise DiscourseHeld("local inference receipt differs")
        if receipts[-1]["stage"]!="final" or time.time()>=deadline:
            raise DiscourseHeld("local discourse expired")
        result={"advice":advice,"model_digest":conf["model_digest"],"role_calls":len(receipts),
                "role_receipts_digest":digest(receipts),"network_authorized":False,
                **({"dragon_model_digest":independent} if independent else {})}
        return {**result,"receipt":digest(result)}
    except (OSError,ValueError,TypeError,KeyError,http.client.HTTPException) as exc:
        raise DiscourseHeld("local discourse unavailable or invalid") from exc
    finally:
        if connection is not None:connection.close()
