"""Explicit operator-owned, one-shot official API execution.

No general-purpose authenticated crawler, redirect following, automatic retry,
account switching, access-denial recovery, or remote credential input.
Credentials remain in a separate private server file. Prior canonical holds
and the shared origin lease are checked before the request. Failed or uncertain
operations stay held for independent operator review.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from pymongo.errors import DuplicateKeyError
from core.dragon_mongo_receipt import _read_json
from core.dragon_hoarder_bulk import owner_key
from core.dragon_raw_export_custody import RawExportCustody
from skeleton.ai.webcrawler.bound_http import SocketBoundFetcher
from skeleton.ai.webcrawler.adaptive_navigation import access_interstitial_reason
from skeleton.ai.webcrawler.capture_rights import source_capture_rights
from skeleton.ai.webcrawler.http_freshness import observe_http_freshness
from skeleton.ai.webcrawler.source_instruction_guard import inspect_response

PROVIDERS={"github_releases":"api.github.com","github_tags":"api.github.com",
           "huggingface_dataset":"huggingface.co"}
SCHEMA="skeleton.dragon.authorized-api-grant.v1"
MAX_BYTES=2*1024*1024
HEX=re.compile(r"[a-f0-9]{64}\Z")
RESOURCE=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
USER_AGENT="Skeleton-Dragon-Publisher/1.0"


def _digest(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                                      allow_nan=False).encode()).hexdigest()


def validate_grant(grant,*,now):
    fields={"schema","scope","principal_email","provider","resource","expires_at",
            "operation","token_file","raw_store","retain_seconds",
            "publisher_permission_acknowledged","independent_resource_acknowledged",
            "retention_rights_acknowledged","egress_approved"}
    if (not isinstance(grant,dict) or set(grant)!=fields or grant["schema"]!=SCHEMA
            or grant["provider"] not in PROVIDERS or not isinstance(grant["resource"],str)
            or not RESOURCE.fullmatch(grant["resource"])
            or type(grant["expires_at"]) is not int or not now+20<=grant["expires_at"]<=now+900
            or not isinstance(grant["operation"],str) or not 1<=len(grant["operation"])<=128
            or not isinstance(grant["principal_email"],str) or not 3<=len(grant["principal_email"])<=200
            or not isinstance(grant["token_file"],str) or not Path(grant["token_file"]).is_absolute()
            or type(grant["retain_seconds"]) is not int or not 0<=grant["retain_seconds"]<=86400
            or 0<grant["retain_seconds"]<300
            or any(grant[k] is not True for k in ("publisher_permission_acknowledged",
                   "independent_resource_acknowledged","egress_approved"))
            or not isinstance(grant["scope"],dict)):
        raise ValueError("explicit finite official API grant required")
    owner_key(grant["scope"])
    if grant["retain_seconds"]:
        if (grant["retention_rights_acknowledged"] is not True or not isinstance(grant["raw_store"],str)
                or not Path(grant["raw_store"]).is_absolute()):
            raise ValueError("separate raw retention consent required")
    elif grant["raw_store"] is not None or grant["retention_rights_acknowledged"] is not False:
        raise ValueError("unexpected retention authority")
    return dict(grant)


def _raw_candidate(response,token):
    if (response.status!=200 or not response.body or len(response.body)>MAX_BYTES
            or response.headers.get("content-type","").split(";",1)[0].strip().lower()!="application/json"
            or "set-cookie" in response.headers or "content-range" in response.headers
            or token.encode() in response.body
            or access_interstitial_reason(response.status,response.headers,response.body) is not None):
        return False
    try:
        if "public" not in {x.strip().lower() for x in response.headers.get("cache-control","").split(",")}:
            return False
        receipt=observe_http_freshness(response.headers,observed_at=response.fetched_at)
        if receipt.private or receipt.no_store or receipt.sensitive_vary:return False
        if not source_capture_rights(response.headers,response.body,media_type="application/json",
                                     user_agent=USER_AGENT).retain:return False
        observation=inspect_response(response.url,"application/json",response.body)
        if observation is not None and observation.held:return False
        def pairs(items):
            out={}
            for key,value in items:
                if key in out or key.casefold() in {"password","access_token","refresh_token","authorization",
                    "api_key","client_secret","private_key","session_cookie","email","token"}:
                    raise ValueError("sensitive or ambiguous JSON field")
                out[key]=value
            return out
        def nonfinite(_):raise ValueError("nonfinite JSON")
        value=json.loads(response.body,object_pairs_hook=pairs,parse_constant=nonfinite)
        return isinstance(value,(dict,list))
    except (ValueError,TypeError,UnicodeError,RecursionError):
        return False


def api_record_id(scope,host):
    return "dragon-official-api:"+_digest([owner_key(scope),host])


async def assert_no_api_restriction(app,scope,hosts):
    """Canonical crawler dispatch honors held or uncertain official API calls."""
    from core.dragon_crawler import CrawlerError
    ids=[api_record_id(scope,h) for h in sorted(set(hosts)&set(PROVIDERS.values()))]
    if not ids:return
    found=await app._acquisition_store().find_one(
        {"_id":{"$in":ids},"kind":"dragon_official_api_v1",
         "state":{"$nin":["ready","completed"]}},{"_id":1},max_time_ms=2000)
    if found is not None:
        raise CrawlerError("crawler_connector_held","Official API restriction requires independent review.",409)


async def execute(app,grant_path,*,expected_grant_digest):
    from core.dragon_crawler import CrawlerError
    grant_path=Path(grant_path)
    if not isinstance(expected_grant_digest,str) or not HEX.fullmatch(expected_grant_digest):
        raise ValueError("exact private grant digest required")
    grant=validate_grant(_read_json(grant_path),now=int(time.time()))
    if _digest(grant)!=expected_grant_digest:raise ValueError("grant digest changed")
    # Explicit direct egress profile only; do not silently ignore an operator
    # proxy configuration. Sites with required proxies remain held.
    if any(os.getenv(k,"").strip() for k in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY",
          "http_proxy","https_proxy","all_proxy","SKL_CRAWLER_PROXY_URL","SKL_DRAGON_PROXY_URL")):
        raise ValueError("configured proxy requires independent API egress integration")
    scope=grant["scope"];host=PROVIDERS[grant["provider"]]
    async def check():
        current=validate_grant(_read_json(grant_path),now=int(time.time()))
        if _digest(current)!=expected_grant_digest:raise ValueError("current grant changed")
        await app._grant_principal(scope,{"principal_email":grant["principal_email"].strip().lower()})
        report=await app.acquisition_hold_catalog(scope,peer_hosts=(host,),exclude_session="official-api")
        if report["capacity_reached"] or report["excluded_sessions"] or report["holds"]:
            raise CrawlerError("crawler_connector_held","Existing origin restriction requires independent review.",409)

    await check()
    store=app._acquisition_store()
    # One durable record per owner and fixed API host. Uncertain/denied
    # calls are not repeatable, even with a new operation or resource.
    rid=api_record_id(scope,host)
    token=uuid4().hex
    try:
        await store.insert_one({"_id":rid,"kind":"dragon_official_api_v1",
            "state":"ready","grant_digest":expected_grant_digest})
    except DuplicateKeyError:
        pass
    row={"request":{"allowed_hosts":[host]}}
    from pymongo import ReturnDocument
    try:
        await app._claim_acquisition_stripes(row,token)
        await check()
        await app._assert_acquisition_stripes(row,token)
        claimed=await store.find_one_and_update({"_id":rid,"kind":"dragon_official_api_v1",
            "$or":[{"state":"ready","grant_digest":expected_grant_digest},
                   {"state":"completed","grant_digest":{"$ne":expected_grant_digest}}]},
            {"$set":{"state":"running","grant_digest":expected_grant_digest,"api_attempt":token}},
            return_document=ReturnDocument.AFTER)
        if claimed is None or claimed.get("api_attempt")!=token:
            raise CrawlerError("crawler_connector_held","API operation already attempted or requires review.",409)
        try:
            await check()
            await app._assert_acquisition_stripes(row,token)
            credential=_read_json(Path(grant["token_file"]))
            if not isinstance(credential,dict) or set(credential)!={"token"}:
                raise ValueError("private credential schema")
            secret=credential["token"]
            fetcher=SocketBoundFetcher(timeout_seconds=10,allowed_hosts=frozenset({host}))
            task=asyncio.create_task(asyncio.to_thread(fetcher.fetch_publisher_api_once,
                    grant["provider"],grant["resource"],token=secret,user_agent=USER_AGENT,max_bytes=MAX_BYTES))
            try:response=await asyncio.shield(task)
            except asyncio.CancelledError:
                # Never release ownership while the transport is draining.
                try:await asyncio.shield(task)
                except Exception:pass
                raise
            status=int(response.status)
            if status!=200 or access_interstitial_reason(status,response.headers,response.body) is not None:
                raise ValueError("official API response held")
            await check()
            raw_sha=hashlib.sha256(response.body).hexdigest()
            retained=None
            if grant["retain_seconds"] and _raw_candidate(response,secret):
                # Retention checks predate this write and remain independent
                # of the credential. The body is never returned to the API CLI.
                def retain():
                    return RawExportCustody(Path(grant["raw_store"])).retain_response(
                        scope,response.body,expected_sha=raw_sha,operation="api:"+expected_grant_digest,
                        retention_seconds=grant["retain_seconds"],rights_acknowledged=True)
                retention_task=asyncio.create_task(asyncio.to_thread(retain))
                try:retained=await asyncio.shield(retention_task)
                except asyncio.CancelledError:
                    try:await asyncio.shield(retention_task)
                    except Exception:pass
                    raise
            result={"status":status,"raw_body_sha256":raw_sha,"body_bytes":len(response.body),
                    "retention":retained,"raw_bytes_retained":retained is not None,
                    "network_executed":True,"license_verified":False,"training_allowed":False}
            settled=await store.update_one({"_id":rid,"state":"running","api_attempt":token},
                  {"$set":{"state":"completed","receipt":result},"$unset":{"api_attempt":""}})
            if settled.modified_count!=1:raise RuntimeError("API settlement changed")
            return result
        except BaseException:
            # Failed, cancelled or ambiguous I/O must never turn into a retry.
            await store.update_one({"_id":rid,"state":"running","api_attempt":token},
                  {"$set":{"state":"held"},"$unset":{"api_attempt":""}})
            raise
    except CrawlerError:raise
    except Exception:
        raise CrawlerError("crawler_connector_held","Official API execution requires independent review.",409) from None
    finally:
        await app._release_worker_credits(token)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grant",type=Path,required=True)
    p.add_argument("--grant-digest",required=True)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    if not args.execute:p.error("explicit official API execution acknowledgement required")
    from core.dragon_crawler import crawler_application
    try:
        result=asyncio.run(execute(crawler_application,args.grant,expected_grant_digest=args.grant_digest))
    except Exception:
        p.exit(2,"Official API operation held; review private configuration and authorized service state.\n")
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__":raise SystemExit(main())
