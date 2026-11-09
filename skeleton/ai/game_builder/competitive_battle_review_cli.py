"""Local manual approval / reconsideration of all three AI battle-plan PDFs.

This is an explicitly user-operated companion to the game studio; no model
may self-approve. A protected session signing key arrives from the host
environment and NEVER via command line, PDF contents or a chat message.
The host is responsible for authenticating the human and provisioning this
high-entropy session key. Role-PDF draft examples without a canonical local
publication manifest cannot be approved by this command.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .contracts import canonical_json
from .competitive_battle_approval import (
    inspect_all_three_pdfs,submit_user_packet_decision,
)
from .competitive_title_radar import ThreatRadarError,_date,_sha
from .game_project_workspace import WorkspaceError
from .competitive_tri_council import ROLES


def parser():
    cli=argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.competitive_battle_review_cli",
        description="Manually review the complete three-PDF council packet and record a user decision")
    cli.add_argument("action",choices=("inspect","approve","revise","defer"))
    cli.add_argument("--root",required=True)
    cli.add_argument("--packet-digest",required=True)
    cli.add_argument("--trusted-local-operator",action="store_true")
    cli.add_argument("--reviewed-dragon",action="store_true")
    cli.add_argument("--reviewed-jeeves",action="store_true")
    cli.add_argument("--reviewed-adversarial",action="store_true")
    cli.add_argument("--feedback",default="")
    cli.add_argument("--as-of",help="UTC timestamp required for a decision")
    cli.add_argument("--session-key-env",default="SKELETON_GAME_PLAN_SESSION_KEY_HEX")
    cli.add_argument("--session-context-digest")
    return cli


def main(argv=None):
    try:
        args=parser().parse_args(argv)
        if not args.trusted_local_operator:
            raise PermissionError("local human operator must authorize all review actions")
        manifest=inspect_all_three_pdfs(
            args.root,args.packet_digest,authorized=True)
        if args.action=="inspect":
            print(canonical_json(dict(
                status="AWAITING_EXPLICIT_USER_CONFIRMATION",
                packet_digest=args.packet_digest,
                original_id=manifest["original_id"],
                roles=sorted(manifest["role_document_sha256"]),
                pages_per_role=manifest["role_pages"],
                round_research_roots=manifest["round_research_roots"],
                approval_granted=False)))
            return 0
        if not all((args.reviewed_dragon,args.reviewed_jeeves,
                    args.reviewed_adversarial)):
            raise ThreatRadarError("user must separately acknowledge all three three-page role PDFs")
        if not args.as_of or not args.session_context_digest:
            raise ThreatRadarError("explicit UTC time and authenticated session context required")
        _date(args.as_of);_sha(args.session_context_digest,"local studio user context")
        # Never echo key contents, path or secret on success or failure.
        name=args.session_key_env
        if (not isinstance(name,str) or not name.startswith("SKELETON_")
                or not name.endswith("_HEX") or len(name)>90):
            raise ThreatRadarError("session key must be in a known protected environment name")
        value=os.environ.get(name,"")
        try:
            key=bytes.fromhex(value)
        except ValueError as exc:
            raise ThreatRadarError("invalid environment-provided session signature key") from exc
        if len(key)<32:
            raise ThreatRadarError("host must supply an authenticated 256-bit or stronger session key")
        record=submit_user_packet_decision(
            args.root,args.packet_digest,
            decision=args.action,feedback=args.feedback,
            authenticated_session_key=key,
            authenticated_session_context_digest=args.session_context_digest,
            reviewed_roles=tuple(sorted(ROLES)),as_of=args.as_of,
            authorized=True)
        print(canonical_json(dict(
            packet_digest=record.packet_digest,
            user_decision=record.decision,
            submitted_at=record.submitted_at,
            reviewed_roles=list(record.reviewed_roles),
            decision_digest=record.signature,
            auto_model_promotion=False,
            auto_implementation=False,
            next_step=("repeat_higher_effort_research_and_three_council_rounds"
                       if record.decision=="revise" else
                       "separately_authorized_original_game_implementation"
                       if record.decision=="approve" else "remain_pending"))))
        return 0
    except (ThreatRadarError,PermissionError,WorkspaceError,ValueError,
            OSError,KeyError,TypeError) as exc:
        # No auth token, private source path or packet contents are printed.
        print(f"error: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["parser","main"]
