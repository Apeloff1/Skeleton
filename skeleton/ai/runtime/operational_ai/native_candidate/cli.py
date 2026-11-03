"""Operator-only offline native candidate training — never automatic promotion."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from .catalog import DOMAINS, inventory
from .errors import CandidateRejected, deny
from .factory import qualify_preflight, train_native
from .plan import TrainingPlan
from .strict import sha


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Real Skeleton native candidate-only SGD")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--train-native", action="store_true")
    mode.add_argument("--doctor", action="store_true")
    result.add_argument("--checkpoint", type=Path)
    result.add_argument("--sha256")
    result.add_argument("--model-sha256")
    result.add_argument("--tokenizer-sha256")
    result.add_argument("--license")
    result.add_argument("--run-id", default="original_candidate")
    result.add_argument("--trainer-code-sha256")
    result.add_argument("--model-name", default="original_native")
    result.add_argument("--output-directory", type=Path)
    result.add_argument("--state-directory", type=Path)
    result.add_argument("--candidate-sha256")
    result.add_argument("--approve-candidate-only", action="store_true")
    result.add_argument("--learning-rate-ppm", type=int, default=10000)
    result.add_argument("--maximum-steps", type=int, default=16384)
    result.add_argument("--batch-lines", type=int, default=8)
    result.add_argument("--maximum-total-ms", type=int, default=3600000)
    result.add_argument("--min-known-token-fraction-ppm", type=int, default=800000)
    return result


def _load_native(args):
    from skeleton.ai.runtime.operational_ai.model.catalog import ModelCatalog, ModelArtifact
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    if not (args.checkpoint and args.sha256 and args.model_sha256
            and args.tokenizer_sha256 and args.license):
        deny("model-arguments-required")
    file = args.checkpoint.absolute()
    sha(args.sha256, "checkpoint-sha")
    sha(args.model_sha256, "native-model-sha")
    sha(args.tokenizer_sha256, "tokenizer-sha")
    artifact = ModelArtifact(
        args.model_name, file.name, args.sha256, file.stat().st_size,
        args.license, tokenizer_sha256=args.tokenizer_sha256,
    )
    descriptor, raw = ModelCatalog(file.parent, [artifact]).verified_bytes(args.model_name)
    native = NativeLLMRuntime.restore_json(raw.decode("utf-8"))
    if native.model_digest != args.model_sha256 or native.tokenizer.digest != args.tokenizer_sha256:
        deny("model-tokenizer-identity-mismatch")
    native.assert_model_unchanged()
    return native


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.inventory:
            data = inventory()
            print(json.dumps({
                "schema": data["schema"], "count": data["count"],
                "domains": data["domains"], "model_trained": False,
                "release_certified": False,
            }, sort_keys=True))
            return 0
        if args.doctor:
            if not args.output_directory or not args.candidate_sha256:
                deny("doctor-arguments")
            from .artifact_doctor import verify_checkpoint
            report = verify_checkpoint(args.output_directory.absolute(), args.candidate_sha256)
            print(json.dumps(report, sort_keys=True))
            return 0
        if not args.approve_candidate_only:
            deny("explicit-operator-approval-required")
        native = _load_native(args)
        plan = TrainingPlan(
            args.run_id, native.model_digest, native.tokenizer.digest,
            learning_rate_ppm=args.learning_rate_ppm,
            max_optimizer_steps=args.maximum_steps,
            batch_lines=args.batch_lines,
            maximum_total_ms=args.maximum_total_ms,
            min_known_token_fraction_ppm=args.min_known_token_fraction_ppm,
            operator_approved=True,
        )
        if args.preflight:
            result = qualify_preflight(native, plan)
            print(json.dumps({
                "status": "candidate-preflight-admitted",
                "admission": result, "real_training_executed": False,
                "production_authorized": False,
            }, sort_keys=True))
            return 0
        if not args.output_directory or not args.state_directory or not args.trainer_code_sha256:
            deny("training-output-state-and-code-required")
        result = train_native(
            native, plan, code_sha256=args.trainer_code_sha256,
            output_directory=args.output_directory.absolute(),
            state_directory=args.state_directory.absolute(),
        )
        print(json.dumps(result.public_record(), sort_keys=True))
        return 0
    except (CandidateRejected, OSError, ValueError, RuntimeError, UnicodeError) as exc:
        print(json.dumps({
            "status": "held", "code": getattr(exc, "code", type(exc).__name__),
            "release_certified": False, "production_authorized": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
