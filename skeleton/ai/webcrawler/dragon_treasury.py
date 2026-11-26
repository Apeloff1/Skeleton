"""Hoarder: version-aware, bounded, owner-scoped archive retrieval.

Source snapshots are the durable records. This index is rebuilt from witnessed
observations; no archive copy, raw payload, model training or new source grant
is created. Expired/withdrawn versions remain metadata-only blockers of stale
promotion. 'Current' means latest observed in the selected corpus, not live truth.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from .dragon_companion import _lexemes, _signature, _similarity
from .dragon_revisit_model import ChangeSample, infer_revisit
from .dragon_temporal_selection import family_identity, select_candidates
from .dragon_temporal_query import MAX_QUERY_SLOTS, rank_admission

SCHEMA = "skeleton.dragon.treasury.v1"
PARSER = "retained-text-sections-v3"
MAX_SESSIONS = 32
MAX_OBSERVATIONS = 2048
MAX_INDEXED = 256
MAX_SECTIONS = 32
MAX_TERMS = 2048
MAX_RESULTS = 24
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_MODES = frozenset({"current_only", "historic_only", "all_revisions", "timeline", "compare", "at_time"})
_STAGES = ("hatchling", "scout", "scholar", "pathfinder", "archivist", "hoarder")
_THRESHOLDS = (0, 120, 300, 550, 800, 1150, 1500)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Observation:
    session_id: str
    source_id: str
    url: str
    content_hash: str
    captured_at: float
    text: str | None
    usable_until: float | None
    media: str
    variant: str = ""
    advisory_due: float | None = None
    complete_text: bool = True
    refresh_allowed: bool = False
    archive_only: bool = False


@dataclass(frozen=True)
class ParsedVersion:
    terms: Counter
    section_hashes: tuple[str, ...]
    signature: frozenset[int]
    numbers: tuple[str, ...]
    digest: str


def term_key(token: str) -> str:
    """Fixed-width lexical fingerprint, not encryption or anonymization."""
    return hashlib.blake2b(token.encode("utf-8"),digest_size=16,person=b"dragon-term-v3").hexdigest()


def materialized_digest(*, text_hash: str, terms: Counter, sections: tuple,
                        signature: frozenset, numbers: tuple) -> str:
    return _digest({"parser":PARSER,"text_sha256":text_hash,"terms":sorted(terms.items()),
                    "section_hashes":sections,"signature":sorted(signature),"numeric_hashes":numbers})


def parse_retained_text(text: str) -> ParsedVersion:
    """Independent bounded lexical reparse, never a raw HTML/network reparse."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 24000:
        raise ValueError("retained text exceeds parser envelope")
    words = _lexemes(text)[:MAX_TERMS]
    # Stable block geometry for change localization; no attacker-controlled
    # markup is executed and no raw source vocabulary is returned to caller.
    # Content-defined landmarks survive insertions better than fixed offsets.
    # A hard tail cap preserves the complete remaining bounded token range.
    blocks, start = [], 0
    for i,word in enumerate(words):
        width=i-start+1
        if len(blocks)==MAX_SECTIONS-1:
            break
        anchor=width>=32 and int.from_bytes(hashlib.blake2s(word.encode(),digest_size=2).digest(),"big")%32==0
        if anchor or width>=128:
            blocks.append(words[start:i+1]);start=i+1
    if start<len(words):
        blocks.append(words[start:])
    hashes = tuple(_digest(block) for block in blocks)
    # Ordered signed/decimal/percentage tokens preserve swaps and repeats.
    # Do not publish numbers or context in the archive projection.
    numbers = tuple(m.group() for m in re.finditer(r"(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:%|‰)?",text[:24000]))[:MAX_TERMS]
    terms = Counter(term_key(word) for word in words)
    signature = _signature(text)
    numeric_hashes = tuple(term_key(number) for number in numbers)
    digest = materialized_digest(text_hash=hashlib.sha256(text.encode()).hexdigest(),terms=terms,
                                  sections=hashes,signature=signature,numbers=numeric_hashes)
    return ParsedVersion(terms,hashes,signature,numeric_hashes,digest)


