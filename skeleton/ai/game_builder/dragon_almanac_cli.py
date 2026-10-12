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


def _portfolio_request(args, parser):
    """One typed parser for preview and persistent research campaign creation."""
    from .dragon_discovery_portfolio import PortfolioAxis, PortfolioRequest
    from .dragon_discovery_mission import SourceMission
    if not args.query or not args.axis:
        parser.error("portfolio planning requires --query and at least one --axis")
    axes = []
    for value in args.axis:
        parts = value.split(":")
        if len(parts) not in (2, 4):
            parser.error("--axis requires id:question[:minimum:importance]")
        if len(parts) == 2:
            axes.append(PortfolioAxis(parts[0], parts[1]))
        else:
            try:
                count, importance = int(parts[2]), int(parts[3])
            except ValueError:
                parser.error("axis minimum and importance must be integers")
            axes.append(PortfolioAxis(parts[0], parts[1], count, importance))
    return PortfolioRequest(
        SourceMission(args.query, platform=args.platform, genre=args.genre,
                      era=args.era, prefer_video=args.prefer_video,
                      scan_budget=args.scan_budget),
        tuple(axes), total_limit=args.portfolio_limit,
        per_axis_candidates=args.per_axis_candidates,
        max_per_host=args.max_per_host, indexed=args.indexed)


