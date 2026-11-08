"""LDraw CAD model finite line-type inventory without external part loading."""
from __future__ import annotations
from collections import Counter
import re
from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines

LDRAW_TYPES=frozenset({"text/x-ldraw","application/x-ldraw"})


def extract_ldraw(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    rows=raw.lstrip("\ufeff").splitlines()
    if not rows or len(rows)>32768:
        raise ResearchFormatError("LDraw source capacity exceeded")
    counts=Counter()
    for row in rows:
        if len(row)>8192:
            raise ResearchFormatError("LDraw geometry record exceeds width")
        line=row.strip()
        if not line:
            continue
        fields=line.split()
        if fields[0] not in ("0","1","2","3","4","5"):
            raise ResearchFormatError("invalid LDraw line type")
        kind=fields[0]
        if kind!="0":
            expected={"1":15,"2":8,"3":11,"4":14,"5":14}[kind]
            if len(fields)<expected:
                raise ResearchFormatError("incomplete LDraw primitive")
            if kind=="1":
                # Library part references remain inert textual source bytes
                # and are never opened or projected as filesystem paths.
                pass
            else:
                for value in fields[2:expected]:
                    try:
                        v=float(value)
                    except ValueError as exc:
                        raise ResearchFormatError("invalid LDraw numeric geometry") from exc
                    if not -1e6<=v<=1e6:
                        raise ResearchFormatError("LDraw geometry extent exceeded")
        counts[kind]+=1
        if sum(counts.values())>16384:
            raise ResearchFormatError("LDraw line count exceeded")
    if not any(counts[k] for k in ("1","2","3","4","5")):
        raise ResearchFormatError("LDraw source has no primitive geometry")
    output=[
        "CAD asset: LDraw finite primitive inventory",
        f"Source records: {sum(counts.values())}",
        f"Part references (not loaded): {counts['1']}",
        f"Line primitives: {counts['2']}; triangle primitives: {counts['3']}",
        f"Quadrilateral primitives: {counts['4']}; conditional lines: {counts['5']}",
        "External parts, instructions, unofficial libraries: not fetched or executed",
    ]
    return project_lines(output,title="LDraw CAD geometry",max_chars=max_chars)
