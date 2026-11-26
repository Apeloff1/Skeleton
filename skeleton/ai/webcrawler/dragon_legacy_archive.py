"""Conservative read-only compatibility inspection of witnessed terminal captures.

This verifier is intentionally narrower than CrawlRun.from_snapshot. It
cannot create a run, synthesize an old checkpoint, change its code digest,
execute a frontier, issue new capture rights, or assert modern acquisition
qualification. Legacy text becomes history-only after an explicit new
archive grant and only if this exact source contract independently verifies.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from .core import CrawlPolicy, canonicalize_url
from .duplicate_custody import validate_aliases
from .http_freshness import verify_freshness_receipt
from .source_instruction_guard import inspect_extracted

SCHEMA="skeleton.ai.dragon.crawl_run.v1"
PROJECTION_SCHEMA="skeleton.dragon.legacy-terminal-inspection.v1"
MAX_SOURCES=64
MAX_BYTES=4*1024*1024
_HEX=re.compile(r"[a-f0-9]{64}\Z")


def digest(value)->str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def _hex(value)->bool:
    return isinstance(value,str) and _HEX.fullmatch(value) is not None


def inspect_terminal(snapshot:dict,*,scope:dict,request_digest:str,consent:dict,now:float)->dict:
    """No transport, file reads, subprocess, model context or legacy code."""
    if (not isinstance(snapshot,dict) or snapshot.get("schema_version")!=SCHEMA
            or snapshot.get("state") not in {"completed","budget_exhausted"}
            or snapshot.get("pending_dispatch") is not None
            or not _hex(snapshot.get("snapshot_digest"))
            or type(now) not in (float,int) or not math.isfinite(now)
            or len(json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode())>MAX_BYTES):
        raise ValueError("legacy snapshot is not an admitted terminal record")
    body={k:v for k,v in snapshot.items() if k!="snapshot_digest"}
    if digest(body)!=snapshot["snapshot_digest"]:
        raise ValueError("legacy snapshot digest mismatch")
    binding=snapshot.get("binding")
    if (not isinstance(binding,dict) or set(binding)!={"request","request_digest","code_digest","scope","consent"}
            or binding["scope"]!=scope or binding["consent"]!=consent
            or binding["request_digest"]!=request_digest or digest(binding["request"])!=request_digest
            or not _hex(binding["code_digest"]) or snapshot.get("run_id")!=digest(binding)
            or consent.get("capture_acknowledged") is not True or consent.get("source_rights_acknowledged") is not True
            or not _hex(consent.get("consent_id")) or type(consent.get("expires_at")) not in (int,float)
            or not math.isfinite(consent["expires_at"])):
        raise ValueError("legacy checkpoint scope or consent mismatch")
    request=binding["request"]
    hosts=request.get("allowed_hosts")
    if (not isinstance(hosts,list) or not 1<=len(hosts)<=16
            or not all(isinstance(h,str) and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?",h)
                       and ".." not in h and len(h)<=253 for h in hosts)):
        raise ValueError("legacy allowlist cannot be verified")
    policy=CrawlPolicy(allowed_hosts=tuple(hosts))
    def admit(url):
        if not isinstance(url,str) or len(url.encode())>4096 or canonicalize_url(url)!=url or not policy.admits(url):
            raise ValueError("legacy source URL outside original authority")
        return url
    seeds=request.get("seed_urls")
    if not isinstance(seeds,list) or not 1<=len(seeds)<=16:
        raise ValueError("legacy source root missing")
    for seed in seeds:
        admit(seed)
    sources=snapshot.get("sources")
    sequence=snapshot.get("sequence")
    usage=snapshot.get("usage")
    docs=request.get("max_documents")
    requests=request.get("max_requests")
    if (type(sequence) is not int or not 0<=sequence<=10000 or not isinstance(sources,dict)
            or type(docs) is not int or not 1<=docs<=64 or type(requests) is not int or not 1<=requests<=128
            or not isinstance(usage,dict) or type(usage.get("requests")) is not int or not 0<=usage["requests"]<=requests
            or type(usage.get("documents")) is not int or usage["documents"]!=len(sources)
            or len(sources)>docs or len(sources)>usage["requests"]):
        raise ValueError("legacy capture budget mismatch")
    events=snapshot.get("events")
    if not isinstance(events,list) or len(events)>64:
        raise ValueError("legacy event receipt unavailable")
    captured={}
    event_by_sequence={}
    last_sequence=0
    for event in events:
        if (not isinstance(event,dict) or type(event.get("sequence")) is not int
                or not last_sequence<event["sequence"]<=sequence
                or not _hex(event.get("event_digest")) or digest({k:v for k,v in event.items() if k!="event_digest"})!=event["event_digest"]):
            raise ValueError("legacy event integrity mismatch")
        last_sequence=event["sequence"]
        event_by_sequence[last_sequence]=event
        if event.get("kind")=="captured":
            sid=event.get("source_id")
            if not _hex(sid) or sid not in sources or sid in captured:
                raise ValueError("legacy capture event identity mismatch")
            captured[sid]=(event["sequence"],admit(event.get("url")),None)
    # Older ring entries may have been compacted. Require a second exact
    # acquisition receipt when present; no guessed event restoration.
    measures=snapshot.get("acquisition_measurements",[])
    if not isinstance(measures,list) or len(measures)>128:
        raise ValueError("legacy acquisition receipt bound")
    measured=set()
    for item in measures:
        if not isinstance(item,dict):
            raise ValueError("malformed legacy acquisition observation")
        sid=item.get("source_id")
        seq=item.get("event_sequence")
        if sid is not None:
            if (not _hex(sid) or sid not in sources or sid in measured or item.get("kind")!="captured"
                    or type(seq) is not int or not 1<=seq<=sequence
                    or type(item.get("status")) is not int or not 200<=item["status"]<300
                    or item.get("host")!=urlsplit(sources[sid]["fetched_url"]).hostname):
                raise ValueError("legacy measurement does not prove a capture")
            measured.add(sid)
            event=event_by_sequence.get(seq)
            if event is not None and (event.get("kind")!="captured" or event.get("source_id")!=sid):
                raise ValueError("legacy measurement contradicts witnessed event")
            if sid in captured and captured[sid][0]!=seq:
                raise ValueError("legacy capture sequence conflicts")
            # An older compacted event may be joined to its exact witnessed
            # acquisition receipt, never to an arbitrary status observation.
            captured.setdefault(sid,(seq,None,item["host"]))
    verified={}
    for sid,source in sources.items():
        if not _hex(sid) or not isinstance(source,dict) or sid!=source.get("source_id"):
            raise ValueError("legacy source identity unavailable")
        text=source.get("text")
        title=source.get("title")
        stamp=source.get("fetched_at")
        provenance=source.get("provenance")
        if (not isinstance(text,str) or len(text.encode("utf-8"))>24000
                or not isinstance(title,str) or len(title.encode("utf-8"))>4000
                or type(stamp) not in (float,int) or not math.isfinite(stamp) or not 0<=stamp<=min(now+300,consent["expires_at"]+1)
                or not all(_hex(source.get(k)) for k in ("content_hash","raw_body_hash","preserved_text_hash"))
                or source["preserved_text_hash"]!=hashlib.sha256(text.encode("utf-8")).hexdigest()
                or type(source.get("text_truncated")) is not bool
                or not source["text_truncated"] and source["content_hash"]!=source["preserved_text_hash"]
                or source.get("review_state")!="unreviewed" or not isinstance(provenance,dict)
                or provenance.get("schema")!="skeleton.ai.crawl.provenance.v1"
                or provenance.get("binding_digest")!=digest(binding)
                or provenance.get("consent_id")!=consent["consent_id"]
                or provenance.get("source_status")!="unreviewed_external_capture"
                or provenance.get("training_permission") is not False
                or provenance.get("raw_bytes_retained") is not False
                or type(provenance.get("status")) is not int or not 200<=provenance["status"]<300
                or source.get("content_type") not in policy.allowed_content_types
                or sid!=digest({"url":source.get("canonical_url"),"content_hash":source["content_hash"]})):
            raise ValueError("legacy source preservation mismatch")
        for key in ("canonical_url","fetched_url","content_hash","fetched_at","raw_body_hash"):
            if provenance.get(key)!=source.get(key):
                raise ValueError("legacy acquisition identity mismatch")
        for key in ("canonical_url","fetched_url"):
            admit(source[key])
        capture=provenance.get("capture_sequence")
        evidence=captured.get(sid)
        if (type(capture) is not int or evidence is None or evidence[0]!=capture
                or evidence[1] is not None and evidence[1]!=source["fetched_url"]
                or evidence[2] is not None and evidence[2]!=urlsplit(source["fetched_url"]).hostname):
            raise ValueError("legacy exact capture event absent or conflicting")
        receipt=provenance.get("http_freshness")
        if receipt is not None and not verify_freshness_receipt(receipt,observed_at=stamp):
            raise ValueError("legacy HTTP metadata malformed")
        # Current security check, never reinterpret or follow page text.
        if inspect_extracted(title,text).held:
            # Held records are not migrated or supplied as usable archive.
            continue
        verified[sid]=source
    aliases=snapshot.get("source_aliases",[])
    if aliases:
        validate_aliases(aliases,sources=sources,seen=snapshot.get("seen",[]),
                         requests=usage["requests"],sequence=sequence,admit=admit)
    return {"schema":PROJECTION_SCHEMA,"snapshot_digest":snapshot["snapshot_digest"],
            "historical_runtime_digest":binding["code_digest"],"verified_source_ids":sorted(verified),
            "excluded_sources":len(sources)-len(verified),"history_only":True,
            "execution_authorized":False,"network_authority_expanded":False,
            "model_context_permission":False,"training_permission":False}
