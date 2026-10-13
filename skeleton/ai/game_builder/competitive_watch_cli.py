"""Local CLI for governed competitive-title watch status and work queue.

This reads actual previously ingested Wiki/rights-cleared scan records.
It does NOT invent scores, fetch websites, trigger a crawler, invoke an LLM,
schedule background tasks or change an original title's code.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import sys

from .contracts import canonical_json
from .competitive_title_radar import ThreatRadarError,_id,_date
from .competitive_watch_book import CompetitionWatchBook
from .competitive_deep_archive import DeepEnemyArchive
from .game_project_workspace import WorkspaceError


def parser():
    cli=argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.competitive_watch_cli",
        description="Show evidence-backed competitor 'enemy' watch and quality demands")
    cli.add_argument("action",choices=("status","due","demands","deep"))
    cli.add_argument("--root",required=True)
    cli.add_argument("--original-id",required=True)
    cli.add_argument("--trusted-local-operator",action="store_true")
    cli.add_argument("--at",help="explicit UTC evaluation time YYYY-MM-DDTHH:MM:SSZ")
    return cli


def main(argv=None):
    try:
        args=parser().parse_args(argv)
        if not args.trusted_local_operator:
            raise PermissionError("competitor-watch inspection needs local operator approval")
        title=_id(args.original_id,"original ID")
        with CompetitionWatchBook(args.root) as book:
            history=book.history(title,authorized=True)
        if not history:
            raise ThreatRadarError("no verified competitor watch scans recorded for this title")
        current,digest=history[-1]
        observed=_date(current["as_of"])
        due=(observed+timedelta(hours=min(
            x["next_review_hours"] for x in current["assessments"])))
        at=_date(args.at) if args.at else None
        if at is not None and at<observed:
            raise ThreatRadarError("inspection clock cannot predate current state")
        watch={
            "schema":"skeleton.game_builder.local_competitor_status.v1",
            "original_id":title,"as_of":current["as_of"],
            "history_length":len(history),
            "journal_tip_digest":digest,
            "enemy_ids":[x["rival_id"] for x in current["assessments"]
                         if x["status"]=="enemy"],
            "watch_ids":[x["rival_id"] for x in current["assessments"]
                         if x["status"]=="watch"],
            "next_review_at":due.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "background_monitor_running":False,
            "new_Wiki_research_required_before_next_scan":True,
        }
        if args.action=="deep":
            with DeepEnemyArchive(args.root) as detailed:
                journal=detailed.history(title,authorized=True)
            if not journal:
                raise ThreatRadarError("deep enemy and genre evolution not yet reviewed and archived")
            data,entry_digest=journal[-1]
            dossiers=data["portfolio"]["enemy_dossiers"]
            result=dict(
                watch,deep_revision=data["revision"],
                deep_archive_digest=entry_digest,
                deep_research_root=data["source_knowledge_root"],
                active_enemy_dossiers=[
                    dict(
                        enemy_id=x["enemy_id"],platform=x["platform"],
                        genre_ancestry_generations=x["evolution"]["verified_generations"],
                        ancestry_complete=x["evolution"]["complete_competitor_coverage"],
                        source_research_gaps=x["unresolved_research"],
                        domain_facet_counts={
                            domain:sum(1 for p in x["analysis_scripts"]
                                       if p["axis"]==domain)
                            for domain in ("gameplay","graphics","sound","storyline")},
                        verified_weakspots=[
                            p["facet"] for p in x["facet_verdicts"]
                            if p["status"]=="verified_weakspot"],
                        incomplete_or_unmeasured=[
                            p["facet"] for p in x["facet_verdicts"]
                            if p["status"]=="insufficient_evidence"],
                        improvement_proposals=len(x["counterproposals"]),
                        all_ancestral_facets_outclassed=x[
                            "ancestral_frontier"]["complete_ancestry_outclassed"])
                    for x in dossiers],
                no_made_up_weakness_or_completed_build=True)
        elif args.action=="status":
            result=dict(watch,
                        all_threats=[dict(rival_id=x["rival_id"],
                                          status=x["status"],
                                          independent_groups=x["independent_groups"],
                                          overlap_bp=x["overlap_bp"],
                                          blockers=x["blockers"])
                                     for x in current["assessments"]])
        elif args.action=="demands":
            items=[]
            for report in current["delivery_reports"]:
                for demand in report["demands"]:
                    items.append(dict(
                        rival_id=demand["rival_id"],
                        axis=demand["axis"],priority=demand["priority"],
                        target_floor_bp=demand["target_floor_bp"],
                        original_direction=demand["original_direction"],
                        blockers=demand["blocked_reason"]))
            items.sort(key=lambda x:(-x["priority"],x["axis"],x["rival_id"]))
            result=dict(watch,outstanding_work=items,
                        no_automatic_asset_copy=True,
                        no_automatic_quality_claim=True)
        else:
            if at is None:
                raise ThreatRadarError("due requires --at with trusted UTC time")
            result=dict(watch,checked_at=args.at,review_due=at>=due,
                        fresh_Wiki_and_rights_packet_required=True)
        print(canonical_json(result))
        return 0
    except (ThreatRadarError,PermissionError,WorkspaceError,
            OSError,ValueError,TypeError) as exc:
        print(f"error: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["parser","main"]
