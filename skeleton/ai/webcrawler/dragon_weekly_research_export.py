"""Weekly Dragon research upgrade notes and bookmark index.

Trusted scheduler calls export_weekly after collecting verified owner-scoped
video/RSS/mother receipts. Materializes a dated Markdown document and JSON
bookmark index atomically in a configured local project folder. It does not
invent observations or automatically publish private evidence to GitHub.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from hashlib import sha256
import json,os,re
from skeleton.ai.game_builder.contracts import canonical_digest,canonical_json

HEX=re.compile(r"[0-9a-f]{64}\Z")
def _digest(value):
    if type(value) is not str or HEX.fullmatch(value) is None:
        raise ValueError("canonical source receipt required")
    return value

def render_weekly_backlog(owner:str,week_start:datetime,*,visual:tuple[dict,...],
                          rss:tuple[dict,...],matrix_reports:tuple[dict,...])->tuple[str,dict]:
    if (type(owner) is not str or not 1<=len(owner)<=128
        or any(c in owner for c in "\\/:\n\r") or
        not isinstance(week_start,datetime) or week_start.tzinfo is None
        or week_start.weekday()!=0 or week_start.hour!=0
        or week_start.minute!=0 or week_start.second!=0
        or any(type(x) is not tuple or len(x)>2000
                for x in (visual,rss,matrix_reports))):
        raise ValueError("bounded week-start/owner research export required")
    week=week_start.astimezone(timezone.utc)
    if week.weekday()!=0 or week.time()!=datetime.min.time():
        raise ValueError("week boundary must be Monday UTC midnight")
    rows=[]
    for item in visual:
        if (not isinstance(item,dict) or item.get("schema")!=
                "skeleton.dragon.visual_inspiration_bookmarks.v1"):
            raise ValueError("canonical visual bookmark packet required")
        _digest(item.get("bookmark_digest"))
        if canonical_digest({k:v for k,v in item.items() if k!="bookmark_digest"})!=item["bookmark_digest"]:
            raise ValueError("modified visual bookmark ledger")
        for note in item["notes"]:
            if len(rows)>=3000:raise ValueError("weekly backlog budget exceeded")
            rows.append({"lane":"video","source_id":item["source_id"],
                         "receipt_digest":item["bookmark_digest"],
                         "evidence_id":note["clip_digest"],
                         "title":note["note"][:160],
                         "topics":list(note["inspiring_tool_leads"]),
                         "observed_at":note["start_ms"],
                         "next_step":"Inspect original clip and verify tool/editor utility"})
    for packet in rss:
        if (not isinstance(packet,dict) or packet.get("schema")!=
                "skeleton.dragon.rss_updates_queue.v1"):
            raise ValueError("canonical RSS queue report required")
        if packet.get("owner")!=owner or packet.get("read_only") is not True:
            raise PermissionError("RSS backlog tenant/permission mismatch")
        for entry in packet["entries"]:
            _digest(entry["item_digest"])
            rows.append({"lane":"updates","source_id":entry["source_id"],
                         "receipt_digest":entry["item_digest"],
                         "evidence_id":entry["item_digest"],
                         "title":entry["title"][:160],
                         "topics":[],"observed_at":entry["observed_at"],
                         "next_step":"Check article rights, freshness and independent corroboration"})
    for packet in matrix_reports:
        if (not isinstance(packet,dict) or packet.get("schema")!=
                "skeleton.dragon.hundred_matrix_scrutiny.v1"
            or packet.get("owner")!=owner or packet.get("normal_weight_promotion_authorized") is not False):
            raise ValueError("signed mother-matrix status required")
        digest=_digest(packet.get("report_digest"))
        if canonical_digest({k:v for k,v in packet.items() if k!="report_digest"})!=digest:
            raise ValueError("tampered mother scrutiny status")
        rows.append({"lane":"mother","source_id":packet["knowledge_digest"],
                     "receipt_digest":digest,"evidence_id":digest,
                     "title":"100-matrix evidence status: "+str(packet["passed_matrix_count"])+"/100",
                     "topics":list(packet["failed_matrix_ids"])[:20],
                     "observed_at":packet["checked_at"],
                     "next_step":"Obtain independent review for unresolved matrices"})
    if len(rows)>3000:raise ValueError("weekly backlog budget exceeded")
    rows.sort(key=lambda x:(x["lane"],x["source_id"],x["evidence_id"]))
    token=week.strftime("%G-W%V")
    index={
        "schema":"skeleton.dragon.weekly_research_bookmarks.v1",
        "owner":owner,"iso_week":token,
        "items":rows,"item_count":len(rows),
        "all_entries_are_unapproved_research":True,
        "neural_training_authorized":False,
        "hyperweight_promotion_authorized":False,
    }
    index["index_digest"]=canonical_digest(index)
    lines=[
        "# Dragon research upgrade backlog — "+token,
        "",
        "Generated from provided custodied receipts; not a claim of weekly automatic crawling.",
        "Owner: "+owner,
        "Report week (UTC): "+week.isoformat(),
        "Indexed research items: "+str(len(rows)),
        "",
        "**No research item below is an approved neural weight or independently verified fact.**",
        "",
    ]
    for lane in ("video","updates","mother"):
        matches=[r for r in rows if r["lane"]==lane]
        lines.extend(["## "+lane.title()+" ("+str(len(matches))+")",""])
        for r in matches:
            title=r["title"].replace("\n"," ").replace("\r"," ")
            lines.extend([
                "- "+title,
                "  - (Next: "+r["next_step"]+")",
                "  - Evidence: `"+r["evidence_id"]+"`",
                "  - Source: `"+r["source_id"]+"`",
            ])
        if not matches:
            lines.append("No independently supplied research receipts for this lane.")
        lines.append("")
    lines.extend(["## Bookmark index",
                  "Digest: `"+index["index_digest"]+"`",
                  ""])
    return "\n".join(lines),index

def export_weekly(root:Path,owner:str,week_start:datetime,*,visual:tuple[dict,...],
                  rss:tuple[dict,...],matrix_reports:tuple[dict,...])->dict:
    # Trusted operator supplies a dedicated local root; no untrusted relative
    # paths or HTML source text are used as filenames.
    if not isinstance(root,Path) or not root.is_absolute() or root.is_symlink():
        raise ValueError("absolute trusted weekly export root required")
    markdown,index=render_weekly_backlog(
        owner,week_start,visual=visual,rss=rss,matrix_reports=matrix_reports)
    folder=root/index["iso_week"]
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    if folder.is_symlink():
        raise ValueError("symlink weekly folder refused")
    out=[]
    for filename,content in (
        ("dragon-upgrade-backlog.md",markdown),
        ("dragon-bookmarks.json",canonical_json(index)+"\n"),
    ):
        target=folder/filename
        if target.is_symlink():
            raise ValueError("weekly output symlink refused")
        # Atomic replacement avoids a half-written weekly milestone file.
        with NamedTemporaryFile(mode="w",encoding="utf-8",dir=folder,
                                prefix=".dragon-",delete=False) as temp:
            temp.write(content)
            scratch=Path(temp.name)
        try:
            os.chmod(scratch,0o600)
            os.replace(scratch,target)
        finally:
            if scratch.exists():scratch.unlink()
        out.append(str(target))
    return {"week":index["iso_week"],"items":index["item_count"],
            "folder":str(folder),"files":out,
            "index_digest":index["index_digest"],
            "network_requests":0,"model_weights_changed":False}
