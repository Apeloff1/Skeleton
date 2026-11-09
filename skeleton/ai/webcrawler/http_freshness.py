"""Finite HTTP cache/validator observations for canonical source provenance.

Headers come from an untrusted remote site. Their freshness instructions
never renew consent, grant recrawl, authorize an origin, issue conditional
requests, override robots, prove authorship, or change source license rights.
ETags are hashed rather than retained because validators may contain
opaque credentials or tracking identities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
from collections.abc import Mapping

_MAX_HEADER_BYTES=8192
_MAX_CACHE_SECONDS=604800
_AGENT_VARY=frozenset({
    "accept","accept-language","accept-encoding","user-agent",
})
_LANGUAGE=re.compile(r"(?i)^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,4}$")
_HASH=re.compile(r"^[a-f0-9]{64}$")
_SECONDS=re.compile(r"^[0-9]{1,9}$")
_RECEIPT_SCHEMA="skeleton.ai.crawl.http_freshness.v1"


class FreshnessError(ValueError):
    """Malformed, oversized or unbounded source metadata."""


@dataclass(frozen=True)
class FreshnessReceipt:
    schema:str
    etag_digest:str|None
    last_modified_unix:float|None
    date_unix:float|None
    expires_unix:float|None
    age_seconds:int
    max_age_seconds:int|None
    stale_while_revalidate_seconds:int|None
    no_store:bool
    no_cache:bool
    private:bool
    must_revalidate:bool
    sensitive_vary:bool
    vary_dimensions:tuple[str,...]
    languages:tuple[str,...]
    advisory_due_unix:float|None
    headers_untrusted:bool=True
    grants_new_consent:bool=False
    network_executed:bool=False


def _seconds(value:str|None,*,name:str)->int|None:
    if value is None:
        return None
    if not isinstance(value,str) or not _SECONDS.fullmatch(value.strip()):
        raise FreshnessError("invalid HTTP "+name+" seconds")
    number=int(value.strip())
    if number>_MAX_CACHE_SECONDS:
        raise FreshnessError("HTTP "+name+" seconds exceed finite cap")
    return number


def _http_date(value:str|None)->float|None:
    if value is None:
        return None
    if not isinstance(value,str) or len(value)>128:
        raise FreshnessError("oversized HTTP date")
    try:
        parsed=parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            raise ValueError("HTTP date missing zone")
        stamp=parsed.timestamp()
    except (ValueError,TypeError,OverflowError,IndexError) as exc:
        raise FreshnessError("malformed HTTP date") from exc
    if not 0<=stamp<=4102444800:
        raise FreshnessError("HTTP date outside admissible epoch")
    return round(stamp,3)


def _cache_control(raw:str)->dict:
    if not isinstance(raw,str) or len(raw)>_MAX_HEADER_BYTES:
        raise FreshnessError("Cache-Control source field exceeds bound")
    flags={
        "no_store":False,"no_cache":False,"private":False,
        "must_revalidate":False,
    }
    seconds={"max_age_seconds":None,"stale_while_revalidate_seconds":None}
    if not raw:
        return {**flags,**seconds}
    for item in raw.split(","):
        item=item.strip()
        if not item:
            continue
        token,separator,value=item.partition("=")
        key=token.strip().casefold()
        if key in ("no-store","no-cache","private","must-revalidate"):
            flags[key.replace("-","_")]=True
            continue
        if key in ("max-age","s-maxage","stale-while-revalidate"):
            if key=="s-maxage":
                # Shared-cache semantics are not evidence of source rights.
                continue
            name=("max_age_seconds" if key=="max-age"
                  else "stale_while_revalidate_seconds")
            seconds[name]=_seconds(value.strip().strip('"'),name=key)
    return {**flags,**seconds}


def _vary(raw:str)->tuple[tuple[str,...],bool]:
    if not isinstance(raw,str) or len(raw)>_MAX_HEADER_BYTES:
        raise FreshnessError("Vary header exceeds finite cap")
    if not raw:
        return (),False
    parts=[x.strip().casefold() for x in raw.split(",") if x.strip()]
    if len(parts)>16 or any(len(x)>128 for x in parts):
        raise FreshnessError("Vary dimension list exceeds bound")
    sensitive=any(x not in _AGENT_VARY for x in parts)
    return tuple(sorted(set(x for x in parts if x in _AGENT_VARY))),sensitive


def _languages(raw:str)->tuple[str,...]:
    if not isinstance(raw,str) or len(raw)>256:
        raise FreshnessError("Content-Language header exceeds finite cap")
    if not raw:
        return ()
    entries=[x.strip() for x in raw.split(",")]
    if len(entries)>8 or any(not _LANGUAGE.fullmatch(x) for x in entries):
        raise FreshnessError("Content-Language token is unsupported")
    return tuple(sorted(set(x.casefold() for x in entries)))


def observe_http_freshness(
    headers:Mapping[str,str],*,observed_at:float,
)->FreshnessReceipt:
    if (not isinstance(headers,Mapping)
            or type(observed_at) not in (int,float)
            or not 0<=observed_at<=4102444800):
        raise FreshnessError("invalid HTTP receipt source authority")
    values={}
    for name,value in headers.items():
        if not isinstance(name,str) or not isinstance(value,str):
            raise FreshnessError("invalid HTTP receipt header type")
        key=name.casefold().strip()
        if key not in ("etag","last-modified","date","expires","age",
                       "cache-control","vary","content-language"):
            continue
        if key in values or len(value)>_MAX_HEADER_BYTES:
            raise FreshnessError("duplicate or oversized HTTP provenance field")
        values[key]=value
    etag=values.get("etag")
    if etag is not None and (len(etag)>512 or "\r" in etag or "\n" in etag):
        raise FreshnessError("opaque ETag is malformed or unbounded")
    digest=hashlib.sha256(etag.encode("utf-8")).hexdigest() if etag else None
    dates={
        "last_modified_unix":_http_date(values.get("last-modified")),
        "date_unix":_http_date(values.get("date")),
        "expires_unix":_http_date(values.get("expires")),
    }
    cache=_cache_control(values.get("cache-control",""))
    age=_seconds(values.get("age"),name="Age") or 0
    vary,sensitive=_vary(values.get("vary",""))
    lang=_languages(values.get("content-language",""))
    due=None
    if not cache["no_store"] and not cache["no_cache"]:
        max_age=cache["max_age_seconds"]
        if max_age is not None:
            due=observed_at+max(0,max_age-age)
        elif dates["expires_unix"] is not None:
            due=max(observed_at,dates["expires_unix"])
        if due is not None:
            due=round(min(due,observed_at+_MAX_CACHE_SECONDS),3)
    return FreshnessReceipt(
        schema=_RECEIPT_SCHEMA,etag_digest=digest,
        **dates,age_seconds=age,**cache,
        vary_dimensions=vary,sensitive_vary=sensitive,
        languages=lang,advisory_due_unix=due,
    )


def verify_freshness_receipt(value:object,*,observed_at:float)->bool:
    if not isinstance(value,dict):
        return False
    expected=set(FreshnessReceipt.__dataclass_fields__)
    if set(value)!=expected:
        return False
    if value.get("schema")!=_RECEIPT_SCHEMA or (
        value.get("headers_untrusted") is not True
        or value.get("grants_new_consent") is not False
        or value.get("network_executed") is not False
    ):
        return False
    etag=value["etag_digest"]
    if etag is not None and (not isinstance(etag,str) or not _HASH.fullmatch(etag)):
        return False
    for name in ("age_seconds","max_age_seconds","stale_while_revalidate_seconds"):
        item=value.get(name)
        if item is not None and (
            type(item) is not int or not 0<=item<=_MAX_CACHE_SECONDS
        ):
            return False
    for name in ("no_store","no_cache","private","must_revalidate","sensitive_vary"):
        if type(value.get(name)) is not bool:
            return False
    dims=value.get("vary_dimensions")
    if (not isinstance(dims,(list,tuple)) or len(dims)>4
            or any(x not in _AGENT_VARY for x in dims)
            or list(dims)!=sorted(set(dims))):
        return False
    langs=value.get("languages")
    if (not isinstance(langs,(list,tuple)) or len(langs)>8
            or any(not isinstance(x,str) or not _LANGUAGE.fullmatch(x) for x in langs)
            or list(langs)!=sorted(set(langs))):
        return False
    for name in ("last_modified_unix","date_unix","expires_unix","advisory_due_unix"):
        stamp=value.get(name)
        if stamp is not None and (
            type(stamp) not in (int,float) or not 0<=stamp<=4102444800
        ):
            return False
    due=value.get("advisory_due_unix")
    if due is not None and (
        value["no_store"] or value["no_cache"]
        or not observed_at<=due<=observed_at+_MAX_CACHE_SECONDS+.001
    ):
        return False
    return True
