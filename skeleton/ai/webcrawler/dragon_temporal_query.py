"""Query-aware first-stage admission for the bounded temporal index.

The scan examines only permitted retained text, not remote bodies or held
text. It ranks candidate version representatives before expensive structural
parsing. The second-stage index still independently enforces plane, family,
source permission, and revision lineage. No term vocabulary leaves this module.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math

MAX_SCAN_OBSERVATIONS=2048
MAX_SCAN_BYTES=MAX_SCAN_OBSERVATIONS*24000
MAX_QUERY_TERMS=32
MAX_QUERY_SLOTS=192


@dataclass(frozen=True)
class QueryAdmission:
    candidates: tuple
    eligible_representatives: int
    scanned_representatives: int
    scanned_bytes: int
    matching_representatives: int
    # Exact permitted representative scores; internal only, no lexemes
    # or per-source scan data leave the projection.
    scores: tuple[tuple[str,str,float], ...]


def _runs(rows):
    """Stable chronological payload runs; no fuzzy identity inference."""
    ordered=sorted(rows,key=lambda r:(r.captured_at,r.session_id,r.source_id))
    groups=[]
    for row in ordered:
        if not groups or row.content_hash!=groups[-1][0].content_hash:
            groups.append([])
        groups[-1].append(row)
    return groups


def representatives(grouped,*,mode,family,blockers):
    for fid,rows in sorted(grouped.items()):
        if family is not None and fid!=family:
            continue
        runs=_runs(rows)
        latest=runs[-1][-1]
        simultaneous=len({r.content_hash for r in rows if r.captured_at==latest.captured_at})>1
        alias_conflict=any(a["captured_at"]>=latest.captured_at and a["content_hash"]!=latest.content_hash
                           for a in blockers.get(latest.url,()))
        for i,run in enumerate(runs):
            head=i==len(runs)-1
            rep=next((r for r in reversed(run) if r.text is not None),None)
            if rep is None:
                continue
            current=head and rep is latest and not latest.archive_only and not simultaneous and not alias_conflict
            if mode=="current_only":
                if current:
                    yield rep
            elif mode=="at_time":
                # Latest as-of observation; an older identical retained
                # representative can support the same observed payload.
                if head and not simultaneous and not alias_conflict:
                    yield rep
            elif mode=="historic_only":
                if not current and not (head and simultaneous):
                    yield rep
            elif not (head and simultaneous):
                yield rep


def rank_admission(grouped,*,mode,family,blockers,query,lexemes,slots:int)->QueryAdmission:
    if type(slots) is not int or not 0<=slots<=MAX_QUERY_SLOTS:
        raise ValueError("invalid temporal query admission capacity")
    terms=tuple(dict.fromkeys(lexemes(query)))[:MAX_QUERY_TERMS]
    if not terms or not slots:
        return QueryAdmission((),0,0,0,0,())
    wanted=set(terms)
    rows=list(representatives(grouped,mode=mode,family=family,blockers=blockers))
    if len(rows)>MAX_SCAN_OBSERVATIONS:
        raise ValueError("temporal candidate scan bound exceeded")
    # Accumulate exact query-term frequencies and document lengths, never
    # build an unbounded full-vocabulary dictionary across the catalogue.
    summaries=[]
    df=Counter()
    total_len=0
    scanned_bytes=0
    for row in rows:
        size=len(row.text.encode("utf-8"))
        if size>24000 or scanned_bytes+size>MAX_SCAN_BYTES:
            raise ValueError("temporal candidate scan byte bound exceeded")
        scanned_bytes+=size
        words=lexemes(row.text)
        counts=Counter(word for word in words if word in wanted)
        df.update(counts.keys())
        length=len(words)
        total_len+=length
        summaries.append((row,counts,length))
    n=len(summaries)
    average=total_len/max(1,n)
    scores=[]
    for row,counts,length in summaries:
        if not counts:
            continue
        norm=1.2*(.25+.75*length/max(1,average))
        score=sum(math.log1p((n-df[t]+.5)/(df[t]+.5))*count*2.2/(count+norm)
                  for t,count in counts.items())
        scores.append((round(score,6),row))
    scores.sort(key=lambda item:(-item[0],-item[1].captured_at,item[1].session_id,item[1].source_id))
    return QueryAdmission(tuple(row for _,row in scores[:slots]),len(rows),n,scanned_bytes,len(scores),
                          tuple((row.session_id,row.source_id,score) for score,row in scores))
