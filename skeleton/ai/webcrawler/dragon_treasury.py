"""Hoarder: version-aware, bounded, owner-scoped archive retrieval.

Source snapshots are the durable records. This index is rebuilt from witnessed
observations; no archive copy, raw payload, model training or new source grant
is created. Expired/withdrawn versions remain metadata-only blockers of stale
promotion. 'Current' means latest observed in the selected corpus, not live truth.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from .dragon_companion import _lexemes, _signature, _similarity

SCHEMA = "skeleton.dragon.treasury.v1"
PARSER = "retained-text-sections-v1"
MAX_SESSIONS = 8
MAX_OBSERVATIONS = 512
MAX_INDEXED = 128
MAX_SECTIONS = 32
MAX_TERMS = 2048
MAX_RESULTS = 24
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_MODES = frozenset({"current_only", "historic_only", "all_revisions", "timeline", "compare"})
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
    section_hashes: frozenset[str]
    signature: frozenset[int]
    numbers: frozenset[str]
    digest: str


def parse_retained_text(text: str) -> ParsedVersion:
    """Independent bounded lexical reparse, never a raw HTML/network reparse."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 24000:
        raise ValueError("retained text exceeds parser envelope")
    words = _lexemes(text)[:MAX_TERMS]
    # Stable block geometry for change localization; no attacker-controlled
    # markup is executed and no raw source vocabulary is returned to caller.
    blocks = [words[i:i+64] for i in range(0,len(words),64)][:MAX_SECTIONS]
    hashes = frozenset(_digest(block) for block in blocks)
    numbers = frozenset(word for word in words if word.isdecimal())
    return ParsedVersion(Counter(words), hashes, _signature(text), numbers,
                         _digest({"parser": PARSER, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                  "section_hashes": sorted(hashes)}))


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
    kind = "minor_update" if similarity >= .85 and not numeric else (
        "substantive_update" if similarity >= .35 or numeric else "major_rewrite")
    return {"kind":kind,"similarity":round(similarity,6),"added_terms":len(b-a),
            "removed_terms":len(a-b),"changed_sections":len(before.section_hashes^after.section_hashes),
            "numeric_change":numeric}


def _revisit(versions: list[dict], latest: Observation, now: float) -> dict:
    # Exposure is elapsed observation time, not a count of crawl requests.
    # Gamma-like shrinkage to one change/week avoids unstable short samples.
    first = versions[0]["first_seen"]
    exposure_days = max(0., (latest.captured_at-first)/86400)
    changes = max(0,len(versions)-1)
    hazard = (1+changes)/(7+exposure_days)
    # Target roughly 30% chance of change; bounded to 1h..7d. Advice only.
    interval = max(3600., min(604800., -math.log(.7)*86400/hazard))
    due = latest.captured_at + interval
    if latest.advisory_due is not None:
        # Publisher freshness hints can postpone, never accelerate a revisit.
        due = max(due, latest.advisory_due)
    age = max(0., now-latest.captured_at)
    probability = 1-math.exp(-hazard*age/86400)
    return {"due_at":round(due,3),"change_probability_estimate":round(probability,6),
            "observed_changes":changes,"interval_seconds":round(due-latest.captured_at,3),
            "ready_for_review":bool(latest.refresh_allowed and now>=due),
            "fresh_consent_required":True,"network_executed":False}


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
    level = min(60,stage*10+1+int(fraction*10))
    return {"form":_STAGES[stage],"stage":stage,"level":level,
            "expedition_growth":growth,"treasury_growth":stewardship,
            "total_evolution":total,"effective_evolution":effective,
            "stage_progress":round(fraction,6),"hoarder_qualified":qualified,
            "next_threshold":hi if stage<5 else None}


