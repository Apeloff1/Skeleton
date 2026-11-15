"""Deterministic bounded index admission for temporal observations.

Preserve latest representatives, reserve historical diversity, and prioritize
an explicitly selected family or time slice. No ranking can make an older
observation current; the lineage builder still sees every metadata record.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json


def family_identity(row)->str:
    raw=json.dumps({"url":row.url,"media":row.media,"variant":row.variant},
                   sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _revision_runs(fid, rows):
    """Same chronological identity as the treasury lineage; no text authority."""
    runs=[]
    parent=None
    for row in reversed(rows):
        if not runs or runs[-1][1][-1].content_hash!=row.content_hash:
            raw=json.dumps({"family":fid,"parent":parent,"first_session":row.session_id,
                            "first_source":row.source_id,"content":row.content_hash},
                           sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)
            parent=hashlib.sha256(raw.encode("ascii")).hexdigest()
            runs.append((parent,[]))
        runs[-1][1].append(row)
    return runs


def select_candidates(grouped:dict,*,budget:int,family:str|None,observed_before:float|None,
                      comparison:tuple[str,str]|None=None)->list:
    if type(budget) is not int or budget<1:
        raise ValueError("invalid index admission budget")
    chosen={}
    def add(row):
        if row is not None and row.text is not None and len(chosen)<budget:
            chosen.setdefault((row.session_id,row.source_id),row)
    def newest(rows):
        return sorted(rows,key=lambda r:(r.captured_at,r.session_id,r.source_id),reverse=True)
    ordered={fid:newest(rows) for fid,rows in grouped.items()}
    # First supply the explicitly requested family including older permitted
    # representatives; never allow a global recent-capture flood to bury it.
    if family is not None and family in ordered:
        rows=ordered[family]
        runs=_revision_runs(family,rows)
        # Preserve explicitly requested revisions before recent duplicates.
        # Metadata-only observations participate in identity, not text access.
        if comparison is not None:
            for rid in comparison:
                for identity,run in runs:
                    if identity==rid:
                        add(next((row for row in reversed(run) if row.text is not None),None))
                        break
        # Reserve latest exact observation and both ends of the newest
        # distinct transition. This keeps current/compare useful after a
        # long sequence of unchanged captures.
        add(rows[0] if rows else None)
        if len(runs)>1:
            add(runs[-2][1][-1])
            add(runs[-1][1][0])
        if observed_before is not None:
            add(next((row for row in rows if row.captured_at<=observed_before),None))
        for _,run in reversed(runs):
            add(next((row for row in reversed(run) if row.text is not None),None))
        for _,run in reversed(runs):
            add(run[0])
            add(run[-1])
        for row in rows:
            add(row)
    # Time queries first reserve the newest observation at/before the cutoff
    # per family (held observations never mint a fallback).
    if observed_before is not None:
        cutoff=[]
        for rows in ordered.values():
            row=next((row for row in rows if row.captured_at<=observed_before),None)
            if row is not None:
                cutoff.append(row)
        for row in newest(cutoff):
            add(row)
    # Give at least half the remaining slots to latest family observations.
    # The balance preserves history from different families instead of a
    # burst of identical recent fetches.
    latest=newest([rows[0] for rows in ordered.values() if rows])
    latest_limit=len(chosen)+(budget-len(chosen)+1)//2
    for row in latest:
        if len(chosen)>=latest_limit:
            break
        add(row)
    # One representative of each distinct chronological payload run, then
    # fair interleaving across origins/families. An inaccessible latest
    # duplicate does not consume a slot, but remains in the metadata ledger.
    queues={}
    for fid,rows in ordered.items():
        runs=[]
        current=[]
        key=None
        for row in rows:
            if row.content_hash!=key:
                if current:
                    runs.append(current)
                current=[]
                key=row.content_hash
            current.append(row)
        if current:
            runs.append(current)
        representatives=[]
        for run in runs:
            permitted=next((r for r in run if r.text is not None),None)
            if permitted is not None and (permitted.session_id,permitted.source_id) not in chosen:
                representatives.append(permitted)
        if representatives:
            queues[fid]=representatives
    keys=sorted(queues,key=lambda fid:(-queues[fid][0].captured_at,fid))
    while keys and len(chosen)<budget:
        next_keys=[]
        for fid in keys:
            if len(chosen)>=budget:
                break
            add(queues[fid].pop(0))
            if queues[fid]:
                next_keys.append(fid)
        keys=next_keys
    # Spend unused capacity on repeated observations only after distinct
    # lineage representatives. This allows cutoff queries to select an
    # independently authorized earlier same-content observation.
    if len(chosen)<budget:
        for row in newest([row for rows in ordered.values() for row in rows]):
            add(row)
            if len(chosen)>=budget:
                break
    return list(chosen.values())
