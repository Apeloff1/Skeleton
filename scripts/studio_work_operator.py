"""Guarded operator CLI for the persistent, local original studio supervisor.

Tokens are loaded from the environment, never passed through argv or printed.
This does not dispatch OS commands, background jobs, GitHub Actions, or publish
games. It manages only source-bound, operator-authorized design work claims.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from skeleton.ai.game_builder.studio_ecosystem_supervisor import StudioSupervisor
from skeleton.ai.game_builder.studio_ecosystem_preview_worker import compile_and_spool_preview
from skeleton.ai.game_builder.studio_ecosystem_spool_audit import audit_artifact_spool
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def _bytes(path: Path):
    if path.is_symlink() or not path.is_file():
        raise StudioQuestError("only regular, nonlinked source artifacts may be submitted")
    flags = os.O_RDONLY
    if hasattr(os,"O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with os.fdopen(os.open(path,flags),"rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise StudioQuestError("submitted artifact is not a regular file")
        while chunk:=stream.read(1024*1024):
            yield chunk


def _token(parser: argparse.ArgumentParser) -> str:
    token=os.environ.get("SKELETON_STUDIO_WORK_TOKEN","")
    if not token:
        parser.error("SKELETON_STUDIO_WORK_TOKEN must be configured privately")
    return token


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Manage private source-bound studio work")
    parser.add_argument("--root",type=Path,required=True,help="Existing owner-only journal folder")
    parser.add_argument("--project",required=True,help="Registered original studio project")
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("status")
    commands.add_parser("audit-spool")
    commands.add_parser("preview")
    c=commands.add_parser("claim")
    c.add_argument("--task",required=True)
    c.add_argument("--worker",required=True)
    s=commands.add_parser("submit")
    s.add_argument("--task",required=True)
    s.add_argument("--worker",required=True)
    s.add_argument("--artifact",type=Path,required=True)
    r=commands.add_parser("review")
    r.add_argument("--task",required=True)
    r.add_argument("--reviewer",required=True)
    decision=r.add_mutually_exclusive_group(required=True)
    decision.add_argument("--accept",action="store_true")
    decision.add_argument("--reject",action="store_true")
    rcv=commands.add_parser("recover")
    rcv.add_argument("--task",required=True)
    rcv.add_argument("--former-worker",required=True)
    rcv.add_argument("--attempt",type=int,required=True)
    rcv.add_argument("--operator",required=True)
    hold=commands.add_parser("pause")
    hold.add_argument("--operator",required=True)
    cont=commands.add_parser("resume-admission")
    cont.add_argument("--operator",required=True)
    args=parser.parse_args(argv)
    try:
        supervisor=StudioSupervisor(args.root,args.project,authorized=True)
        journal=supervisor.journal
        if args.command=="status":
            result=supervisor.resume(authorized=True)
        elif args.command=="audit-spool":
            result=audit_artifact_spool(supervisor.spool,authorized=True)
        elif args.command=="preview":
            result=compile_and_spool_preview(journal,supervisor.spool,authorized=True)
        elif args.command=="claim":
            supervisor.claim(args.task,worker=args.worker,
                             token=_token(parser),authorized=True)
            result={"task_id":args.task,"claimed":True,"release_certified":False}
        elif args.command=="submit":
            result=supervisor.submit(args.task,worker=args.worker,token=_token(parser),
                                     chunks=_bytes(args.artifact),authorized=True)
        elif args.command=="review":
            result=supervisor.review(args.task,reviewer=args.reviewer,
                                      accepted=args.accept,authorized=True)
        elif args.command=="recover":
            supervisor._fence()
            journal.recover_claim(args.task,former_worker=args.former_worker,
                                  expected_attempt=args.attempt,operator=args.operator,
                                  authorized=True)
            result={"task_id":args.task,"returned_to_pending":True,
                    "release_certified":False}
        elif args.command in ("pause","resume-admission"):
            supervisor._fence()
            paused=args.command=="pause"
            journal.set_paused(paused,operator=args.operator,authorized=True)
            result={"admission_paused":paused,"release_certified":False}
        else:
            parser.error("unsupported command")
    except (StudioQuestError,ValueError,PermissionError,OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result,sort_keys=True,ensure_ascii=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
