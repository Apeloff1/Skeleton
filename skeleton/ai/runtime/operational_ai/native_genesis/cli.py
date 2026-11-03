"""Operator-only native genesis tool, no network or automatic model serving."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from .errors import GenesisRejected, refuse
from .policy import GenesisPolicy
from .doctor import check
from .factory import initialize_native
from .checkpoint_store import publish_genesis
from .smoke import run_graph_smoke
from .training_bridge import train_candidate_from_genesis
from .evaluation_bridge import evaluate_pair
from .source import verify_source
from .vector_runner import run_all
from .canonical import required_sha


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Offline original-data native TinyTransformer genesis")
    mode=p.add_mutually_exclusive_group(required=True)
    for name in ("doctor","bootstrap","smoke","train","evaluate","vectors"):
        mode.add_argument("--"+name,action="store_true")
    p.add_argument("--approve-candidate-only",action="store_true")
    p.add_argument("--run-id",default="original_genesis_001")
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--dim",type=int,default=16)
    p.add_argument("--context",type=int,default=128)
    p.add_argument("--heads",type=int,default=2)
    p.add_argument("--layers",type=int,default=1)
    p.add_argument("--feed-forward",type=int,default=64)
    p.add_argument("--max-vocab",type=int,default=4096)
    p.add_argument("--maximum-model-bytes",type=int,default=256000000)
    p.add_argument("--max-optimizer-steps",type=int,default=32000)
    p.add_argument("--minimum-frequency",type=int,default=1)
    p.add_argument("--minimum-known-ppm",type=int,default=900000)
    p.add_argument("--learning-rate-ppm",type=int,default=10000)
    p.add_argument("--batch-lines",type=int,default=8)
    p.add_argument("--maximum-wall-ms",type=int,default=3600000)
    p.add_argument("--position-mode",default="rope")
    p.add_argument("--norm",default="ln")
    p.add_argument("--ffn",default="gelu")
    p.add_argument("--genesis-dir",type=Path)
    p.add_argument("--candidate-dir",type=Path)
    p.add_argument("--state-dir",type=Path)
    p.add_argument("--trainer-code-sha256")
    p.add_argument("--champion-checkpoint-sha256")
    p.add_argument("--champion-model-sha256")
    p.add_argument("--candidate-checkpoint-sha256")
    p.add_argument("--candidate-model-sha256")
    p.add_argument("--partition",choices=("validation","holdout"),default="validation")
    p.add_argument("--max-new-tokens",type=int,default=32)
    return p


def _policy(args)->GenesisPolicy:
    return GenesisPolicy(
        run_id=args.run_id,seed=args.seed,dim=args.dim,ctx=args.context,
        n_heads=args.heads,n_layers=args.layers,d_ff=args.feed_forward,
        max_vocab=args.max_vocab,maximum_model_bytes=args.maximum_model_bytes,
        max_optimizer_steps=args.max_optimizer_steps,
        minimum_document_frequency=args.minimum_frequency,
        minimum_known_fraction_ppm=args.minimum_known_ppm,
        learning_rate_ppm=args.learning_rate_ppm,batch_lines=args.batch_lines,
        maximum_wall_ms=args.maximum_wall_ms,position_mode=args.position_mode,
        norm=args.norm,ffn_kind=args.ffn,
        operator_approved=args.approve_candidate_only,candidate_only=True,
    )


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if args.vectors:
            result=run_all()
        else:
            policy=_policy(args)
            if args.doctor:
                result=check(policy)
            elif args.evaluate:
                if not (args.genesis_dir and args.candidate_dir and
                        args.champion_checkpoint_sha256 and args.champion_model_sha256 and
                        args.candidate_checkpoint_sha256 and args.candidate_model_sha256):
                    refuse("evaluation-arguments")
                result=evaluate_pair(
                    verify_source(),
                    champion_directory=args.genesis_dir.absolute(),
                    candidate_directory=args.candidate_dir.absolute(),
                    champion_checkpoint_sha256=args.champion_checkpoint_sha256,
                    champion_model_sha256=args.champion_model_sha256,
                    candidate_checkpoint_sha256=args.candidate_checkpoint_sha256,
                    candidate_model_sha256=args.candidate_model_sha256,
                    partition=args.partition,max_new_tokens=args.max_new_tokens,
                ).report()
            else:
                # Deny missing storage, trainer authority or other arguments
                # before source scanning or allocating any native model tensors.
                if args.bootstrap and args.genesis_dir is None:
                    refuse("genesis-directory-required")
                if args.train:
                    if not (args.genesis_dir and args.candidate_dir and args.state_dir
                            and args.trainer_code_sha256):
                        refuse("training-arguments")
                    required_sha(args.trainer_code_sha256,"trainer-code")
                model=initialize_native(policy)
                if args.smoke:
                    result=run_graph_smoke(
                        model.runtime,exact_model_sha256=model.runtime.model_digest
                    ).report()
                elif args.bootstrap:
                    if args.genesis_dir is None:
                        refuse("genesis-directory-required")
                    result=publish_genesis(args.genesis_dir.absolute(),model)
                elif args.train:
                    if not (args.genesis_dir and args.candidate_dir and args.state_dir
                            and args.trainer_code_sha256):
                        refuse("training-arguments")
                    required_sha(args.trainer_code_sha256,"trainer-code")
                    result=train_candidate_from_genesis(
                        model,trainer_code_sha256=args.trainer_code_sha256,
                        bootstrap_directory=args.genesis_dir.absolute(),
                        candidate_directory=args.candidate_dir.absolute(),
                        state_directory=args.state_dir.absolute(),
                    ).report()
                else:
                    refuse("unknown-genesis-mode")
        print(json.dumps(result,sort_keys=True,ensure_ascii=True))
        return 0 if result.get("failed",0)==0 else 2
    except (GenesisRejected,OSError,ValueError,RuntimeError,UnicodeError) as exc:
        error=getattr(exc,"code",type(exc).__name__)
        print(json.dumps({
            "status":"held","reason":error,
            "model_quality_verified":False,
            "release_certified":False,
        },sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