def main():
    parser = argparse.ArgumentParser(description="Import, inspect and seed sequential Dragon almanacs")
    parser.add_argument("command", choices=("bootstrap", "status", "experiment", "delivery-status", "delivery-search", "delivery-brief", "mission-scout", "mission-index", "mission-audit", "mission-health", "mission-portfolio", "campaign-record", "campaign-inspect", "campaign-refresh", "import-supplements", "discovery-verify", "discovery-census", "platform-matrix", "discovery-identity-audit", "import-reconciled", "discovery-topics", "discovery-sources", "discovery-receipts"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    parser.add_argument("--registry", default=str(Path(__file__).parent / "catalogs/dragon_sources_20261010"))
    parser.add_argument("--output")
    parser.add_argument("--now", type=int)
    parser.add_argument("--platform", default="", help="Target console, computer or mobile platform")
    parser.add_argument("--genre", default="", help="Target game style or editor family")
    parser.add_argument("--era", default="", help="Historical era or generation")
    parser.add_argument("--prefer-video", action="store_true")
    parser.add_argument("--topic", help="Optional owner-scoped almanac topic ID")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--scan-budget", type=int, default=2000)
    parser.add_argument("--samples-per-platform", type=int, default=3,
                        help="Maximum URL metadata examples per platform (0..10)")
    parser.add_argument("--axis", action="append", default=[],
                        help="Portfolio id:question or id:question:minimum:importance")
    parser.add_argument("--portfolio-limit", type=int, default=30)
    parser.add_argument("--per-axis-candidates", type=int, default=15)
    parser.add_argument("--max-per-host", type=int, default=3)
    parser.add_argument("--campaign", help="Exact research campaign ID")
    parser.add_argument("--expected-parent", help="Current campaign revision digest for CAS")
    parser.add_argument("--indexed", action="store_true",
                        help="Use materialized whole-catalog facet index")
    parser.add_argument("--after-source", help="Resumable exclusive facet indexing cursor")
    parser.add_argument("--parent", help="Optional parent heading topic ID")
    parser.add_argument("--source", help="Exact source ID for raw discovery receipts")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--supplement", action="append", default=[], help="Discovery evidence JSON in chain order")
    parser.add_argument("--query", help="Reviewed mechanic or design research question")
    parser.add_argument("--design", type=Path, help="Strict native game design JSON")
    args = parser.parse_args()
    if not args.trusted_local_operator:
        parser.error("local authenticated operator acknowledgement required")
    with ReviewedKnowledgeStore(args.database) as library:
        almanacs = DragonAlmanacs(library)
        worker = SequentialAlmanacWorker(almanacs)
        if args.command in {"discovery-verify", "discovery-census", "platform-matrix", "discovery-identity-audit", "import-reconciled"}:
            from .dragon_discovery_reconciled import (
                verify_reconciled_chain, import_reconciled_chain)
            registry = read_source_registry(args.registry)
            if args.supplement:
                parser.error("reconciled chain uses pinned evidence; omit --supplement")
            if args.command == "discovery-verify":
                result = verify_reconciled_chain(registry)
            elif args.command == "discovery-census":
                from .dragon_discovery_census import discovery_census
                result = discovery_census(registry, top_hosts=args.limit)
            elif args.command == "platform-matrix":
                from .dragon_platform_coverage import platform_discovery_matrix
                result = platform_discovery_matrix(
                    registry, samples_per_platform=args.samples_per_platform)
            elif args.command == "discovery-identity-audit":
                from .dragon_discovery_identity_audit import audit_raw_discovery_identity
                result = audit_raw_discovery_identity(registry, detail_limit=args.limit)
            else:
                result = import_reconciled_chain(
                    almanacs, args.owner, registry, authorized=True)
        elif args.command == "import-supplements":
            from .dragon_discovery_admission import import_supplement_files
            if not args.supplement:
                parser.error("import-supplements requires --supplement in lineage order")
            registry = read_source_registry(args.registry)
            result = import_supplement_files(
                almanacs, args.owner, registry, args.supplement, authorized=True)
        elif args.command in {"discovery-topics", "discovery-sources", "discovery-receipts"}:
            from .dragon_discovery_admission import DragonDiscoveryAdmission
            discovery = DragonDiscoveryAdmission(almanacs)
            if args.command == "discovery-topics":
                result = discovery.topic_page(
                    args.owner, parent=args.parent, limit=args.limit, offset=args.offset,
                    authorized=True)
            elif args.command == "discovery-sources":
                if not args.topic:
                    parser.error("discovery-sources requires --topic")
                result = discovery.source_page(
                    args.owner, args.topic, limit=args.limit, offset=args.offset,
                    authorized=True)
            else:
                if not args.source:
                    parser.error("discovery-receipts requires --source")
                result = discovery.provenance_page(
                    args.owner, args.source, limit=args.limit, offset=args.offset,
                    authorized=True)
        elif args.command == "mission-health":
            from .dragon_discovery_facets import DiscoveryFacetIndex
            result = DiscoveryFacetIndex(almanacs).health(
                args.owner, authorized=True)
        elif args.command == "mission-portfolio":
            from .dragon_discovery_portfolio import MissionPortfolio
            result = MissionPortfolio(almanacs).build(
                args.owner, _portfolio_request(args, parser),
                authorized=True, topic=args.topic)
        elif args.command in {"campaign-record", "campaign-inspect", "campaign-refresh"}:
            from .dragon_research_campaigns import DiscoveryCampaigns
            if not args.campaign:
                parser.error("campaign command requires --campaign")
            ledger = DiscoveryCampaigns(almanacs)
            if args.command == "campaign-record":
                result = ledger.record(
                    args.owner, args.campaign, _portfolio_request(args, parser),
                    authorized=True, topic=args.topic,
                    expected_parent=args.expected_parent)
            elif args.command == "campaign-refresh":
                result = ledger.refresh(
                    args.owner, args.campaign, authorized=True,
                    expected_parent=args.expected_parent)
            else:
                result = ledger.inspect(
                    args.owner, args.campaign, authorized=True)
        elif args.command == "mission-audit":
            from .dragon_discovery_facets import DiscoveryFacetIndex
            result = DiscoveryFacetIndex(almanacs).audit(
                args.owner, authorized=True, limit=args.limit,
                after_source=args.after_source)
        elif args.command == "mission-index":
            from .dragon_discovery_facets import DiscoveryFacetIndex
            result = DiscoveryFacetIndex(almanacs).refresh(
                args.owner, authorized=True, limit=args.limit,
                after_source=args.after_source)
        elif args.command == "mission-scout":
            from .dragon_discovery_mission import MissionSourceScout, SourceMission
            if not args.query:
                parser.error("mission-scout requires --query")
            result = MissionSourceScout(almanacs).propose(
                args.owner,
                SourceMission(args.query, platform=args.platform, genre=args.genre,
                              era=args.era, prefer_video=args.prefer_video,
                              limit=args.limit, scan_budget=args.scan_budget),
                authorized=True, topic=args.topic, indexed=args.indexed)
        elif args.command.startswith("delivery-"):
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
