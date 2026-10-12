"""Trusted operator entry for Dragon's curated technical research leads."""
from __future__ import annotations

import argparse
from collections import Counter

from .contracts import canonical_json
from .dragon_almanacs import DragonAlmanacs
from .dragon_technical_source_atlas import CATALOG, CATALOG_DIGEST, DragonTechnicalSources
from .dragon_technical_source_captures import DragonSourceCaptures
from .dragon_technical_source_analysis import DragonTechnicalGlean
from .reviewed_knowledge import ReviewedKnowledgeStore


def main():
    parser=argparse.ArgumentParser(description="Policy-stage technical source metadata")
    parser.add_argument("command",choices=("census","import","plan","history",
                                                  "capture-history","capture-review",
                                                  "capture-census","glean-preview","glean-handoff"))
    parser.add_argument("--database",required=True)
    parser.add_argument("--owner",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    parser.add_argument("--recorded-at",type=int)
    parser.add_argument("--query")
    parser.add_argument("--source-id")
    parser.add_argument("--capture-digest")
    parser.add_argument("--peer-source-id",action="append",default=[])
    parser.add_argument("--limit",type=int,default=20)
    parser.add_argument("--max-per-host",type=int,default=2)
    parser.add_argument("--direct-only",action="store_true")
    parser.add_argument("--include-captured-text",action="store_true")
    args=parser.parse_args()
    if not args.trusted_local_operator:
        parser.error("local operator trust required; no HTTP browsing endpoint")
    with ReviewedKnowledgeStore(args.database) as store:
        atlas=DragonTechnicalSources(DragonAlmanacs(store))
        if args.command=="census":
            report={"schema":"skeleton.dragon.technical_source_census.v1",
                "catalog_digest":CATALOG_DIGEST,"curated_leads":len(CATALOG),
                "families":dict(sorted(Counter(x["family"] for x in CATALOG).items())),
                "rights_review":"not_assessed","crawler_authorized":False,
                "training_authorized":False}
        elif args.command=="import":
            if args.recorded_at is None:
                parser.error("--recorded-at UNIX epoch required")
            report=atlas.import_catalog(args.owner,authorized=True,
                                        recorded_at=args.recorded_at)
        elif args.command=="plan":
            if not args.query: parser.error("--query required")
            report=atlas.plan(args.owner,args.query,authorized=True,limit=args.limit,
                              max_per_host=args.max_per_host,
                              include_adjacent=not args.direct_only)
        elif args.command=="history":
            if not args.source_id: parser.error("--source-id required")
            report=atlas.history(args.owner,args.source_id,authorized=True)
        else:
            captures=DragonSourceCaptures(atlas.a)
            if args.command in ("glean-preview","glean-handoff"):
                if not args.source_id:
                    parser.error("--source-id required for glean inspection")
                glean=DragonTechnicalGlean(captures)
                if args.command=="glean-preview":
                    if not args.capture_digest:
                        parser.error("--capture-digest required")
                    report=glean.preview(args.owner,args.source_id,
                        capture_digest=args.capture_digest,
                        peers=tuple(args.peer_source_id),authorized=True)
                else:
                    report=glean.handoff(args.owner,args.source_id,
                        authorized=True,include_quotes=args.include_captured_text)
            elif args.command=="capture-census":
                rows=store.db.execute(
                    "SELECT DISTINCT source FROM dragon_technical_captures_v1 "
                    "WHERE owner=? ORDER BY source",(args.owner,)
                ).fetchall()
                sequences=[captures.history(args.owner,row[0],authorized=True)
                           for row in rows]
                report={
                    "schema":"skeleton.dragon.capture_census.v1",
                    "owner":args.owner,
                    "curated_candidates":len(CATALOG),
                    "observed_sources":len(rows),
                    "observation_events":sum(len(seq) for seq in sequences),
                    "new_content_revisions":sum(
                        event["change"] in ("new","changed")
                        for seq in sequences for event in seq
                    ),
                    "uncorroborated_review_packets":sum(
                        seq[-1]["change"]!="unchanged" for seq in sequences if seq
                    ),
                    "network_requests":0,
                    "knowledge_approved":False,
                    "training_authorized":False,
                }
            else:
                if not args.source_id:
                    parser.error("--source-id required for capture inspection")
                report=(captures.history(args.owner,args.source_id,authorized=True)
                        if args.command=="capture-history"
                        else captures.review_packet(
                            args.owner,args.source_id,authorized=True,
                            include_text=args.include_captured_text
                        ))
        print(canonical_json(report))


if __name__=="__main__":
    main()
