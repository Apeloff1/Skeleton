"""Local, owner-scoped operation of the Dragon's almanac projection."""
from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import canonical_json
from .dragon_almanacs import DragonAlmanacs, ProjectLearning, read_source_registry
from .dragon_almanac_sequence import SequentialAlmanacWorker
from .dragon_almanac_experiment import run_original_experiment
from .game_niche_catalog import NICHES
from .dragon_industry_domains import INDUSTRY_DOMAINS, ALMANAC_SECTIONS
from .reviewed_knowledge import ReviewedKnowledgeStore


def main():
    parser = argparse.ArgumentParser(description="Import, inspect and seed sequential Dragon almanacs")
    parser.add_argument("command", choices=("bootstrap", "status", "experiment", "delivery-status", "delivery-search", "delivery-brief"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--registry", default=str(Path(__file__).parent / "catalogs/dragon_sources_20261010"))
    parser.add_argument("--output")
    parser.add_argument("--now", type=int)
    parser.add_argument("--query", help="Reviewed mechanic or design research question")
    parser.add_argument("--design", type=Path, help="Strict native game design JSON")
    args = parser.parse_args()
    if not args.trusted_local_operator:
        parser.error("local authenticated operator acknowledgement required")
    with ReviewedKnowledgeStore(args.database) as library:
        almanacs = DragonAlmanacs(library)
        worker = SequentialAlmanacWorker(almanacs)
        if args.command.startswith("delivery-"):
            from .dragon_delivery import DragonDelivery
            from ..webcrawler.dragon_game_design import load_design
            if args.now is None:
                parser.error("delivery projections require --now for evidence freshness")
            delivery = DragonDelivery(almanacs)
            library.db.execute("BEGIN")
            try:
                if args.command == "delivery-status":
                    result = delivery.overview(args.owner, now=args.now, authorized=True)
                elif args.command == "delivery-search":
                    if not args.query:
                        parser.error("delivery-search requires --query")
                    result = delivery.search(args.owner, args.query, now=args.now, authorized=True)
                else:
                    if not args.query or not args.design:
                        parser.error("delivery-brief requires --query and --design")
                    result = delivery.brief(args.owner, load_design(args.design), args.query, now=args.now, authorized=True)
            finally:
                library.db.execute("ROLLBACK")
        elif args.command == "bootstrap":
            registry = read_source_registry(args.registry)
            ingestion = almanacs.ingest_sources(args.owner, registry, authorized=True)
            for niche in NICHES:
                for mechanic in niche.mechanics:
                    for section in ALMANAC_SECTIONS:
                        almanacs.ensure_topic(args.owner, ("Gaming", niche.family, niche.niche_id, mechanic, section), authorized=True)
            for domain, headers in INDUSTRY_DOMAINS:
                for header in headers:
                    for section in ALMANAC_SECTIONS:
                        almanacs.ensure_topic(args.owner, ("Industry", domain, header, section), authorized=True)
            jobs = worker.seed(args.owner, authorized=True)
            result = {"ingestion": ingestion, "new_sequential_jobs": jobs,
                      "catalog_digest": registry["catalog_digest"],
                      "almanacs": almanacs.report(args.owner, authorized=True, limit=1),
                      "worker": worker.status(args.owner, authorized=True)}
        elif args.command == "experiment":
            if args.now is None or not args.output:
                parser.error("experiment requires --now and --output for raw evidence")
            result = run_original_experiment()
            raw = canonical_json(result)
            Path(args.output).write_text(raw + "\n")
            topic = almanacs.ensure_topic(args.owner, ("Gaming", "AI", "Pathfinding", "Machine findings"), authorized=True)
            learning = ProjectLearning("original-grid-study", result["experiment_digest"], topic,
                "steppingstone", "measured_experiment",
                "Uniform-cost and A* search returned matching path costs on the recorded synthetic grids.",
                "Deterministic seeded grid study; raw rows and held-out cost-model results are retained.",
                "Single implementation and synthetic generator; not evidence about human gameplay or all games.",
                (result["experiment_digest"],))
            digest = almanacs.record_learning(args.owner, learning, now=args.now, authorized=True)
            result = {"summary": result["summary"], "model": result["model"], "learning_digest": digest,
                      "memory_promotion_authorized": False, "raw_evidence": args.output}
        else:
            result = {"almanacs": almanacs.report(args.owner, authorized=True),
                      "worker": worker.status(args.owner, authorized=True)}
        print(canonical_json(result))


if __name__ == "__main__":
    main()