def build_treasury(observations: list[Observation], *, as_of: float, growth: int,
                   mode: str = "current_only", query: str = "", family: str | None = None,
                   candidate_limit_reached: bool = False, excluded_sessions: int = 0) -> dict:
    if (not isinstance(observations,list) or len(observations)>MAX_OBSERVATIONS
            or type(as_of) not in (int,float) or not math.isfinite(as_of)
            or mode not in _MODES or not isinstance(query,str) or len(query.encode())>1024
            or family is not None and (not isinstance(family,str) or not _HEX.fullmatch(family))
            or type(candidate_limit_reached) is not bool
            or type(excluded_sessions) is not int or not 0<=excluded_sessions<=MAX_SESSIONS):
        raise ValueError("invalid treasury query envelope")
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
        family_id = _digest({"url":row.url,"media":row.media,"variant":row.variant})
        grouped[family_id].append(row)
    if len({x.session_id for x in observations})>MAX_SESSIONS:
        raise ValueError("archive expedition capacity exceeded")
    ordered = sorted((x for x in observations if x.text is not None),
                     key=lambda x:(-x.captured_at,x.session_id,x.source_id))
    indexed = ordered[:MAX_INDEXED]
    index = {(x.session_id,x.source_id):parse_retained_text(x.text) for x in indexed}
    capped = candidate_limit_reached or len(ordered)>MAX_INDEXED
    families, revisions, parse_rows = [], [], {}
    comparisons = {}
    changed_families = changes = rollbacks = revalidated = blocked_current = 0
    for fid, rows in sorted(grouped.items()):
        rows.sort(key=lambda x:(x.captured_at,x.session_id,x.source_id))
        versions = []
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
                latest.update(session_id=row.session_id,source_id=row.source_id,
                              indexed=parsed is not None,metadata_only=parsed is None,
                              archive_only=row.archive_only)
                parse_rows[latest["revision_id"]] = parsed
                prior = row
                continue
            delta = ({"kind":"initial","similarity":None,"added_terms":None,"removed_terms":None,
                      "changed_sections":None,"numeric_change":None} if prior is None else
                     _delta(index.get((prior.session_id,prior.source_id)),parsed,
                            complete=prior.complete_text and row.complete_text))
            if row.content_hash in observed_hashes:
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
                       "archive_only":row.archive_only,
                       "delta":delta}
            versions.append(version)
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
            parse_rows[latest["revision_id"]]=None
        current_available=latest["indexed"] and not latest["archive_only"]
        blocked_current+=int(not current_available)
        for v in versions:
            v["plane"]="current" if v is latest and not v["archive_only"] else "historic"
            v["latest_observed"]=v is latest
            v["source_id"]=v["source_id"] if v["indexed"] else None
            v["session_id"]=v["session_id"] if v["indexed"] else None
            v["projection_digest"]=parse_rows[v["revision_id"]].digest if v["indexed"] else None
        revisions.extend(versions)
        families.append({"family_id":fid,"revision_count":len(versions),
                         "current_revision":latest["revision_id"],"first_seen":versions[0]["first_seen"],
                         "last_seen":latest["last_seen"],"current_indexed":current_available,
                         "simultaneous_conflict":tied,"revisit":_revisit(versions,rows[-1],as_of),
                         "refresh_url":rows[-1].url if rows[-1].refresh_allowed and not tied else None})
        if len(versions)>1:
            comparisons[fid]={"current":latest,"previous":versions[-2],"delta":latest["delta"]}
    # Explicitly separate index corpora before computing document frequency.
    # Historic pages cannot leak into current-only scoring via IDF.
    allowed = [v for v in revisions if v["indexed"] and (family is None or v["family_id"]==family)
               and (mode in {"all_revisions","timeline","compare"} or
                    v["plane"]==("current" if mode=="current_only" else "historic"))]
    terms = list(dict.fromkeys(_lexemes(query)))[:32]
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
    hits=[{**v,"score":score(v)} for v in allowed]
    hits=[v for v in hits if not terms or v["score"]>0]
    hits.sort(key=lambda v:(-v["score"],-v["last_seen"],v["revision_id"]))
    current_count=sum(v["plane"]=="current" and v["indexed"] for v in revisions)
    historic_count=sum(v["plane"]=="historic" and v["indexed"] for v in revisions)
    verified_transitions=sum(not v["latest_observed"] and v["indexed"] for v in revisions)
    current_ratio=current_count/max(1,len(families))
    # Reward preserved, currently indexable history, not repeated fetches or
    # unverifiable metadata. Coverage-incomplete views cannot unlock Hoarder.
    stewardship=int(round(500*(.40*min(1.,verified_transitions/8)
                    +.25*min(1.,changed_families/4)*min(1.,historic_count/4)
                    +.20*current_ratio*min(1.,historic_count/4)
                    +.15*min(1.,revalidated/4)*min(1.,historic_count/4))))
    qualified=(not capped and not excluded_sessions and verified_transitions>=3 and changed_families>=2
               and current_count>=2)
    families.sort(key=lambda f:(not f["revisit"]["ready_for_review"],-f["last_seen"],f["family_id"]))
    family_rows=[f for f in families if family is None or f["family_id"]==family]
    history=sorted((v for v in revisions if family is None or v["family_id"]==family),
                   key=lambda v:(-v["last_seen"],v["revision_id"]))
    # The receipt binds exact observations, parser identity, index partition
    # and projection content without emitting old source text.
    partition_digest=_digest({"parser":PARSER,"families":sorted(({k:v for k,v in f.items() if k not in {"revisit","refresh_url"}} for f in families),key=lambda f:f["family_id"]),
                             "revisions":revisions})
    return {"schema":SCHEMA,"parser":PARSER,"mode":mode,"family":family,
            "as_of_unix":as_of,"partition_digest":partition_digest,"candidate_limit_reached":capped,
            "excluded_sessions":excluded_sessions,"observations":len(observations),
            "families":len(families),"revisions":len(revisions),"changed_families":changed_families,
            "rollbacks":rollbacks,"current_indexed":current_count,"historic_indexed":historic_count,
            "metadata_only":len(revisions)-current_count-historic_count,
            "blocked_current":blocked_current,"changes":changes,"revalidated_revisions":revalidated,
            "verified_historic_transitions":verified_transitions,
            "evolution":progression(growth,stewardship,qualified=qualified),
            "family_rows":family_rows[:MAX_RESULTS],"hits":hits[:MAX_RESULTS],
            "timeline":history[:MAX_RESULTS] if mode in {"timeline","compare"} else [],
            "comparison":comparisons.get(family) if mode=="compare" and family else None,
            "earliest_source_expiry":min((x.usable_until for x in indexed),default=None),
            "latest_observed_only":True,"source_text_returned":False,"network_executed":False,
            "training_permission":False,"fresh_consent_required":True}