def _validate(row: Observation, *, now: float) -> None:
    if (not isinstance(row, Observation) or not isinstance(row.session_id, str)
            or not 1 <= len(row.session_id) <= 128
            or not isinstance(row.source_id, str) or not _HEX.fullmatch(row.source_id)
            or not isinstance(row.content_hash, str) or not _HEX.fullmatch(row.content_hash)
            or not isinstance(row.url, str) or not 1 <= len(row.url.encode()) <= 4096
            or not isinstance(row.media, str) or len(row.media) > 256
            or not isinstance(row.variant, str) or len(row.variant) > 128
            or type(row.complete_text) is not bool or type(row.refresh_allowed) is not bool
            or type(row.archive_only) is not bool or (row.archive_only and row.text is None)
            or type(row.captured_at) not in (int,float) or not math.isfinite(row.captured_at)
            or not 0 <= row.captured_at <= now+300):
        raise ValueError("invalid archive observation")
    parsed = urlsplit(row.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid archive family identity")
    if (row.text is None) != (row.usable_until is None):
        raise ValueError("metadata-only archive observation has invalid access state")
    if row.text is not None and (
        not isinstance(row.text, str) or len(row.text.encode()) > 24000
        or type(row.usable_until) not in (int,float) or not math.isfinite(row.usable_until)
        or row.usable_until <= now
    ):
        raise ValueError("archive text is outside current source permission")
    if row.advisory_due is not None and (
        type(row.advisory_due) not in (int,float) or not math.isfinite(row.advisory_due)
        or not row.captured_at <= row.advisory_due <= row.captured_at + 604801
    ):
        raise ValueError("invalid advisory revisit clock")


def _delta(before: ParsedVersion | None, after: ParsedVersion | None,
           *, complete: bool) -> dict:
    if before is None or after is None or not complete:
        return {"kind": "changed_unclassified", "similarity": None, "added_terms": None,
                "removed_terms": None, "changed_sections": None, "numeric_change": None}
    a,b = set(before.terms), set(after.terms)
    similarity = _similarity(before.signature, after.signature)
    if not before.signature or not after.signature:
        similarity = len(a&b)/max(1,len(a|b))
    numeric = before.numbers != after.numbers
    common=sum(match.size for match in SequenceMatcher(None,before.section_hashes,after.section_hashes,autojunk=False).get_matching_blocks())
    kind = "minor_update" if similarity >= .85 and not numeric else (
        "substantive_update" if similarity >= .35 or numeric else "major_rewrite")
    return {"kind":kind,"similarity":round(similarity,6),"added_terms":len(b-a),
            "removed_terms":len(a-b),"changed_sections":len(before.section_hashes)+len(after.section_hashes)-2*common,
            "numeric_change":numeric}


def _revisit(rows: list[Observation], now: float) -> dict:
    latest = rows[-1]
    # Higher-impact families are assigned a smaller target stale risk,
    # while short repeated observations cannot manufacture confidence.
    unique = len({row.content_hash for row in rows})
    priority = .4 + .35 * min(1., (unique-1)/4) + .25 * int(latest.text is not None)
    return infer_revisit(
        [ChangeSample(row.captured_at,row.content_hash) for row in rows],
        now=now, publisher_due=latest.advisory_due,
        allowed=latest.refresh_allowed, priority_value=priority,
        estimated_bytes=max(1,len(latest.text.encode()) if latest.text is not None else 65536),
    )


def progression(growth: int, stewardship: int, *, qualified: bool) -> dict:
    if (type(growth) is not int or not 0<=growth<=1000
            or type(stewardship) is not int or not 0<=stewardship<=500
            or type(qualified) is not bool):
        raise ValueError("invalid evolution inputs")
    total = growth + stewardship
    # Archive credit cannot skip the pre-existing discovery requirement.
    effective = total if growth>=800 and qualified else min(growth,1149)
    stage = sum(effective >= threshold for threshold in _THRESHOLDS[1:-1])
    lo, hi = _THRESHOLDS[stage], _THRESHOLDS[stage+1]
    fraction = min(1., max(0., (effective-lo)/(hi-lo)))
    level = min(stage*10+10,stage*10+1+int(fraction*10))
    return {"form":_STAGES[stage],"stage":stage,"level":level,
            "expedition_growth":growth,"treasury_growth":stewardship,
            "total_evolution":total,"effective_evolution":effective,
            "stage_progress":round(fraction,6),"hoarder_qualified":qualified,
            "next_threshold":hi if stage<5 else None}


def build_treasury(observations: list[Observation], *, as_of: float, growth: int,
                   mode: str = "current_only", query: str = "", family: str | None = None,
                   candidate_limit_reached: bool = False, excluded_sessions: int = 0,
                   alias_blockers: list[dict] | None = None,
                   materialized: dict[tuple[str,str],ParsedVersion] | None = None,
                   cursor: str | None = None, observed_before: float | None = None,
                   left: str | None = None, right: str | None = None,
                   catalogue_scope:tuple[str,...]|None=None) -> dict:
    if (not isinstance(observations,list) or len(observations)>MAX_OBSERVATIONS
            or type(as_of) not in (int,float) or not math.isfinite(as_of)
            or mode not in _MODES or not isinstance(query,str) or len(query.encode())>1024
            or family is not None and (not isinstance(family,str) or not _HEX.fullmatch(family))
            or cursor is not None and (not isinstance(cursor,str) or not re.fullmatch(r"[0-9a-f]{64}:[0-9]{1,4}",cursor))
            or (mode=="at_time") != (observed_before is not None)
            or observed_before is not None and (type(observed_before) not in (float,int) or not math.isfinite(observed_before) or not 0<=observed_before<=as_of)
            or (left is None)!=(right is None)
            or left is not None and (mode!="compare" or family is None or left==right
                or not isinstance(left,str) or not _HEX.fullmatch(left) or not isinstance(right,str) or not _HEX.fullmatch(right))
            or type(candidate_limit_reached) is not bool
            or type(excluded_sessions) is not int or not 0<=excluded_sessions<=MAX_SESSIONS):
        raise ValueError("invalid treasury query envelope")
    if catalogue_scope is not None:
        from .dragon_treasury_vault import selected_ids
        if (not isinstance(catalogue_scope,tuple) or tuple(selected_ids(list(catalogue_scope)))!=catalogue_scope
                or mode=="current_only" or not candidate_limit_reached or growth!=0
                or any(not isinstance(row,Observation) or row.session_id not in catalogue_scope
                       or row.refresh_allowed or (row.text is not None and not row.archive_only)
                       for row in observations)):
            raise ValueError("invalid history-only catalogue window")
    aliases = alias_blockers if alias_blockers is not None else []
    if not isinstance(aliases,list) or len(aliases)>4096:
        raise ValueError("archive alias blocker capacity exceeded")
    blockers = defaultdict(list)
    for alias in aliases:
        if (not isinstance(alias,dict) or set(alias)!={"url","captured_at","content_hash"}
                or not isinstance(alias["url"],str) or len(alias["url"].encode())>4096
                or type(alias["captured_at"]) not in (float,int) or not math.isfinite(alias["captured_at"])
                or not 0<=alias["captured_at"]<=as_of+300
                or not isinstance(alias["content_hash"],str) or not _HEX.fullmatch(alias["content_hash"])):
            raise ValueError("invalid archive alias receipt")
        if observed_before is None or alias["captured_at"]<=observed_before:
            blockers[alias["url"]].append(alias)
    grouped = defaultdict(list)
    identities = set()
    for row in observations:
        _validate(row,now=as_of)
        identity = row.session_id,row.source_id
        if identity in identities:
            raise ValueError("duplicate archive identity")
        identities.add(identity)
        # Exact fetched URL and representation boundary: never merge different
        # routes by a publisher canonical tag, title, redirect or fuzzy match.
        if observed_before is None or row.captured_at<=observed_before:
            grouped[family_identity(row)].append(row)
    if len({x.session_id for x in observations})>MAX_SESSIONS:
        raise ValueError("archive expedition capacity exceeded")
    selected_observations=[row for rows in grouped.values() for row in rows]
    ordered = [row for row in selected_observations if row.text is not None]
    baseline=select_candidates(grouped,budget=MAX_INDEXED,family=family,observed_before=observed_before,
                               comparison=(left,right) if left is not None else None)
    # On a capped corpus, use a bounded first-stage search over exact,
    # permitted representatives in the requested plane. Reserve the rest
    # of the structural capacity for stable temporal coverage. On a fully
    # admitted corpus the original partition is independent of query/mode.
    admission=None
    indexed=baseline
    if len(ordered)>MAX_INDEXED and query.strip() and mode not in {"compare","timeline"}:
        slots=min(MAX_QUERY_SLOTS,max(1,MAX_INDEXED*3//4))
        admission=rank_admission(grouped,mode=mode,family=family,blockers=blockers,
                                 query=query,lexemes=_lexemes,slots=slots)
        selected={(row.session_id,row.source_id):row for row in admission.candidates}
        for row in baseline:
            if len(selected)>=MAX_INDEXED:
                break
            selected.setdefault((row.session_id,row.source_id),row)
        indexed=list(selected.values())
    # Exact retained-text memoization; full-source hash alone is not a
    # sufficient key when a source was truncated. No cross-request cache.
    index, memo = {}, {}
    cache = materialized or {}
    if not isinstance(cache,dict) or len(cache)>MAX_OBSERVATIONS:
        raise ValueError("materialized index exceeds owner envelope")
    materialized_hits=0
    for row in indexed:
        key = hashlib.sha256(row.text.encode("utf-8")).hexdigest()
        if key not in memo:
            saved=cache.get((row.session_id,row.source_id))
            if isinstance(saved,ParsedVersion) and saved.digest==materialized_digest(
                    text_hash=key,terms=saved.terms,sections=saved.section_hashes,
                    signature=saved.signature,numbers=saved.numbers):
                memo[key]=saved
                materialized_hits+=1
            else:
                memo[key] = parse_retained_text(row.text)
        index[row.session_id,row.source_id] = memo[key]
    capped = candidate_limit_reached or len(ordered)>MAX_INDEXED
    families, revisions, parse_rows = [], [], {}
    comparisons = {}
    changed_families = changes = rollbacks = revalidated = blocked_current = alias_held = 0
    verified_transitions = verified_families = 0
    family_origins = {}
    version_content = {}
    for fid, rows in sorted(grouped.items()):
        rows.sort(key=lambda x:(x.captured_at,x.session_id,x.source_id))
        family_origins[fid] = urlsplit(rows[0].url).hostname
        ambiguous_times = {stamp for stamp,count in Counter(x.captured_at for x in rows).items()
                           if count>1 and len({x.content_hash for x in rows if x.captured_at==stamp})>1}
        versions = []
        version_hashes = []
        prior = None
        observed_hashes = set()
        previous_hash = None
        for row in rows:
            key = row.session_id,row.source_id
            parsed = index.get(key)
            if versions and row.content_hash == previous_hash:
                # Re-observation extends the observation interval but does
                # not create another revision or novelty reward.
                latest = versions[-1]
                if row.captured_at > latest["last_seen"] and parsed is not None:
                    revalidated += int(latest["reobservations"] == 0)
                latest["last_seen"] = row.captured_at
                latest["reobservations"] += 1
                latest["latest_access"] = parsed is not None and not row.archive_only
                # A later held duplicate cannot grant access or erase an
                # earlier independently permitted historic representative.
                if parsed is not None:
                    latest.update(session_id=row.session_id,source_id=row.source_id,
                                  indexed=True,metadata_only=False,archive_only=row.archive_only,
                                  indexed_capture_at=row.captured_at)
                    parse_rows[latest["revision_id"]] = parsed
                prior = row
                continue
            delta = ({"kind":"initial","similarity":None,"added_terms":None,"removed_terms":None,
                      "changed_sections":None,"numeric_change":None} if prior is None else
                     _delta(index.get((prior.session_id,prior.source_id)),parsed,
                            complete=prior.complete_text and row.complete_text))
            if prior is not None and (row.captured_at in ambiguous_times or prior.captured_at in ambiguous_times):
                delta = _delta(None,None,complete=False)
            elif row.content_hash in observed_hashes:
                delta["kind"]="rollback"
                rollbacks += 1
            observed_hashes.add(row.content_hash)
            parent = versions[-1]["revision_id"] if versions else None
            rid = _digest({"family":fid,"parent":parent,"first_session":row.session_id,
                           "first_source":row.source_id,"content":row.content_hash})
            version = {"revision_id":rid,"family_id":fid,"previous_revision_id":parent,
                       "session_id":row.session_id,"source_id":row.source_id,
                       "first_seen":row.captured_at,"last_seen":row.captured_at,
                       "reobservations":0,"indexed":parsed is not None,"metadata_only":parsed is None,
                       "archive_only":row.archive_only,"latest_access":parsed is not None and not row.archive_only,
                       "indexed_capture_at":row.captured_at if parsed is not None else None,
                       "delta":delta}
            versions.append(version)
            version_content[rid]=row.content_hash
            version_hashes.append(row.content_hash)
            parse_rows[rid]=parsed
            prior=row
            previous_hash=row.content_hash
        if len(versions)>1:
            changed_families+=1
            changes+=len(versions)-1
        latest=versions[-1]
        # Simultaneous incompatible payloads or a held latest observation
        # must not cause an older readable version to masquerade as current.
        tied = len({x.content_hash for x in rows if x.captured_at==rows[-1].captured_at})>1
        if tied:
            latest["indexed"]=False
            latest["metadata_only"]=True
            latest["latest_access"]=False
            parse_rows[latest["revision_id"]]=None
        alias_conflict = any(a["captured_at"]>=rows[-1].captured_at and
                             a["content_hash"]!=rows[-1].content_hash for a in blockers.get(rows[-1].url,()))
        alias_held += int(alias_conflict)
        current_available=latest["indexed"] and latest["latest_access"] and not alias_conflict and observed_before is None
        # Keep an earlier authorized payload available only to the historic
        # plane when a newer variant-unknown receipt contradicts it.
        blocked_current+=int(not current_available)
        unique_edges=set()
        for k in range(1,len(versions)):
            a,b=versions[k-1],versions[k]
            if (a["indexed"] and b["indexed"] and a["last_seen"]<b["first_seen"]
                    and b["delta"]["kind"]!="changed_unclassified" and b["first_seen"] not in ambiguous_times):
                unique_edges.add(tuple(sorted((version_hashes[k-1],version_hashes[k]))))
        verified_transitions+=len(unique_edges)
        verified_families+=int(bool(unique_edges))
        for v in versions:
            v["plane"]="current" if v is latest and current_available else "historic"
            v.pop("latest_access",None)
            if not v["indexed"]:
                v["indexed_capture_at"]=None
            v["latest_observed"]=v is latest
            v["source_id"]=v["source_id"] if v["indexed"] else None
            v["session_id"]=v["session_id"] if v["indexed"] else None
            v["projection_digest"]=parse_rows[v["revision_id"]].digest if v["indexed"] else None
        revisions.extend(versions)
        families.append({"family_id":fid,"revision_count":len(versions),
                         "current_revision":latest["revision_id"],"first_seen":versions[0]["first_seen"],
                         "last_seen":latest["last_seen"],"current_indexed":current_available,
                         "simultaneous_conflict":tied,"alias_conflict":alias_conflict,"revisit":_revisit(rows,as_of),
                         "refresh_url":rows[-1].url if rows[-1].refresh_allowed and not tied and observed_before is None else None})
        if observed_before is not None:
            families[-1]["revisit"]["ready_for_review"]=False
        if alias_conflict:
            # The ambiguous receipt cannot itself authorize work. A new grant
            # from the previously admitted URL can resolve it after a floor.
            hold = max(a["captured_at"] for a in blockers[rows[-1].url])+3600
            revisit=families[-1]["revisit"]
            revisit["due_at"]=max(revisit["due_at"],hold)
            revisit["interval_seconds"]=revisit["due_at"]-rows[-1].captured_at
            revisit["ready_for_review"]=bool(observed_before is None and rows[-1].refresh_allowed and not tied and as_of>=revisit["due_at"])
        if len(versions)>1 and not tied and not alias_conflict and latest["delta"]["kind"]!="changed_unclassified":
            comparisons[fid]={"current":latest,"previous":versions[-2],"delta":latest["delta"]}
    # Explicitly separate index corpora before computing document frequency.
    # Historic pages cannot leak into current-only scoring via IDF.
    if mode=="at_time":
        # Build the lineage from observations at/before the requested cutoff.
        # All results remain history-plane evidence, not present-day context.
        held_by_family={f["family_id"] for f in families if f["simultaneous_conflict"] or f["alias_conflict"]}
        allowed=[v for v in revisions if v["indexed"] and v["latest_observed"]
                 and v["family_id"] not in held_by_family and (family is None or v["family_id"]==family)]
    else:
        allowed = [v for v in revisions if v["indexed"] and (family is None or v["family_id"]==family)
                   and (mode in {"all_revisions","timeline","compare"} or
                        v["plane"]==("current" if mode=="current_only" else "historic"))]
    terms = list(dict.fromkeys(term_key(token) for token in _lexemes(query)))[:32]
    frequency = Counter(term for v in allowed for term in terms if term in parse_rows[v["revision_id"]].terms)
    average = sum(sum(parse_rows[v["revision_id"]].terms.values()) for v in allowed)/max(1,len(allowed))
    def score(v):
        parsed=parse_rows[v["revision_id"]]
        length=sum(parsed.terms.values())
        value=0.
        for term in terms:
            tf=parsed.terms[term]
            idf=math.log(1+(len(allowed)-frequency[term]+.5)/(frequency[term]+.5))
            value+=idf*tf*2.2/(tf+1.2*(.25+.75*length/max(1,average)))
        return round(value,6)
    if admission is not None and terms:
        # The capped structural subset must not redefine IDF or length
        # statistics. Reuse the full permitted-plane scan's exact BM25
        # value only when the final representative is the same source.
        # An admitted historic baseline must not impersonate a matching
        # current representative (or vice versa).
        scanned_scores={(session,source):value for session,source,value in admission.scores}
        hits=[{**v,"score":scanned_scores[v["session_id"],v["source_id"]]} for v in allowed
              if (v["session_id"],v["source_id"]) in scanned_scores]
    else:
        hits=[{**v,"score":score(v)} for v in allowed]
    hits=[v for v in hits if not terms or v["score"]>0]
    hits.sort(key=lambda v:(-v["score"],-v["last_seen"],v["revision_id"]))
    current_count=sum(v["plane"]=="current" and v["indexed"] for v in revisions)
    historic_count=sum(v["plane"]=="historic" and v["indexed"] for v in revisions)
    current_ratio=current_count/max(1,len(families))
    # Reward preserved, currently indexable history, not repeated fetches or
    # unverifiable metadata. Coverage-incomplete views cannot unlock Hoarder.
    stewardship=int(round(500*(.40*min(1.,verified_transitions/8)
                    +.25*min(1.,verified_families/4)*min(1.,historic_count/4)
                    +.20*current_ratio*min(1.,historic_count/4)
                    +.15*min(1.,revalidated/4)*min(1.,historic_count/4))))
    qualified=(observed_before is None and not capped and not excluded_sessions and verified_transitions>=3 and verified_families>=2
               and current_count>=2)
    # Deficit-style round robin of due origins. Within each origin prioritize
    # expected stale loss per retained-text cost, not repeated request count.
    due = defaultdict(list)
    for f in families:
        if f["revisit"]["ready_for_review"] and f["refresh_url"]:
            due[family_origins[f["family_id"]]].append(f)
    for queue in due.values():
        queue.sort(key=lambda f:(-f["revisit"]["utility_per_cost"],f["revisit"]["due_at"],f["family_id"]))
    plan=[]
    while due and len(plan)<MAX_RESULTS:
        for host in sorted(due,key=lambda h:(-due[h][0]["revisit"]["utility_per_cost"],h)):
            if len(plan)>=MAX_RESULTS:
                break
            f=due[host].pop(0)
            plan.append(f["family_id"])
            if not due[host]:
                del due[host]
    families.sort(key=lambda f:f["family_id"])
    # Paging uses time-independent keys. Dynamic scheduler priority is a
    # separate plan so a due-time crossing cannot move rows across pages.
    family_rows=sorted((f for f in families if family is None or f["family_id"]==family),
                       key=lambda f:(-f["last_seen"],f["family_id"]))
    history=sorted((v for v in revisions if family is None or v["family_id"]==family),
                   key=lambda v:(-v["last_seen"],v["revision_id"]))
    # The receipt binds exact observations, parser identity, index partition
    # and projection content without emitting old source text.
    partition_digest=_digest({"parser":PARSER,"families":sorted(({k:v for k,v in f.items() if k not in {"revisit","refresh_url"}} for f in families),key=lambda f:f["family_id"]),
                             "revisions":revisions,"alias_blockers":sorted(_digest(a) for a in aliases if observed_before is None or a["captured_at"]<=observed_before)})
    chosen=comparisons.get(family) if mode=="compare" and family else None
    if left is not None:
        by_id={v["revision_id"]:v for v in revisions if v["family_id"]==family}
        before,after=by_id.get(left),by_id.get(right)
        if before is None or after is None or not before["indexed"] or not after["indexed"]:
            raise ValueError("selected historic comparison is not currently indexable")
        # Nonadjacent comparisons are observations, never inferred causality.
        exact={(row.session_id,row.source_id):row for row in grouped[family]}
        complete=all(exact[(v["session_id"],v["source_id"])].complete_text for v in (before,after))
        chosen={"current":after,"previous":before,"delta":_delta(parse_rows[left],parse_rows[right],complete=complete)}
    scope_digest=_digest({"partition":partition_digest,"mode":mode,"family":family,"query":query,
                         "observed_before":observed_before,"left":left,"right":right,
                         "catalogue_scope":catalogue_scope})
    offset=0
    if cursor is not None:
        bound,raw_offset=cursor.split(":",1)
        if bound!=scope_digest:
            raise ValueError("treasury cursor no longer matches index partition")
        offset=int(raw_offset)
        if offset%MAX_RESULTS or not 0<offset<=MAX_OBSERVATIONS:
            raise ValueError("invalid treasury cursor offset")
    total=max(len(family_rows),len(hits),len(history) if mode in {"timeline","compare"} else 0)
    next_cursor=f"{scope_digest}:{offset+MAX_RESULTS}" if offset+MAX_RESULTS<total else None
    return {"schema":SCHEMA,"parser":PARSER,"mode":mode,"family":family,
            "observed_before":observed_before,"page_offset":offset,"next_cursor":next_cursor,
            "query_scope_digest":scope_digest,"comparison_selection":None if left is None else {"left":left,"right":right},
            "as_of_unix":as_of,"partition_digest":partition_digest,"candidate_limit_reached":capped,
            "excluded_sessions":excluded_sessions,"observations":len(selected_observations),
            "families":len(families),"revisions":len(revisions),"changed_families":changed_families,
            "rollbacks":rollbacks,"current_indexed":current_count,"historic_indexed":historic_count,
            "metadata_only":len(revisions)-current_count-historic_count,
            "blocked_current":blocked_current,"alias_held_families":alias_held,"changes":changes,"revalidated_revisions":revalidated,
            "revisit_plan":plan,"parsed_unique_payloads":len(memo),"materialized_payload_hits":materialized_hits,
            "verified_historic_transitions":verified_transitions,"verified_changed_families":verified_families,
            "evolution":progression(growth,stewardship,qualified=qualified),
            "family_rows":family_rows[offset:offset+MAX_RESULTS],"hits":hits[offset:offset+MAX_RESULTS],
            "timeline":history[offset:offset+MAX_RESULTS] if mode in {"timeline","compare"} else [],
            "comparison":chosen,
            # Ranking statistics, lineage and evolution depend on all
            # permitted observations, not just the structural winners.
            "earliest_source_expiry":min((x.usable_until for x in ordered),default=None),
            "latest_observed_only":True,"source_text_returned":False,"network_executed":False,
            "index_admission":"temporal_query_rerank_v2" if admission is not None else "temporal_diversity_v1",
            "query_admission":None if admission is None else {
                "eligible_representatives":admission.eligible_representatives,
                "scanned_representatives":admission.scanned_representatives,
                "scanned_bytes":admission.scanned_bytes,
                "matching_representatives":admission.matching_representatives,
                "prioritized_representatives":len(admission.candidates),
                "full_structural_corpus":False,
                "score_basis":"permitted_plane_scan_bm25",
            },
            "eligible_observations":len(ordered),"indexed_observations":len(indexed),
            "training_permission":False,"fresh_consent_required":True}
