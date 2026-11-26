"""Owner-scoped source viewer; no fetch, render, promotion or grant creation.

The catalogue only routes to canonical captures. The existing treasury
inspection authority verifies exact current or historical text. Remote
images/audio/video/PDFs are reference links, not locally captured payloads.
"""
from __future__ import annotations

import hashlib
from uuid import UUID

from core.dragon_game_corpus import GameCorpus, source_url, _id
from core.dragon_game_taxonomy import view_mode
from core.dragon_corpus_runtime import _bounded, _path

MAX_RECORDS=8
MAX_CHARS=4000


def _uuid(value):
    if not isinstance(value,str) or str(UUID(value))!=value:
        raise ValueError("capture session id")
    return value


async def _binding(scope,game,source,session):
    return await _bounded(lambda:GameCorpus(_path(scope=scope)).inspect_capture_binding(
        scope,_id(game),_id(source),_uuid(session)))


async def _session(scope,game,source,session):
    from core.dragon_crawler import crawler_application as app,CrawlerError
    from skeleton.ai.webcrawler.core import canonicalize_url
    binding=await _binding(scope,game,source,session)
    row=await app.sessions.find_one({**scope,"_id":session,"status":{"$nin":["deleted","cancelled"]}},
        max_time_ms=2000)
    if row is None:
        raise CrawlerError("crawler_source_not_found","Bound capture is unavailable.",404)
    # Old bindings must not route to unrelated sessions, even if a catalogue
    # row has been corrupted. Exact seed must still identify the source.
    try:
        seeds=row["request"]["seed_urls"]
        if not isinstance(seeds,list) or len(seeds)!=1 or canonicalize_url(binding["url"])!=canonicalize_url(seeds[0]):
            raise ValueError("capture seed mismatch")
    except (KeyError,TypeError,ValueError) as exc:
        raise CrawlerError("crawler_source_binding","Source and capture binding differ.",409) from exc
    return app,binding,row


async def source_capture_page(scope,game,source,*,before=None,limit=32):
    page=await _bounded(lambda:GameCorpus(_path(scope=scope)).source_captures(scope,game,source,before=before,limit=limit))
    return {**page,"network_executed":False,"wiki_approved":False}


async def capture_documents(scope,game,source,session,*,after=None,limit=MAX_RECORDS):
    """List only permitted snapshot documents, with bounded authority probes.

    A missing/expired/held source exposes no title or body. The next cursor
    belongs to the scanned canonical window, not to the visible subset.
    """
    from core.dragon_crawler import CrawlerError,_plain,_now
    from skeleton.ai.webcrawler.source_instruction_guard import inspect_extracted
    from core.dragon_checkpoint_replica import verify_primary,CheckpointReplicaError
    if type(limit) is not int or not 1<=limit<=MAX_RECORDS:
        raise ValueError("document page limit")
    if after is not None:
        _id(after)
    app,binding,row=await _session(scope,game,source,session)
    try:
        snapshot=_plain(app._custody_snapshot(row))
        verify_primary(snapshot,_plain(row["checkpoint_identity"]))
        if snapshot["binding"]["scope"]!=scope or snapshot["binding"]["request_digest"]!=row["request_digest"]:
            raise ValueError("capture scope mismatch")
        sources=snapshot["sources"]
        if not isinstance(sources,dict) or len(sources)>64:
            raise ValueError("source bound")
        identities=sorted(_id(sid) for sid in sources if after is None or sid>after)
    except (KeyError,ValueError,TypeError,CheckpointReplicaError) as exc:
        raise CrawlerError("crawler_source_integrity","Capture witness unavailable.",409) from exc
    visible=[]
    held=0
    expiries=[]
    for sid in identities[:limit]:
        candidate=sources[sid]
        try:
            if inspect_extracted(candidate["title"],candidate["text"]).held:
                held+=1
                continue
            # The canonical reader also qualifies older runtime captures and
            # enforces grant, source policy, expiry, version and provenance.
            receipt=await app.treasury_passage(scope,session,sid,offset=0,length=1)
            if (receipt["session_version"]!=row["version"]
                    or receipt["snapshot_digest"]!=snapshot["snapshot_digest"]
                    or receipt["preserved_text_hash"]!=candidate["preserved_text_hash"]):
                raise CrawlerError("crawler_source_changed","Capture changed; refresh.",409)
            url=source_url(candidate["canonical_url"])
            expiries.append(receipt["valid_until"])
            visible.append({"capture_source_id":sid,"title":candidate["title"][:512],"url":url,
                "captured_at":receipt["captured_at"],"total_chars":receipt["total_chars"],
                "session_version":receipt["session_version"],"snapshot_digest":receipt["snapshot_digest"],
                "preserved_text_hash":receipt["preserved_text_hash"],"valid_until":receipt["valid_until"],
                "history_only":receipt["history_only"],"legacy_history_only":receipt["legacy_history_only"],
                "representation":"captured_text","view_mode":view_mode(binding["kind"])})
        except CrawlerError as exc:
            if exc.status not in (403,404):
                raise
            held+=1
        except (KeyError,TypeError,ValueError):
            held+=1
    final=await app.sessions.find_one({**scope,"_id":session,"version":row["version"],
        "status":{"$nin":["cancelled","deleted"]}},{"_id":1},max_time_ms=2000)
    now=_now().timestamp()
    if final is None or (expiries and min(expiries)<=now):
        raise CrawlerError("crawler_source_changed","Source authority changed; refresh.",409)
    return {"game_id":game,"catalogue_source_id":source,"session_id":session,
        "documents":visible,"held":held,"scanned":min(limit,len(identities)),
        "next_cursor":identities[limit-1] if len(identities)>limit else None,
        "session_version":row["version"],"as_of_unix":now,
        "earliest_expiry":min(expiries) if expiries else None,
        "network_executed":False,"wiki_approved":False,"model_context_permission":False}


