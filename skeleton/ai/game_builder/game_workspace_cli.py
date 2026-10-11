"""Supervised AI game studio: original project trees, targeted patches, UI.

Local operations do not run generated scripts or change a remote repository.
Jeeves/Dragon can submit a proposed source body to 'propose', but only the
human-reviewed 'commit' action mutates the selected current project.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import webbrowser

from .contracts import canonical_json
from .game_project_workspace import (
    GameWorkspace,WorkspaceError,SOURCE_MAX,
)
from .game_workspace_server import create_workspace_server,StudioServerError


def parser():
    cli=argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.game_workspace_cli",
        description="Original AI game studio: prior genres, editable current game, immutable demos.",
    )
    cmd=cli.add_subparsers(dest="command",required=True)
    init=cmd.add_parser("init",help="Initialize brand-new local 3-tree studio")
    init.add_argument("--root",required=True)
    init.add_argument("--trusted-local-operator",action="store_true")
    for name in ("create","tree","files","read","propose","commit",
                 "archive","demo","autoload","select","serve"):
        p=cmd.add_parser(name)
        p.add_argument("--root",required=True)
        if name not in {"tree","files","read","serve"}:
            p.add_argument("--trusted-local-operator",action="store_true")
        if name=="create":
            p.add_argument("--project",required=True)
            p.add_argument("--genre",required=True)
        elif name=="select":
            p.add_argument("--project",required=True)
        elif name=="files":
            p.add_argument("--tree",required=True,
                           choices=("current","previous","demos"))
            p.add_argument("--project",required=True)
        elif name=="read":
            p.add_argument("--tree",required=True,
                           choices=("current","previous","demos"))
            p.add_argument("--project",required=True)
            p.add_argument("--path",required=True)
        elif name=="propose":
            p.add_argument("--project",required=True)
            p.add_argument("--path",required=True,
                           help="Exact relative source path, no folder mutation")
            p.add_argument("--file",required=True,
                           help="AI- or user-authored replacement source on local disk")
            p.add_argument("--expected-sha256",required=True)
            p.add_argument("--reason",required=True)
            p.add_argument("--author",choices=("human","jeeves","dragon"),
                           default="human")
        elif name=="commit":
            p.add_argument("--proposal-id",required=True)
            p.add_argument("--human-reviewed",action="store_true")
        elif name in {"archive","demo"}:
            p.add_argument("--project",required=True)
            p.add_argument("--genre")
        elif name=="autoload":
            p.add_argument("--genre",required=True)
            p.add_argument("--project",required=True,
                           help="New active original project name for previous genre")
        elif name=="serve":
            p.add_argument("--port",type=int,default=0)
            p.add_argument("--open-browser",action="store_true")
    return cli


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=="init":
            output=GameWorkspace.create(
                args.root,authorized=args.trusted_local_operator,
            ).tree()
        else:
            ws=GameWorkspace(args.root)
            if args.command=="tree":
                output=ws.tree()
            elif args.command=="create":
                output=ws.create_project(
                    args.project,args.genre,authorized=args.trusted_local_operator,
                )
            elif args.command=="select":
                output=ws.select_project(
                    args.project,authorized=args.trusted_local_operator,
                )
            elif args.command=="files":
                output=dict(files=[x.payload() for x in
                                  ws.files(args.tree,args.project)])
            elif args.command=="read":
                output=ws.read(args.tree,args.project,args.path)
            elif args.command=="propose":
                path=Path(args.file)
                if (path.is_symlink() or not path.is_file()
                        or path.stat().st_size>SOURCE_MAX):
                    raise WorkspaceError("AI submitted source must be bounded real local file")
                body=path.read_text(encoding="utf-8")
                output=ws.propose(
                    args.project,args.path,body,
                    expected_sha256=args.expected_sha256,
                    reason=f"Author {args.author}: {args.reason}",
                    authorized=args.trusted_local_operator,
                )
                output["proposed_by"]=args.author
                output["not_auto_executed"]=True
            elif args.command=="commit":
                output=ws.commit(
                    args.proposal_id,
                    human_approved=args.human_reviewed,
                    authorized=args.trusted_local_operator,
                )
            elif args.command in {"archive","demo"}:
                output=ws.archive(
                    args.project,genre=args.genre,
                    demo=args.command=="demo",
                    authorized=args.trusted_local_operator,
                )
            elif args.command=="autoload":
                output=ws.autoload_previous(
                    args.genre,args.project,authorized=args.trusted_local_operator,
                )
            elif args.command=="serve":
                server=create_workspace_server(ws,port=args.port)
                host,port=server.server_address
                url=f"http://{host}:{port}/"
                print(canonical_json({
                    "schema":"skeleton.game_builder.visual_studio_receipt.v1",
                    "url":url,"loopback_only":True,
                    "project_trees":["previous","current","demos"],
                    "server_side_ai_tool_execution":False,
                    "edits_require_review_and_explicit_commit":True,
                }),flush=True)
                if args.open_browser:
                    webbrowser.open(url)
                try:
                    server.serve_forever(poll_interval=0.1)
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
                return 0
            else:
                raise WorkspaceError("unrecognized workbench mode")
        print(canonical_json(output))
        return 0
    except (WorkspaceError,StudioServerError,PermissionError,
            ValueError,OSError,UnicodeError) as exc:
        print(f"error: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

__all__=["parser","main"]
