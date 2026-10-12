#!/usr/bin/env python3
"""Generate a weekly Dragon upgrade report from reviewed on-disk receipts.

Without an explicitly provided input snapshot, produce an *empty* status
report, never synthesized research. The original source worker is responsible
for permission and custody, not this scheduled formatter.
"""
from __future__ import annotations
import argparse,json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path

from skeleton.ai.webcrawler.dragon_weekly_research_export import export_weekly

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="")
    ap.add_argument("--root",required=True)
    ap.add_argument("--owner",required=True)
    ap.add_argument("--week",default="")
    ns=ap.parse_args()
    today=datetime.now(timezone.utc)
    if ns.week:
        date=datetime.strptime(ns.week,"%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        date=(today-timedelta(days=today.weekday())).replace(
            hour=0,minute=0,second=0,microsecond=0)
    payload={"visual":[],"rss":[],"matrix_reports":[],
             "video_tool_indexes":[],"article_fact_reports":[]}
    if ns.input:
        path=Path(ns.input).resolve(strict=True)
        if not path.is_file() or path.stat().st_size>4_000_000:
            raise ValueError("bounded pre-reviewed weekly input required")
        raw=json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(raw,dict)
            or not {"visual","rss","matrix_reports"}.issubset(raw)
            or not set(raw).issubset(payload)):

            raise ValueError("approved weekly payload schema required")
        payload.update(raw)
    export=export_weekly(Path(ns.root).resolve(),ns.owner,date,
        visual=tuple(payload["visual"]),rss=tuple(payload["rss"]),
        matrix_reports=tuple(payload["matrix_reports"]),
        video_tool_indexes=tuple(payload["video_tool_indexes"]),
        article_fact_reports=tuple(payload["article_fact_reports"]))
    print(json.dumps(export,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
