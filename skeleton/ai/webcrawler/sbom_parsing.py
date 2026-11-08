"""Shared finite JSON/identity normalization for inert SBOM/VEX documents."""
from __future__ import annotations
import json
import re
from typing import Any
from .research_projection import ResearchFormatError, check_text

_MIME = frozenset({
    "application/vnd.cyclonedx+json",
    "application/spdx+json",
    "application/vnd.openvex+json",
})
_PURL_ECOSYSTEM=re.compile(r"^pkg:([A-Za-z0-9.+-]{1,40})/")
_ALLOWED_LICENSE=re.compile(r"^[A-Za-z0-9._+-]{1,128}$")
_ID=re.compile(r"^[A-Za-z0-9._:+/@#-]{1,256}$")


def unique(pairs:list[tuple[str,Any]])->dict[str,Any]:
    value={}
    for key,part in pairs:
        if key in value:
            raise ResearchFormatError("duplicate external SBOM/VEX object key")
        value[key]=part
    return value


def nonfinite(value:str)->Any:
    raise ResearchFormatError("nonfinite external component metadata")


def load(raw:str,*,max_chars:int)->dict:
    check_text(raw,max_chars=max_chars)
    try:
        obj=json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite)
    except (ValueError,RecursionError) as exc:
        raise ResearchFormatError("unparseable external software inventory") from exc
    if not isinstance(obj,dict):
        raise ResearchFormatError("software inventory must be an object")
    return obj


def identity(value:object)->str:
    if not isinstance(value,str) or not _ID.fullmatch(value):
        raise ResearchFormatError("invalid external software identity")
    return value


def label(value:object,*,maxlen:int=256,empty:bool=False)->str:
    if (not isinstance(value,str) or len(value)>maxlen
            or (not empty and not value.strip())
            or any(ord(c)<32 or ord(c)==127 for c in value)):
        raise ResearchFormatError("invalid software source label")
    return value.strip()


def license_id(value:object)->str:
    if not isinstance(value,str) or not _ALLOWED_LICENSE.fullmatch(value):
        return "NOASSERTION"
    return value


def ecosystem_from_purl(value:object)->str:
    if not isinstance(value,str) or len(value)>2048:
        return "unspecified"
    match=_PURL_ECOSYSTEM.match(value)
    return match.group(1).lower() if match else "unspecified"


def count_rows(value:object,name:str,maxlen:int)->list:
    if not isinstance(value,list) or len(value)>maxlen:
        raise ResearchFormatError(f"{name} exceeds finite row capacity")
    return value


def limited_strings(values:object,name:str,maximum:int=32)->tuple[str,...]:
    if not isinstance(values,list) or len(values)>maximum:
        raise ResearchFormatError(f"{name} list capacity exceeded")
    return tuple(identity(x) for x in values)
