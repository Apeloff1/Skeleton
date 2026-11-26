"""Explicit archival-use grant over immutable retained text, never fetch authority.

The grant is attached to the existing owner-scoped session row. It does not
change capture consent, ordinary freshness policy, or model-use permissions.
Withdrawal or any source-use policy revision invalidates the affected member.
"""
from __future__ import annotations

import math
import re

SCHEMA = "skeleton.dragon.archive-grant.v1"
MAX_DAYS = 30
MAX_SOURCES = 64
_HASH = re.compile(r"[a-f0-9]{64}\Z")


def _hash(x: object) -> bool:
    return isinstance(x,str) and bool(_HASH.fullmatch(x))


def eligible_source(source: dict, policy: dict) -> bool:
    from .source_instruction_guard import inspect_extracted
    # Missing/ambiguous cache receipt is not independent archive authority.
    provenance = source["provenance"]
    receipt = provenance.get("http_freshness")
    if (not policy["enabled"] or not isinstance(receipt,dict)
            or any(receipt.get(k) is not False for k in ("private","no_store","sensitive_vary"))
            or provenance.get("source_status")!="unreviewed_external_capture"
            or provenance.get("training_permission") is not False):
        return False
    return not inspect_extracted(source["title"],source["text"]).held


def create_grant(*, snapshot: dict, policies: dict, now: float, days: int) -> dict:
    if (type(days) is not int or not 1<=days<=MAX_DAYS or type(now) not in (int,float)
            or not math.isfinite(now) or not _hash(snapshot.get("snapshot_digest"))
            or snapshot.get("state") not in {"completed","budget_exhausted"}
            or snapshot["binding"]["consent"].get("source_rights_acknowledged") is not True):
        raise ValueError("archive grant requires a terminal witnessed capture")
    members = {}
    for sid,source in snapshot["sources"].items():
        policy=policies.get(sid,{"version":0,"enabled":True})
        if eligible_source(source,policy):
            members[sid]={"text_digest":source["preserved_text_hash"],"policy_version":policy["version"]}
    if not members:
        raise ValueError("no qualified retained source available for archival reuse")
    value={"schema":SCHEMA,"snapshot_digest":snapshot["snapshot_digest"],
           "issued_at":now,"expires_at":now+days*86400,"members":members,
           "history_only":True,"network_authority_expanded":False,"training_permission":False}
    validate_grant(value)
    return value


def validate_grant(grant: object) -> None:
    if (not isinstance(grant,dict) or set(grant)!={"schema","snapshot_digest","issued_at","expires_at",
            "members","history_only","network_authority_expanded","training_permission"}
            or grant["schema"]!=SCHEMA or not _hash(grant["snapshot_digest"])
            or grant["history_only"] is not True or grant["network_authority_expanded"] is not False
            or grant["training_permission"] is not False
            or not isinstance(grant["members"],dict) or not 1<=len(grant["members"])<=MAX_SOURCES):
        raise ValueError("invalid historical grant schema")
    issued,expires=grant["issued_at"],grant["expires_at"]
    if (type(issued) not in (float,int) or type(expires) not in (float,int)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0<=issued<expires<=issued+MAX_DAYS*86400):
        raise ValueError("invalid historical grant time")
    for sid,member in grant["members"].items():
        if (not _hash(sid) or not isinstance(member,dict)
                or set(member)!={"text_digest","policy_version"}
                or not _hash(member["text_digest"])
                or type(member["policy_version"]) is not int
                or not 0<=member["policy_version"]<=2**31-1):
            raise ValueError("invalid historical grant member")


def archive_expiry(grant: dict | None, *, snapshot_digest: str, source: dict,
                   policy: dict, now: float) -> float | None:
    if grant is None:
        return None
    validate_grant(grant)
    if (grant["snapshot_digest"]!=snapshot_digest or not grant["issued_at"]<=now<grant["expires_at"]
            or not policy["enabled"]):
        return None
    member=grant["members"].get(source["source_id"])
    if (member is None or member["policy_version"]!=policy["version"]
            or member["text_digest"]!=source["preserved_text_hash"]
            or not eligible_source(source,policy)):
        return None
    return grant["expires_at"]


def public_grant(grant: dict | None, *, now: float, snapshot_digest: str,
                 sources: dict, policies: dict) -> dict:
    if grant is None:
        return {"active":False,"expires_at":None,"granted_sources":0,"usable_sources":0,
                "history_only":True,"network_authority_expanded":False}
    validate_grant(grant)
    count=sum(archive_expiry(grant,snapshot_digest=snapshot_digest,source=source,
                    policy=policies.get(sid,{"version":0,"enabled":True}),now=now) is not None
              for sid,source in sources.items())
    return {"active":bool(count),"expires_at":grant["expires_at"],"granted_sources":len(grant["members"]),
            "usable_sources":count,"history_only":True,"network_authority_expanded":False}