async def read_document(scope,game,source,session,capture_source,*,offset,length,
                        session_version,snapshot_digest,preserved_text_hash,history_only):
    from core.dragon_crawler import CrawlerError,_now
    _id(capture_source);_id(snapshot_digest);_id(preserved_text_hash)
    if (type(offset) is not int or not 0<=offset<=24000 or type(length) is not int
            or not 1<=length<=MAX_CHARS or type(session_version) is not int or session_version<1
            or type(history_only) is not bool):
        raise ValueError("exact view coordinates required")
    app,_,row=await _session(scope,game,source,session)
    if row["version"]!=session_version:
        raise CrawlerError("crawler_source_changed","Capture changed; refresh.",409)
    try:
        from core.dragon_crawler import _plain
        from core.dragon_checkpoint_replica import verify_primary
        snapshot=_plain(row["snapshot"])
        verify_primary(snapshot,_plain(row["checkpoint_identity"]))
        if snapshot["binding"]["scope"]!=scope or snapshot["snapshot_digest"]!=snapshot_digest:
            raise ValueError("snapshot authority differs")
        candidate=snapshot["sources"][capture_source]
        canonical_url=source_url(candidate["canonical_url"])
    except (ValueError,TypeError,KeyError) as exc:
        raise CrawlerError("crawler_source_changed","Capture witness unavailable; refresh.",409) from exc
    receipt=await app.treasury_passage(scope,session,capture_source,offset=offset,length=length)
    if (receipt["session_version"]!=session_version or receipt["snapshot_digest"]!=snapshot_digest
            or receipt["preserved_text_hash"]!=preserved_text_hash
            or receipt["history_only"]!=history_only
            or receipt["span_sha256"]!=hashlib.sha256(receipt["text"].encode("utf-8")).hexdigest()
            or receipt["valid_until"]<=_now().timestamp()):
        raise CrawlerError("crawler_source_changed","Capture changed; refresh.",409)
    # Never render captured HTML, scripts or SVG. Exact plaintext only.
    return {**receipt,"game_id":game,"catalogue_source_id":source,"representation":"captured_text",
            "wiki_approved":False,"network_executed":False,"canonical_url":canonical_url}


async def compare_documents(scope,game,source,left,right):
    """Compare two explicitly pinned passage windows, preserving their authority.

    Return bounded diff lines, never stitch passages from unrelated sources.
    Both versions are revalidated before publication.
    """
    import difflib
    from core.dragon_crawler import CrawlerError,_now
    async def read(pin):
        expected={"session","capture_source","offset","length","session_version",
                  "snapshot_digest","preserved_text_hash","history_only"}
        if not isinstance(pin,dict) or set(pin)!=expected:
            raise ValueError("invalid comparison pin")
        return await read_document(scope,game,source,**pin)
    a=await read(left)
    b=await read(right)
    if a["canonical_url"]!=b["canonical_url"]:
        raise ValueError("comparison requires the same canonical source URL")
    if a["session_id"]==b["session_id"] and a["source_id"]==b["source_id"]:
        raise ValueError("choose distinct retained documents")
    # SequenceMatcher on line chunks is bounded by max 4,000 codepoints each;
    # splitlines retains original text and never interpolates HTML.
    def diff():
        aa=a["text"].splitlines(keepends=True)
        bb=b["text"].splitlines(keepends=True)
        if len(aa)>512 or len(bb)>512:
            raise ValueError("comparison line bound")
        matcher=difflib.SequenceMatcher(None,aa,bb,autojunk=True)
        result=[]
        for tag,i,j,k,l in matcher.get_opcodes():
            result.append({"operation":tag,"left_offset":i,"right_offset":k,
                           "left":"".join(aa[i:j]),"right":"".join(bb[k:l])})
        return result
    changes=await _bounded(diff)
    for pin,prior in ((left,a),(right,b)):
        current=await read(pin)
        if current["span_sha256"]!=prior["span_sha256"] or current["valid_until"]!=prior["valid_until"]:
            raise CrawlerError("crawler_source_changed","Comparison authority changed.",409)
    expiry=min(a["valid_until"],b["valid_until"])
    now=_now().timestamp()
    if expiry<=now:
        raise CrawlerError("crawler_source_changed","Comparison authority expired.",409)
    return {"game_id":game,"catalogue_source_id":source,"changes":changes,
            "left_digest":a["span_sha256"],"right_digest":b["span_sha256"],
            "left_history":a["history_only"],"right_history":b["history_only"],
            "valid_until":expiry,"as_of_unix":now,"partial_windows":True,
            "network_executed":False,"wiki_approved":False,"model_context_permission":False}
