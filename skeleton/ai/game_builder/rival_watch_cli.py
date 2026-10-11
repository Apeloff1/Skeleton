"""Operator CLI for competing-title watch, adversarial priority and release gates.

Public polling is *not* a reviewed model signal. A separate human-approved
source receipt must supply specific observed mechanics before enemy tagging.
Usage:
  python -m skeleton.ai.game_builder.rival_watch_cli poll --config file.json --allow-network
  python -m skeleton.ai.game_builder.rival_watch_cli analyze --evidence input.json --trusted-reviewer
  python -m skeleton.ai.game_builder.rival_watch_cli signoff --evidence delivery.json --trusted-reviewer
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

from .contracts import canonical_json
from .rival_convergence_observatory import (
    CompetitiveError,DesignFacet,PlannedTitle,CompetitorTitle,PublicSignal,
    QualityMeasurement,DeliveryOrder,ConvergenceReport,DeliveryVerification,
    CompetitiveLedger,evaluate_convergence,verify_delivery,
)
from .rival_public_monitor import MonitoringError,poll_public_steam_titles


def _file(path:str,maximum=900_000):
    file=Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size>maximum:
        raise CompetitiveError("bounded regular non-symlink reviewed input required")
    def unique(items):
        result={}
        for name,value in items:
            if name in result:
                raise CompetitiveError("ambiguous repeated key in rival input")
            result[name]=value
        return result
    try:
        doc=json.loads(file.read_bytes().decode("utf-8","strict"),
                       object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           CompetitiveError("nonfinite public competitor input")))
    except (UnicodeError,ValueError,TypeError) as exc:
        raise CompetitiveError("malformed evidence file") from exc
    if type(doc) is not dict:
        raise CompetitiveError("top-level typed evidence object required")
    return doc


def _typed(cls,doc,*,sequence=()):
    if type(doc) is not dict:
        raise CompetitiveError("structured reviewed evidence required")
    # Python dataclasses reject unknown fields and missing fields.
    try:
        fields=cls.__dataclass_fields__
        if set(doc)!=set(fields):
            raise CompetitiveError(f"{cls.__name__}: exact evidence schema required")
        arguments=dict(doc)
        for field in sequence:
            if type(arguments[field]) is not list:
                raise CompetitiveError("bounded evidence arrays required")
            arguments[field]=tuple(arguments[field])
        return cls(**arguments)
    except (ValueError,TypeError,KeyError) as exc:
        raise CompetitiveError(f"invalid {cls.__name__} evidence") from exc


def _planned(doc):
    if type(doc) is not dict:
        raise CompetitiveError("typed precommitted planned game required")
    rows=doc.get("facets")
    if type(rows) is not list:
        raise CompetitiveError("planned original facets required")
    fields={x for x in PlannedTitle.__dataclass_fields__}
    if set(doc)!=(fields|{"schema"}) or doc.get("schema")!="skeleton.game_builder.planned_original_title.v1":
        raise CompetitiveError("no mutable or unidentified original game plan permitted")
    args={k:v for k,v in doc.items() if k!="schema"}
    args["facets"]=tuple(_typed(DesignFacet,item) for item in rows)
    if type(args["original_identity_pillars"]) is not list:
        raise CompetitiveError("original game identity commitments must be explicit")
    args["original_identity_pillars"]=tuple(args["original_identity_pillars"])
    return PlannedTitle(**args)


def _report(doc):
    if type(doc) is not dict:
        raise CompetitiveError("typed independently compared report required")
    digest=doc.get("report_digest")
    without={k:v for k,v in doc.items() if k not in {
        "report_digest","schema","strategic_enemy_label_is_not_an_accusation",
        "no_competitor_expression_or_assets_copied",
        "protected_original_identity_unchanged",
        "competitor_scores_are_not_inferred_from_news",
        "automatic_delivery_or_model_promotion"}}
    try:
        without["convergent_features"]=tuple(without["convergent_features"])
        without["watch_reasons"]=tuple(without["watch_reasons"])
        without["orders"]=tuple(_typed(DeliveryOrder,v) for v in without["orders"])
        report=ConvergenceReport(**without)
    except (TypeError,ValueError,KeyError) as exc:
        raise CompetitiveError("invalid report revision") from exc
    if report.payload()!=doc or report.digest!=digest:
        raise CompetitiveError("competitive report evidence tampered")
    return report


def parser():
    p=argparse.ArgumentParser(prog="python -m skeleton.ai.game_builder.rival_watch_cli")
    sub=p.add_subparsers(dest="action",required=True)
    poll=sub.add_parser("poll")
    poll.add_argument("--config",required=True)
    poll.add_argument("--allow-network",action="store_true")
    analyze=sub.add_parser("analyze")
    analyze.add_argument("--evidence",required=True)
    analyze.add_argument("--trusted-reviewer",action="store_true")
    analyze.add_argument("--ledger")
    analyze.add_argument("--expected-head",default=None)
    delivery=sub.add_parser("signoff")
    delivery.add_argument("--evidence",required=True)
    delivery.add_argument("--trusted-reviewer",action="store_true")
    return p


def main(argv=None):
    a=parser().parse_args(argv)
    try:
        if a.action=="poll":
            cfg=_file(a.config,128_000)
            if (set(cfg)!={"schema","polling_enabled","titles"}
                    or cfg["schema"]!="skeleton.game_builder.competitor_watch_config.v1"
                    or type(cfg["polling_enabled"]) is not bool
                    or type(cfg["titles"]) is not list
                    or len(cfg["titles"])>64):
                raise CompetitiveError("reviewed bounded public-title watch config required")
            titles=tuple(_typed(CompetitorTitle,t) for t in cfg["titles"])
            if cfg["polling_enabled"] and not a.allow_network:
                raise PermissionError("scheduled public polling needs explicit network permission")
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            result=poll_public_steam_titles(
                titles if cfg["polling_enabled"] else (),
                observed_at=timestamp,authorized=True,
                fetcher=None).payload()
        elif a.action=="analyze":
            if not a.trusted_reviewer:
                raise PermissionError("authentic source review must occur before rival tagging")
            doc=_file(a.evidence)
            if set(doc)!={"schema","plan","rival","signals","benchmarks"} or doc["schema"]!="skeleton.game_builder.competitor_analysis_request.v1":
                raise CompetitiveError("exact review request schema required")
            plan=_planned(doc["plan"])
            rival=_typed(CompetitorTitle,doc["rival"])
            if type(doc["signals"]) is not list or type(doc["benchmarks"]) is not list:
                raise CompetitiveError("complete source and benchmark arrays required")
            signals=tuple(_typed(PublicSignal,s,sequence=("reviewed_feature_ids",))
                          for s in doc["signals"])
            benchmark=tuple(_typed(QualityMeasurement,q)
                            for q in doc["benchmarks"])
            report=evaluate_convergence(
                plan,rival,signals,benchmark,authorized=True)
            result=report.payload()
            if a.ledger:
                with CompetitiveLedger(a.ledger) as ledger:
                    result["audit_head"]=ledger.append(
                        report,expected_head=a.expected_head,authorized=True)
        else:
            if not a.trusted_reviewer:
                raise PermissionError("only independent actual game delivery may pass verification")
            doc=_file(a.evidence)
            if set(doc)!={"schema","plan","report","delivery"} or doc["schema"]!="skeleton.game_builder.competitor_delivery_request.v1":
                raise CompetitiveError("exact delivery source evidence required")
            plan=_planned(doc["plan"])
            report=_report(doc["report"])
            raw=doc["delivery"]
            if type(raw) is not dict or set(raw)!=set(DeliveryVerification.__dataclass_fields__):
                raise CompetitiveError("complete delivery proof shape required")
            if type(raw["measurements"]) is not list:
                raise CompetitiveError("bounded measured gameplay receipt list required")
            proof=DeliveryVerification(
                **{**raw,"measurements":tuple(
                    _typed(QualityMeasurement,m) for m in raw["measurements"])})
            result=verify_delivery(plan,report,proof,authorized=True)
        print(canonical_json(result))
        return 0
    except (CompetitiveError,MonitoringError,PermissionError,OSError,
            ValueError,TypeError,KeyError) as exc:
        print("error: "+type(exc).__name__+": "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["parser","main"]
