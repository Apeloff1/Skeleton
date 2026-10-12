"""Trusted operator entry for Dragon's curated technical research leads."""
from __future__ import annotations

import argparse
from collections import Counter

from .contracts import canonical_json
from .dragon_almanacs import DragonAlmanacs
from .dragon_technical_source_atlas import CATALOG, CATALOG_DIGEST, DragonTechnicalSources
from .reviewed_knowledge import ReviewedKnowledgeStore


def main():
    parser=argparse.ArgumentParser(description="Policy-stage technical source metadata")
    parser.add_argument("command",choices=("census","import","plan","history"))
    parser.add_argument("--database",required=True)
    parser.add_argument("--owner",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    parser.add_argument("--recorded-at",type=int)
    parser.add_argument("--query")
    parser.add_argument("--source-id")
    parser.add_argument("--limit",type=int,default=20)
    parser.add_argument("--max-per-host",type=int,default=2)
    parser.add_argument("--direct-only",action="store_true")
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
        else:
            if not args.source_id: parser.error("--source-id required")
            report=atlas.history(args.owner,args.source_id,authorized=True)
        print(canonical_json(report))


if __name__=="__main__":
    main()
