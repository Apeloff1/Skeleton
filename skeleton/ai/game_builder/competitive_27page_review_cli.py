"""Authentic local user confirmation of the COMPLETE 27-page AI strategy.

Does not open source websites or infer consent. Uses an existing independent
studio session key supplied by the parent application environment. Manual
review is intentional: all three nine-page PDFs must be read and acknowledged.
"""
from __future__ import annotations
import argparse
import json
import os
import sys

from .competitive_27page_approval import (
    inspect_27page_packet,sign_user_27page_decision,
)
from .competitive_title_radar import ThreatRadarError,_sha,_date
from .competitive_4080_scrutiny import ROLE_NAMES
from .game_project_workspace import WorkspaceError
from .contracts import canonical_json


def parser():
    p=argparse.ArgumentParser(prog="python -m skeleton.ai.game_builder.competitive_27page_review_cli")
    p.add_argument("action",choices=("inspect","approve","revise","defer"))
    p.add_argument("--root",required=True)
    p.add_argument("--packet-digest",required=True)
    p.add_argument("--trusted-local-operator",action="store_true")
    for name in ROLE_NAMES:
        p.add_argument("--reviewed-"+name,action="store_true")
    p.add_argument("--as-of")
    p.add_argument("--session-context-digest")
    p.add_argument("--feedback",default="")
    return p


def main(argv=None):
    try:
        args=parser().parse_args(argv)
        if not args.trusted_local_operator:
            raise PermissionError("explicit authenticated local game studio user required")
        manifest=inspect_27page_packet(args.root,args.packet_digest,
                                       authorized=True)
        if args.action=="inspect":
            print(canonical_json(dict(
                original_id=manifest["original_id"],
                packet_digest=args.packet_digest,
                role_pdf_pages=manifest["role_final_pdf_pages"],
                total_unique_pages=27,
                scheduled_probes=4080,
                separate_review_obligations=12240,
                empirically_measured=manifest["empirical_measurements_verified"],
                needs_explicit_whole_set_user_confirmation=True)))
            return 0
        if not all(getattr(args,"reviewed_"+role) for role in ROLE_NAMES):
            raise ThreatRadarError("read all three nine-page AI PDFs before deciding")
        if not args.as_of or not args.session_context_digest:
            raise ThreatRadarError("explicit UTC decision time and studio session context needed")
        _date(args.as_of)
        _sha(args.session_context_digest,"user session context")
        raw=os.environ.get("SKELETON_GAME_PLAN_SESSION_KEY_HEX","")
        try:
            key=bytes.fromhex(raw)
        except ValueError as exc:
            raise ThreatRadarError("host-controlled session key not configured") from exc
        if len(key)<32:
            raise ThreatRadarError("authenticated host must provide 256-bit or stronger session secret")
        record=sign_user_27page_decision(
            args.root,args.packet_digest,decision=args.action,
            feedback=args.feedback,signed_at=args.as_of,
            user_session_key=key,
            user_context_digest=args.session_context_digest,
            reviewed_roles=tuple(sorted(ROLE_NAMES)),authorized=True)
        print(canonical_json(dict(
            status="user_decision_recorded",
            packet_digest=record.packet_digest,
            decision=record.decision,submitted_at=record.submitted_at,
            complete_role_set=list(record.reviewed_roles),
            automatic_game_edits=False,
            automatic_weight_updates=False,
            next_step="repeat_full_three_round_wider_research"
                      if args.action=="revise" else
                      "separately_authorized_original_game_build"
                      if args.action=="approve" else "defer")))
        return 0
    except (ThreatRadarError,PermissionError,WorkspaceError,
            ValueError,OSError,TypeError,KeyError) as exc:
        print(f"error: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["parser","main"]
