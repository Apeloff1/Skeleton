"""Operational CLI for approved *local* game-reviewer models.

A real model is fitted only in the isolated training pipeline. Staging requires
frozen heldout evaluation; shadow requires six separately named reviewers;
'usage' and 'idle-pass' require fresh, independently replayed original games;
activation remains explicitly operator approved. The loop does not install,
modify or impersonate Dragon/Jeeves language-model parameters.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .contracts import canonical_json,canonical_digest
from .game_project_workspace import GameWorkspace
from .game_training_flow import (
    TrainingFlowError,load_quarantined_batches,plan_training_flow,
    train_isolated_review_ranker,materialize_training_flow,
from .game_reviewer_v2 import train_robust_game_reviewer
)
from .game_model_promotion import (
    PromotionError,PromotionStandard,evaluate_candidate,
)
from .game_reviewer_registry import (
    ReviewerRegistry,PromotionAttestation,ROLES,
)
from .quest_scene_forge import read_director_blueprint


def _structured_file(source: str,*,max_bytes: int=24000):
    path=Path(source)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>max_bytes:
        raise PromotionError("real bounded local human-reviewed JSON file required")
    try:
        doc=json.loads(path.read_bytes().decode("utf-8","strict"))
    except (ValueError,UnicodeError) as exc:
        raise PromotionError("ambiguous or malformed review evidence") from exc
    return doc


def parser():
    cmd=argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.game_model_cli",
        description="Adversarial model maturity and promotion for the LOCAL game-review classifier.",
    )
    commands=cmd.add_subparsers(dest="action",required=True)
    for name in ("evaluate","stage","approve","usage","idle-pass",
                 "activate","status","rollback","recover","predict"):
        p=commands.add_parser(name)
        p.add_argument("--root",required=True)
        if name!="status":
            p.add_argument("--trusted-local-operator",action="store_true")
        if name in {"evaluate","stage"}:
            p.add_argument("--epochs",type=int,default=75)
            p.add_argument("--feature-version",
                           choices=("robust_v2","baseline_v1"),default="robust_v2",
                           help="V2 normalized, adversarially augmented model by default")
            p.add_argument("--per-project-cap",type=int,default=256)
            p.add_argument("--minimum-balanced-accuracy",type=float,default=0.94)
            p.add_argument("--minimum-evidence-per-class",type=int,default=8)
            p.add_argument("--minimum-counterfactual-accuracy",type=float,default=0.98,
                           help="Strict default: prevent metadata-shortcut reviewer promotion; override only in an explicitly limited lab")
        elif name=="approve":
            p.add_argument("--reviewers-file",required=True)
        elif name in {"usage","idle-pass"}:
            p.add_argument("--director-blueprints",nargs="+",required=True,
                           help="At least two new original projects distinct from train/validation/test and past cohorts")
            p.add_argument("--quest-key",default="quest_00")
        elif name=="predict":
            p.add_argument("--game-digest",required=True)
            p.add_argument("--evidence-file",required=True)
        elif name=="rollback":
            p.add_argument("--reason",required=True)
    return cmd


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.action!="status" and not args.trusted_local_operator:
            raise PermissionError("reviewer model evolution needs explicit local operator authority")
        studio=GameWorkspace(args.root)
        registry=ReviewerRegistry(studio.root)
        if args.action=="status":
            state=registry.read_state()
            result=dict(schema="skeleton.game_builder.reviewer_status.v1",
                        phase=state["phase"],revision=state["revision"],
                        active_local_reviewer=state["active"],
                        shadow_candidate=state["candidate"],
                        usage_checked="usage" in state["observations"],
                        idle_checked="idle" in state["observations"],
                        review_roles=[row["role"] for row in state["attestations"]],
                        no_remote_llm_deployment=True,
                        no_hidden_hardware_activation=True)
        elif args.action in {"evaluate","stage"}:
            batches=load_quarantined_batches(studio.root,authorized=True)
            plan=plan_training_flow(
                batches,per_project_cap=args.per_project_cap,authorized=True)
            fit=(train_robust_game_reviewer(
                plan,epochs=args.epochs,authorized=True)
                if args.feature_version=="robust_v2" else
                train_isolated_review_ranker(
                    plan,epochs=args.epochs,authorized=True))
            standard=PromotionStandard(
                min_balanced_accuracy=args.minimum_balanced_accuracy,
                min_per_class=args.minimum_evidence_per_class,
                min_counterfactual_accuracy=args.minimum_counterfactual_accuracy)
            active=registry.read_state()["active"]
            champion=(registry._candidate(active)["policy"]
                      if active is not None else None)
            if args.action=="evaluate":
                evaluation=evaluate_candidate(
                    plan,fit,standard=standard,champion=champion,
                    authorized=True)
                result=dict(schema="skeleton.game_builder.review_evaluation_cli.v1",
                            evaluation=evaluation.payload(),
                            fit_executed=fit["training_performed"],
                            core_ai_model_changed=False)
            else:
                result=registry.stage(plan,fit,standard=standard,
                                      champion=champion,authorized=True)
        elif args.action=="approve":
            data=_structured_file(args.reviewers_file)
            if type(data) is not list or len(data)!=6:
                raise PromotionError("six explicit independent review attestations required")
            rows=tuple(PromotionAttestation(**row) for row in data)
            result=registry.authorize_shadow(rows,authorized=True)
        elif args.action in {"usage","idle-pass"}:
            paths=args.director_blueprints
            if not 2<=len(paths)<=8 or len(set(paths))!=len(paths):
                raise PromotionError("2..8 distinct original world blueprint paths required")
            worlds=tuple(
                read_director_blueprint(path,human_reviewed=True) for path in paths
            )
            result=registry.observe(
                worlds,mode="usage" if args.action=="usage" else "idle",
                quest_key=args.quest_key,authorized=True)
        elif args.action=="predict":
            evidence=_structured_file(args.evidence_file,max_bytes=12000)
            result=registry.score_active_game(
                evidence,game_digest=args.game_digest,authorized=True)
        elif args.action=="activate":
            result=registry.activate(authorized=True)
        elif args.action=="rollback":
            result=registry.abort(args.reason,authorized=True)
        elif args.action=="recover":
            state=registry.recover_interrupted(authorized=True)
            result=dict(status="recovered",revision=state["revision"],
                        phase=state["phase"],active=state["active"])
        else:
            raise PromotionError("unknown explicit original model promotion step")
        print(canonical_json(result))
        return 0
    except (PromotionError,TrainingFlowError,PermissionError,
            TypeError,ValueError,OSError) as exc:
        print(f"error: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["parser","main"]
