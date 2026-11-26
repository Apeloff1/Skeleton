"""Owner-authorized finite revisit grants. No transport lives in this module.

A watch names exactly one previously admitted public source. A scheduler
may reserve bounded child expeditions only while its independent grant,
source policy, owner role, budget, and deadline are current. A child must
recheck the parent before every physical request. Observed failures never
confer permission to retry outside the existing canonical transport.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from .dragon_revisit_model import ChangeSample, infer_revisit

SCHEMA="skeleton.dragon.treasury-watch.v1"
MAX_CYCLES=6
MAX_DAYS=7
MIN_INTERVAL=6*3600
MAX_INTERVAL=7*86400
MAX_SLICES=8
LEASE_SECONDS=180
_HEX=re.compile(r"[a-f0-9]{64}\Z")


def _hex(value):
    return isinstance(value,str) and _HEX.fullmatch(value) is not None


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def safe_watch_url(url):
    if not isinstance(url,str) or not 1<=len(url.encode("utf-8"))<=2048:
        return False
    try:
        parsed=urlsplit(url)
        # No query-bearing or credential-bearing URLs in an unattended watch.
        return (parsed.scheme in {"http","https"} and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment
                and parsed.port in {None,80,443})
    except ValueError:
        return False


def same_watch_representation(parent:dict,candidate:dict)->bool:
    """A public revisit sample must describe the same representation family.

    Matching URLs alone are insufficient: declared media, languages and
    Vary dimensions are independent boundaries. Missing receipt fields,
    private or uncacheable captures, and sensitive variance fail closed.
    """
    def identity(source):
        if not isinstance(source,dict) or not safe_watch_url(source.get("fetched_url")):
            return None
        provenance=source.get("provenance")
        receipt=provenance.get("http_freshness") if isinstance(provenance,dict) else None
        if (not isinstance(receipt,dict)
                or any(receipt.get(k) is not False for k in ("private","no_store","sensitive_vary"))):
            return None
        media=source.get("content_type")
        langs=receipt.get("languages")
        vary=receipt.get("vary_dimensions")
        if (not isinstance(media,str) or not 1<=len(media)<=256
                or not isinstance(langs,(list,tuple)) or not isinstance(vary,(list,tuple))
                or len(langs)>8 or len(vary)>4
                or not all(isinstance(v,str) and 1<=len(v)<=256 for v in (*langs,*vary))
                or list(langs)!=sorted(set(langs)) or list(vary)!=sorted(set(vary))):
            return None
        return source["fetched_url"],media,tuple(langs),tuple(vary)
    a,b=identity(parent),identity(candidate)
    return a is not None and a==b


def create_watch(*, operation:str, parent_id:str, scope:dict, principal_email:str,
                 snapshot_digest:str, source:dict, policy_version:int, now:float,
                 days:int, cycles:int, minimum_interval:int, retention_days:int)->dict:
    if (not _hex(operation) or not _hex(snapshot_digest)
            or not isinstance(parent_id,str) or not 1<=len(parent_id)<=128
            or not isinstance(scope,dict) or set(scope)!={"tenant_id","owner_id"}
            or not all(isinstance(v,str) and 1<=len(v)<=128 for v in scope.values())
            or not isinstance(principal_email,str) or not 3<=len(principal_email)<=200
            or not _number(now) or now<0
            or type(days) is not int or not 1<=days<=MAX_DAYS
            or type(cycles) is not int or not 1<=cycles<=MAX_CYCLES
            or type(minimum_interval) is not int or not MIN_INTERVAL<=minimum_interval<=MAX_INTERVAL
            or type(retention_days) is not int or not 1<=retention_days<=30
            or type(policy_version) is not int or not 0<=policy_version<=2**31-1
            or not _hex(source.get("source_id")) or not _hex(source.get("content_hash"))
            or not safe_watch_url(source.get("fetched_url")) or not _number(source.get("fetched_at"))
            or not 0<=source["fetched_at"]<=now+300):
        raise ValueError("invalid finite watch bounds")
    expires=now+days*86400
    sample={"at":source["fetched_at"],"digest":source["content_hash"]}
    due=now+minimum_interval
    if due+60>=expires:
        raise ValueError("watch duration cannot admit even one complete revisit")
    return {"schema":SCHEMA,"epoch":operation,"parent_id":parent_id,"scope":scope,
            "principal_email":principal_email,"snapshot_digest":snapshot_digest,
            "source_id":source["source_id"],"policy_version":policy_version,
            "url":source["fetched_url"],"issued_at":now,"expires_at":expires,
            "max_cycles":cycles,"minimum_interval":minimum_interval,"retention_days":retention_days,
            "enabled":True,"state":"waiting","cycles_started":0,"cycles_completed":0,
            "active_cycle":None,"slices_started":0,"next_due":due,"claim_token":None,
            "claim_until":0.,"samples":[sample],"last_child_id":None,"stop_reason":None,
            "capture_rights_acknowledged":True,"archive_rights_acknowledged":True,
            "network_scope":"exact_public_seed_canonical_policy"}


def validate_watch(value:object)->dict:
    keys={"schema","epoch","parent_id","scope","principal_email","snapshot_digest","source_id","policy_version",
          "url","issued_at","expires_at","max_cycles","minimum_interval","retention_days","enabled","state",
          "cycles_started","cycles_completed","active_cycle","slices_started","next_due","claim_token","claim_until",
          "samples","last_child_id","stop_reason","capture_rights_acknowledged","archive_rights_acknowledged","network_scope"}
    if not isinstance(value,dict) or set(value)!=keys or value["schema"]!=SCHEMA:
        raise ValueError("invalid watch schema")
    w=value
    if (not all(_hex(w[key]) for key in ("epoch","snapshot_digest","source_id"))
            or not isinstance(w["parent_id"],str) or not 1<=len(w["parent_id"])<=128
            or not isinstance(w["scope"],dict) or set(w["scope"])!={"tenant_id","owner_id"}
            or not all(isinstance(v,str) and 1<=len(v)<=128 for v in w["scope"].values())
            or not isinstance(w["principal_email"],str) or not 3<=len(w["principal_email"])<=200
            or type(w["policy_version"]) is not int or not 0<=w["policy_version"]<=2**31-1
            or not safe_watch_url(w["url"]) or type(w["enabled"]) is not bool
            or w["state"] not in {"waiting","working","stopped","blocked"}
            or not all(_number(w[k]) for k in ("issued_at","expires_at","next_due","claim_until"))
            or not 0<=w["issued_at"]<w["expires_at"]<=w["issued_at"]+MAX_DAYS*86400
            or not w["issued_at"]<=w["next_due"]<=w["expires_at"]
            or not 0<=w["claim_until"]<=w["expires_at"]+LEASE_SECONDS
            or not all(type(w[k]) is int for k in ("max_cycles","minimum_interval","retention_days",
                     "cycles_started","cycles_completed","slices_started"))
            or not 1<=w["max_cycles"]<=MAX_CYCLES or not MIN_INTERVAL<=w["minimum_interval"]<=MAX_INTERVAL
            or not 1<=w["retention_days"]<=30 or not 0<=w["cycles_completed"]<=w["cycles_started"]<=w["max_cycles"]
            or not 0<=w["slices_started"]<=MAX_SLICES
            or w["active_cycle"] is not None and (type(w["active_cycle"]) is not int
                 or w["active_cycle"]!=w["cycles_started"] or w["cycles_completed"]!=w["cycles_started"]-1)
            or w["active_cycle"] is None and w["cycles_completed"]!=w["cycles_started"]
            or w["claim_token"] is not None and (not isinstance(w["claim_token"],str) or len(w["claim_token"])>64)
            or w["last_child_id"] is not None and (not isinstance(w["last_child_id"],str) or len(w["last_child_id"])>128)
            or w["stop_reason"] is not None and (not isinstance(w["stop_reason"],str) or len(w["stop_reason"])>64)
            or w["capture_rights_acknowledged"] is not True or w["archive_rights_acknowledged"] is not True
            or w["network_scope"]!="exact_public_seed_canonical_policy"):
        raise ValueError("invalid watch authority")
    if (not isinstance(w["samples"],list) or not 1<=len(w["samples"])<=MAX_CYCLES+1):
        raise ValueError("invalid watch history")
    previous=-1.
    for item in w["samples"]:
        if (not isinstance(item,dict) or set(item)!={"at","digest"} or not _number(item["at"])
                or not previous<item["at"]<=w["expires_at"] or not _hex(item["digest"])):
            raise ValueError("invalid watch sample")
        previous=item["at"]
    return w


def claim_watch(value:dict,*,now:float,token:str)->dict:
    w=dict(validate_watch(value))
    if (not _number(now) or now<0 or not w["enabled"] or w["state"] not in {"waiting","working"}
            or w["expires_at"]<=now+60 or w["next_due"]>now
            or w["claim_until"]>now or not isinstance(token,str) or not 1<=len(token)<=64):
        raise ValueError("watch is not claimable")
    if w["active_cycle"] is None:
        if w["cycles_started"]>=w["max_cycles"]:
            raise ValueError("watch cycle budget exhausted")
        w["cycles_started"]+=1
        w["active_cycle"]=w["cycles_started"]
        w["slices_started"]=0
    w.update(claim_token=token,claim_until=min(now+LEASE_SECONDS,w["expires_at"]),state="working")
    return validate_watch(w)


def child_binding(watch:dict)->dict:
    w=validate_watch(watch)
    if not w["enabled"] or w["active_cycle"] is None:
        raise ValueError("watch has no reserved child")
    return {"parent_id":w["parent_id"],"epoch":w["epoch"],"cycle":w["active_cycle"],
            "source_id":w["source_id"],"snapshot_digest":w["snapshot_digest"],
            "url_digest":digest(w["url"])}


def child_matches(binding:dict,watch:dict,*,now:float,margin:float=0)->bool:
    try:
        w=validate_watch(watch)
        return (_number(now) and _number(margin) and now>=0 and margin>=0
                and w["enabled"] and w["state"] in {"waiting","working"}
                and now+margin<w["expires_at"] and binding==child_binding(w))
    except (ValueError,TypeError,KeyError):
        return False


def settle_watch(value:dict,*,now:float,child_id:str,sample:dict|None,completed:bool)->dict:
    w=dict(validate_watch(value))
    if (not _number(now) or now<0 or w["active_cycle"] is None
            or not w["enabled"] or w["state"]!="working" or not w["claim_token"]
            or now>=w["claim_until"] or type(completed) is not bool
            or not isinstance(child_id,str) or not 1<=len(child_id)<=128):
        raise ValueError("unreserved watch settlement")
    w["samples"]=list(w["samples"])
    if sample is not None:
        if (not completed or not isinstance(sample,dict) or set(sample)!={"at","digest"}
                or not _number(sample["at"]) or not w["samples"][-1]["at"]<sample["at"]<=min(now+300,w["expires_at"])
                or not _hex(sample["digest"])):
            raise ValueError("invalid watch observation")
        w["samples"].append(sample)
    w["cycles_completed"]+=1
    w.update(active_cycle=None,slices_started=0,claim_token=None,claim_until=0.,last_child_id=child_id)
    delay=w["minimum_interval"]
    if completed and sample is not None:
        model=infer_revisit([ChangeSample(x["at"],x["digest"]) for x in w["samples"]],
                            now=now,publisher_due=None,allowed=True,priority_value=.7)
        delay=max(delay,model["interval_seconds"])
    elif not completed:
        # A failed cycle never adds a change sample or accelerates scheduling.
        delay=max(delay,24*3600)
    next_due=min(w["expires_at"],now+delay)
    exhausted=w["cycles_started"]>=w["max_cycles"] or next_due+60>=w["expires_at"]
    w.update(next_due=next_due,enabled=not exhausted,state="stopped" if exhausted else "waiting",
             stop_reason="cycle_budget" if w["cycles_started"]>=w["max_cycles"] else "authorization_expiry" if exhausted else None)
    return validate_watch(w)


def public_watch(value:dict|None,*,now:float)->dict|None:
    if value is None:
        return None
    w=validate_watch(value)
    return {"schema":SCHEMA,"source_id":w["source_id"],"enabled":w["enabled"] and now<w["expires_at"],
            "state":w["state"] if now<w["expires_at"] else "stopped",
            "expires_at":w["expires_at"],"max_cycles":w["max_cycles"],"cycles_started":w["cycles_started"],
            "cycles_completed":w["cycles_completed"],"next_due":w["next_due"],"retention_days":w["retention_days"],
            "minimum_interval":w["minimum_interval"],"last_child_id":w["last_child_id"],
            "stop_reason":w["stop_reason"] if now<w["expires_at"] else "authorization_expiry",
            "network_scope":w["network_scope"],"owner_revocable":True}
