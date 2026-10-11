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
from .quest_scene_forge import read_director_blueprint
from .quest_director_solver import solve_quest
from .npc_witness_quest_engine import observe_story
from .competitive_mirror_training import run_mirror_competition
from .game_learning_almanac import (
    AlmanacError,build_curriculum,build_game_tester_curriculum,quarantine_curriculum,
)
from .game_tester_almanac import PlaytestError,test_game_personas,TEST_FAMILIES
from .game_training_flow import (
    TrainingFlowError,load_quarantined_batches,plan_training_flow,
    materialize_training_flow,train_isolated_review_ranker,
)


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
                 "archive","demo","autoload","fork-demo","select","serve","review-game",
                 "playtest-game","train-dataset"):
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
        elif name=="fork-demo":
            p.add_argument("--reference",required=True)
            p.add_argument("--project",required=True)
        elif name=="autoload":
            p.add_argument("--genre",required=True)
            p.add_argument("--project",required=True,
                           help="New active original project name for previous genre")
        elif name=="serve":
            p.add_argument("--port",type=int,default=0)
            p.add_argument("--open-browser",action="store_true")
        elif name=="review-game":
            p.add_argument("--director-blueprint",required=True)
            p.add_argument("--population",type=int,default=48)
            p.add_argument("--active-budget",type=int,default=24)
            p.add_argument("--ambient-budget",type=int,default=24)
            p.add_argument("--witness-limit",type=int,default=32)
            p.add_argument("--mirror-attempts",type=int,default=36)
            p.add_argument("--quest-key",default="quest_00")
            p.add_argument("--skip-quarantine",action="store_true")
        elif name=="playtest-game":
            p.add_argument("--director-blueprint",required=True)
            p.add_argument("--quest-key",default="quest_00")
            p.add_argument("--testers",type=int,default=5)
            p.add_argument("--attack-families",type=int,default=len(TEST_FAMILIES),
                           help="Use first N independently implemented fault families")
            p.add_argument("--quarantine-learning",action="store_true")
        elif name=="train-dataset":
            p.add_argument("--shard-size",type=int,default=32)
            p.add_argument("--per-project-cap",type=int,default=256)
            p.add_argument("--epochs",type=int,default=35)
            p.add_argument("--dry-run",action="store_true")

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
            elif args.command=="fork-demo":
                output=ws.fork_demo(
                    args.reference,args.project,
                    authorized=args.trusted_local_operator,
                )
            elif args.command=="autoload":
                output=ws.autoload_previous(
                    args.genre,args.project,authorized=args.trusted_local_operator,
                )
            elif args.command=="playtest-game":
                if not args.trusted_local_operator:
                    raise PermissionError("independent playtest replay requires operator authority")
                if type(args.attack_families) is not int or not 1<=args.attack_families<=len(TEST_FAMILIES):
                    raise PlaytestError("explicit adversarial family limit 1..24 required")
                world=read_director_blueprint(args.director_blueprint,human_reviewed=True)
                almanac=test_game_personas(
                    world,args.quest_key,max_personas=args.testers,
                    mutation_families=TEST_FAMILIES[:args.attack_families],
                    authorized=True)
                if not almanac.passed:
                    raise PlaytestError("replay almanac discovered unhandled actual game faults")
                curriculum=build_game_tester_curriculum(almanac,authorized=True)
                stored=(quarantine_curriculum(curriculum,ws.root,authorized=True)
                        if args.quarantine_learning else None)
                output=dict(schema="skeleton.game_builder.playtest_cli_result.v1",
                            report=almanac.payload(),report_digest=almanac.digest,
                            curriculum_digest=curriculum.digest,
                            candidate_examples=len(curriculum.examples),
                            quarantined=stored,
                            model_training_executed=False)
            elif args.command=="train-dataset":
                if not args.trusted_local_operator:
                    raise PermissionError("model experiment and dataset publication require authority")
                sources=load_quarantined_batches(ws.root,authorized=True)
                plan=plan_training_flow(
                    sources,per_project_cap=args.per_project_cap,authorized=True)
                fit=train_isolated_review_ranker(
                    plan,epochs=args.epochs,authorized=True)
                shipped=(materialize_training_flow(
                    plan,ws.root,shard_size=args.shard_size,authorized=True)
                    if not args.dry_run else None)
                output=dict(schema="skeleton.game_builder.train_flow_cli_result.v1",
                            run_id=plan.run_id,selected_examples=len(plan.selected),
                            source_project_count=len(plan.source_projects),
                            per_split=dict((name,len(projects)) for name,projects in plan.split_projects),
                            training_experiment=fit,immutable_shards=shipped,
                            permanent_core_AI_weights_changed=False)
            elif args.command=="review-game":
                if not args.trusted_local_operator:
                    raise PermissionError("game mirror and training-candidate generation needs operator approval")
                world=read_director_blueprint(args.director_blueprint,
                                              human_reviewed=True)
                proof=solve_quest(world,args.quest_key,
                                 strategy="creative",authorized=True)
                campaign=observe_story(
                    world,proof.replay,population=args.population,
                    active_budget=args.active_budget,
                    ambient_budget=args.ambient_budget,
                    maximum_witnesses=args.witness_limit,
                    authorized=True,
                )
                mirror=run_mirror_competition(
                    world,proof.replay,campaign,population=args.population,
                    active_budget=args.active_budget,
                    ambient_budget=args.ambient_budget,
                    maximum_witnesses=args.witness_limit,
                    attempts=args.mirror_attempts,authorized=True,
                )
                if not mirror.passed:
                    raise WorkspaceError("adversarial game mirror has detected unhandled attack")
                curriculum=build_curriculum(mirror,campaign,authorized=True)
                quarantine=(quarantine_curriculum(curriculum,ws.root,
                             authorized=True) if not args.skip_quarantine else None)
                output=dict(
                    schema="skeleton.game_builder.original_review_run.v1",
                    world_digest=world.digest,mirror_digest=mirror.digest,
                    mirror_attempts=len(mirror.probes),
                    rejected_attacks=sum(p.detected for p in mirror.probes),
                    npc_witnesses=len(campaign.witnessed),
                    emergent_quests=len(campaign.opportunities),
                    training_candidates=len(curriculum.examples),
                    knowledge_split=curriculum.split,
                    quarantined_dataset=quarantine,
                    neural_model_weights_trained=False,
                    human_approval_for_promotion_pending=True,
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
    except (WorkspaceError,StudioServerError,AlmanacError,TrainingFlowError,
            PermissionError,ValueError,OSError,UnicodeError) as exc:
        print(f"error: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

__all__=["parser","main"]
