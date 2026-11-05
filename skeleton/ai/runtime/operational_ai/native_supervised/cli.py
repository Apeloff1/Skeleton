"""Operator-owned offline SFT: source -> actual SGD -> private candidate -> actual probes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from .canonical import require_sha
from .errors import SupervisedRejected,reject
from .policy import SupervisedPolicy
from .doctor import diagnose
from .source_manifest import generate
from .bootstrap import initialize_aligned_model
from .run_director import bootstrap,deliver
from .probe_director import probe
from .compare_director import compare_checkpoints
from .challenge_catalog import inventory as challenge_inventory
from .privacy import require_public


def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(
        description="Real offline completion-only native AI supervised training and independent probes"
    )
    kind=p.add_mutually_exclusive_group(required=True)
    for name in ("inventory","doctor","bootstrap","train","probe","compare","capability","smoke"):
        kind.add_argument("--"+name,action="store_true")
    p.add_argument("--approve-candidate-only",action="store_true")
    p.add_argument("--run-id",default="native_sft_001")
    p.add_argument("--seed",type=int,default=29)
    p.add_argument("--dimension",type=int,default=16)
    p.add_argument("--context",type=int,default=256)
    p.add_argument("--heads",type=int,default=2)
    p.add_argument("--layers",type=int,default=1)
    p.add_argument("--feed-forward",type=int,default=32)
    p.add_argument("--max-vocabulary",type=int,default=8192)
    p.add_argument("--epochs",type=int,default=1)
    p.add_argument("--batch-examples",type=int,default=8)
    p.add_argument("--learning-rate-ppm",type=int,default=2500)
    p.add_argument("--max-optimizer-steps",type=int,default=48000)
    p.add_argument("--max-wall-ms",type=int,default=3600000)
    p.add_argument("--max-checkpoint-bytes",type=int,default=256000000)
    p.add_argument("--minimum-known-ppm",type=int,default=1000000)
    p.add_argument("--genesis-directory",type=Path)
    p.add_argument("--candidate-directory",type=Path)
    p.add_argument("--state-directory",type=Path)
    p.add_argument("--checkpoint-sha256")
    p.add_argument("--model-sha256")
    p.add_argument("--tokenizer-sha256")
    p.add_argument("--champion-directory",type=Path)
    p.add_argument("--champion-checkpoint-sha256")
    p.add_argument("--champion-model-sha256")
    p.add_argument("--champion-tokenizer-sha256")
    p.add_argument("--case-start",type=int,default=0)
    p.add_argument("--case-count",type=int,default=24)
    p.add_argument("--max-new-tokens",type=int,default=32)
    return p


def _policy(args)->SupervisedPolicy:
    return SupervisedPolicy(
        run_id=args.run_id,seed=args.seed,dimension=args.dimension,
        context=args.context,heads=args.heads,layers=args.layers,
        feed_forward=args.feed_forward,max_vocabulary=args.max_vocabulary,
        epochs=args.epochs,batch_examples=args.batch_examples,
        learning_rate_ppm=args.learning_rate_ppm,
        max_optimizer_steps=args.max_optimizer_steps,
        max_wall_ms=args.max_wall_ms,
        max_checkpoint_bytes=args.max_checkpoint_bytes,
        min_train_known_ppm=args.minimum_known_ppm,
        operator_approved=args.approve_candidate_only,
    )


def main(argv:list[str]|None=None)->int:
    args=parser().parse_args(argv)
    try:
        if args.inventory:
            challenges=challenge_inventory()
            source=generate()
            report={
                "schema":"skeleton.native-supervised.operator-inventory.v1",
                "challenge_count":challenges["count"],
                "challenge_domains":len(challenges["domains"]),
                "challenge_source_sha256":challenges["source_sha256"],
                "training_source_sha256":source.training_sha256,
                "train_only":True,"optimizer_steps":0,
                "release_certified":False,
            }
        elif args.probe:
            if not (args.candidate_directory and args.checkpoint_sha256
                    and args.model_sha256 and args.tokenizer_sha256):
                reject("operator-probe-arguments")
            report=probe(
                args.candidate_directory.absolute(),args.checkpoint_sha256,
                model_sha256=args.model_sha256,
                tokenizer_sha256=args.tokenizer_sha256,
                start=args.case_start,count=args.case_count,
                max_new_tokens=args.max_new_tokens,
            )
        elif args.compare:
            if not all((
                args.candidate_directory,args.checkpoint_sha256,
                args.model_sha256,args.tokenizer_sha256,
                args.champion_directory,args.champion_checkpoint_sha256,
                args.champion_model_sha256,args.champion_tokenizer_sha256,
            )):
                reject("operator-comparison-arguments")
            report=compare_checkpoints(
                args.champion_directory.absolute(),
                args.champion_checkpoint_sha256,
                args.champion_model_sha256,args.champion_tokenizer_sha256,
                args.candidate_directory.absolute(),
                args.checkpoint_sha256,args.model_sha256,args.tokenizer_sha256,
                start=args.case_start,count=args.case_count,
                max_new_tokens=args.max_new_tokens,
            )
        else:
            policy=_policy(args)
            if args.doctor:
                report=diagnose(policy)
            elif args.capability:
                from .capability_gaps import describe
                instance=initialize_aligned_model(policy)
                report=describe(instance.runtime)
            elif args.smoke:
                from .model_smoke import native_smoke
                instance=initialize_aligned_model(policy)
                report=native_smoke(instance.runtime,
                                    expected_model_sha256=instance.runtime.model_digest)
            elif args.bootstrap:
                if not args.genesis_directory:
                    reject("operator-genesis-directory")
                report=bootstrap(
                    policy,directory=args.genesis_directory.absolute(),
                )
            elif args.train:
                if not args.candidate_directory or not args.state_directory:
                    reject("operator-training-directories")
                report=deliver(
                    policy,candidate_directory=args.candidate_directory.absolute(),
                    state_directory=args.state_directory.absolute(),
                ).report()
            else:
                reject("operator-mode")
        require_public(report)
        print(json.dumps(report,sort_keys=True,ensure_ascii=True,allow_nan=False))
        return 0
    except (SupervisedRejected,OSError,ValueError,RuntimeError,UnicodeError) as exc:
        print(json.dumps({
            "status":"held",
            "reason":getattr(exc,"code",type(exc).__name__),
            "candidate_only":True,
            "production_authorized":False,
            "release_certified":False,
        },sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
