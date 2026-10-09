"""CLI for the unified Skeleton application assembly."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Sequence

from skeleton.app.assembly import (
    checks_ok,
    compose_command,
    find_repo_root,
    load_manifest,
    manifest_payload,
    preflight,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app",
        description="Validate and operate the repository as one assembled application.",
    )
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="show the canonical application topology")
    status.add_argument("--json", action="store_true", dest="as_json")
    status.add_argument("--live", action="store_true", help="also probe public runtime health")
    status.add_argument("--full", action="store_true", help="include optional full-profile health")
    status.add_argument("--timeout", type=float, default=3.0, help="per-service live probe timeout")

    check = sub.add_parser("check", help="validate the application assembly")
    check.add_argument(
        "--runtime",
        action="store_true",
        help="also require Docker and runtime environment values",
    )
    check.add_argument("--json", action="store_true", dest="as_json")

    plan = sub.add_parser("plan", help="show dependency-aware application startup order")
    plan.add_argument("--full", action="store_true", help="include optional full-profile services")
    plan.add_argument("--json", action="store_true", dest="as_json")

    up = sub.add_parser("up", help="build and start the assembled application")
    up.add_argument("--full", action="store_true", help="include optional full-profile services")
    up.add_argument("--no-build", action="store_true", help="do not rebuild images")
    up.add_argument(
        "--production",
        action="store_true",
        help="use production backend and frontend image stages",
    )
    up.add_argument(
        "--hot",
        action="store_true",
        help="bind repository source into dev containers for hot reload",
    )
    up.add_argument(
        "--no-verify",
        action="store_true",
        help="return after Compose starts without probing public application surfaces",
    )
    up.add_argument("--verify-attempts", type=int, default=12)
    up.add_argument("--verify-delay", type=float, default=1.0)

    local_ai = sub.add_parser("local-ai", help="run native AI locally, without Docker or provider credentials")
    local_ai.add_argument("--model", help="native content-addressed checkpoint for headless inference")
    local_ai.add_argument("--inspect-model", action="store_true", help="validate model weights and report offline runtime limits")
    local_ai.add_argument("--prepare-dataset", help="flat folder of explicit UTF-8 .txt documents")
    local_ai.add_argument("--dataset-output", help="new directory for disjoint train/validation and identity manifest")
    local_ai.add_argument("--verify-dataset", help="check published dataset hashes, split contract and canonical manifest")
    local_ai.add_argument("--verify-sources", help="optional original source folder for strict source-to-dataset verification")
    local_ai.add_argument("--validation-percent", type=int, default=25, help="source-document validation split percent (10–50)")
    local_ai.add_argument("--split-seed", type=int, default=41, help="reproducible source-document split seed")
    local_ai.add_argument("--train-corpus", help="train a bounded CPU native checkpoint from a local UTF-8 text file")
    local_ai.add_argument("--improve-model", help="previous native checkpoint for independent held-out improvement")
    local_ai.add_argument("--compare-model", help="baseline checkpoint for read-only held-out comparison")
    local_ai.add_argument("--candidate-model", help="candidate checkpoint for read-only held-out comparison")

    local_ai.add_argument("--eval-corpus", help="separate held-out UTF-8 evaluation text (required for improvement)")
    local_ai.add_argument("--benchmark-suite", help="strict offline multi-category native model evaluation JSON")
    local_ai.add_argument("--exclude-train-corpus", help="reject benchmark cases copied from a specified local training text")
    local_ai.add_argument("--protect-suite", help="require an independent category benchmark pass before publishing trained weights")
    local_ai.add_argument("--replay-improvement", help="verify JSON receipt by regenerating exact native weights in temporary storage")

    local_ai.add_argument("--output-model", help="new native checkpoint filename for --train-corpus")
    local_ai.add_argument("--epochs", type=int, default=1, help="bounded native CPU training passes (1-4)")

    local_ai.add_argument("--prompt", help="headless text request (requires --model)")
    local_ai.add_argument("--max-output-tokens", type=int, default=8)
    local_ai.add_argument("--json", action="store_true", dest="as_json", help="print a bound inference receipt")
    local_ai.add_argument("--load-chat", help="restore verified turns from explicit model-bound local transcript")
    local_ai.add_argument("--save-chat", help="atomically export model-bound local transcript after inference")

    sub.add_parser("down", help="stop the assembled application")
    sub.add_parser("ps", help="show assembled service state")

    smoke = sub.add_parser("smoke", help="probe assembled public service health")
    smoke.add_argument("--full", action="store_true", help="probe the full profile")
    smoke.add_argument("--timeout", type=float, default=3.0)
    smoke.add_argument("--attempts", type=int, default=1)
    smoke.add_argument("--delay", type=float, default=1.0)
    smoke.add_argument("--json", action="store_true", dest="as_json")

    logs = sub.add_parser("logs", help="show assembled service logs")
    logs.add_argument("service", nargs="?", default="")
    logs.add_argument("-f", "--follow", action="store_true")

    sub.add_parser("config", help="render and validate the Docker Compose configuration")

    from skeleton.app.installer import configure_setup_parsers

    configure_setup_parsers(sub)
    return parser


def _print_status(
    as_json: bool,
    *,
    live: bool = False,
    full: bool = False,
    timeout: float = 3.0,
) -> int:
    manifest = load_manifest()
    payload = manifest_payload(manifest)
    live_results = ()
    live_ok: bool | None = None

    if live:
        if timeout <= 0:
            print("status timeout must be greater than zero")
            return 2
        from skeleton.app.health import probe_application, probes_ok

        live_results = probe_application(manifest=manifest, full=full, timeout=timeout)
        live_ok = probes_ok(live_results)
        payload["runtime_health"] = {
            "ok": live_ok,
            "full": full,
            "results": [result.to_dict() for result in live_results],
        }

    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if live_ok is not False else 1

    print(f"{manifest.name} application assembly v{manifest.version}")
    print(f"compose: {manifest.compose_file}")
    for service in manifest.services:
        marker = "*" if service.canonical else "-"
        url = f" {service.public_url}" if service.public_url else ""
        profile = f" [{service.profile}]" if service.profile else ""
        print(f"{marker} {service.name:<10} {service.role:<18} {service.kind}{profile}{url}")

    if live:
        print("")
        for result in live_results:
            status = result.status if result.status is not None else "-"
            print(
                f"[{'PASS' if result.ok else 'FAIL'}] "
                f"{result.service:<10} status={status} {result.url} {result.detail}"
            )
        print("runtime: healthy" if live_ok else "runtime: unhealthy")

    return 0 if live_ok is not False else 1


def _print_checks(runtime: bool, as_json: bool) -> int:
    root = find_repo_root()
    checks = preflight(root, runtime=runtime)
    ok = checks_ok(checks)
    if as_json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "root": str(root),
                    "runtime": runtime,
                    "checks": [check.to_dict() for check in checks],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"assembly root: {root}")
        for check in checks:
            print(f"[{'PASS' if check.ok else 'FAIL'}] {check.message}")
        print("assembly: ready" if ok else "assembly: blocked")
    return 0 if ok else 1


def _run_compose(
    command: Sequence[str],
    root: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> int:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    completed = subprocess.run(list(command), cwd=root, check=False, env=env)
    return int(completed.returncode)


def run_app_cli(argv: Sequence[str] | None = None) -> int:
    """Run the application assembly CLI and return a process-style exit code."""

    args = _parser().parse_args(list(argv or ()))
    command = args.command or "status"

    if command == "status":
        return _print_status(
            bool(getattr(args, "as_json", False)),
            live=bool(getattr(args, "live", False)),
            full=bool(getattr(args, "full", False)),
            timeout=float(getattr(args, "timeout", 3.0)),
        )
    if command == "check":
        return _print_checks(bool(args.runtime), bool(args.as_json))
    if command == "plan":
        from skeleton.app.plan import build_plan

        plan = build_plan(full=bool(args.full))
        if bool(args.as_json):
            print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"assembly profile: {plan.profile}")
            print("requested: " + ", ".join(plan.requested))
            for index, layer in enumerate(plan.layers):
                print(f"layer {index}: " + ", ".join(layer))
            print("startup order: " + " -> ".join(plan.services))
        return 0

    if command == "local-ai":
        from skeleton.app.local_ai import OfflineAISession, inspect_local_model, load_native_checkpoint, run_offline_ai

        if args.verify_dataset or args.verify_sources:
            if (
                not args.verify_dataset or args.prepare_dataset or args.dataset_output
                or args.model or args.prompt or args.inspect_model
                or args.train_corpus or args.output_model or args.improve_model
                or args.compare_model or args.candidate_model or args.eval_corpus
                or args.benchmark_suite or args.exclude_train_corpus
                or args.protect_suite or args.replay_improvement
                or args.load_chat or args.save_chat
                or args.epochs != 1 or args.max_output_tokens != 8
                or args.validation_percent != 25 or args.split_seed != 41
            ):
                print("dataset verification requires --verify-dataset and optional --verify-sources only")
                return 2
            from skeleton.app.local_ai_dataset import verify_native_dataset

            try:
                verification = verify_native_dataset(
                    args.verify_dataset, original_sources=args.verify_sources,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("native dataset verification failed: "
                      + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(verification, sort_keys=True, ensure_ascii=False))
            else:
                print("Verified prepared native dataset: " + verification["dataset_id"])
                print("Original sources checked: "
                      + ("yes" if verification["original_sources_verified"] else "no"))
                print("No model quality certification")
            return 0

        if args.prepare_dataset or args.dataset_output:
            if (
                not args.prepare_dataset or not args.dataset_output
                or args.model or args.prompt or args.inspect_model
                or args.train_corpus or args.output_model or args.improve_model
                or args.compare_model or args.candidate_model or args.eval_corpus
                or args.benchmark_suite or args.exclude_train_corpus
                or args.protect_suite or args.replay_improvement
                or args.load_chat or args.save_chat
                or args.epochs != 1 or args.max_output_tokens != 8
            ):
                print("local-ai dataset preparation requires only --prepare-dataset, --dataset-output and optional split controls")
                return 2
            from skeleton.app.local_ai_dataset import prepare_native_dataset

            try:
                dataset = prepare_native_dataset(
                    args.prepare_dataset, args.dataset_output,
                    validation_percent=args.validation_percent,
                    seed=args.split_seed,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai dataset rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(dataset, ensure_ascii=False, sort_keys=True))
            else:
                print("Prepared native train/validation corpus in: " + str(dataset["output_directory"]))
                print("Source documents: " + str(dataset["source_count"]))
                print("Training/validation tokens: "
                      + str(dataset["training_tokens"]) + "/" + str(dataset["validation_tokens"]))
                print("Dataset ID: " + str(dataset["dataset_id"]))
                print("Quality: not independently certified")
            return 0
        if args.validation_percent != 25 or args.split_seed != 41:
            print("--validation-percent and --split-seed require --prepare-dataset")
            return 2

        # Never accept tuning switches that a mode would silently ignore.
        # A replay always uses epochs pinned inside its original receipt;
        # inspection, evaluation and inference do not train any weights.
        if args.epochs != 1 and (
            not args.train_corpus
            or args.replay_improvement
            or args.compare_model
            or args.candidate_model and not args.improve_model
            or args.benchmark_suite
        ):
            print("--epochs applies only to local training or continued training")
            return 2
        if args.max_output_tokens != 8 and (
            args.train_corpus or args.improve_model or args.replay_improvement
            or args.benchmark_suite or args.compare_model or args.candidate_model
            or args.inspect_model
        ):
            print("--max-output-tokens applies only to native inference")
            return 2

        if args.replay_improvement:
            if (
                not args.compare_model or not args.candidate_model
                or not args.train_corpus or not args.eval_corpus
                or args.model or args.prompt or args.inspect_model
                or args.output_model or args.load_chat or args.save_chat
                or args.improve_model or args.benchmark_suite
                or args.exclude_train_corpus
            ):
                print("replay requires --compare-model parent, --candidate-model, --train-corpus and --eval-corpus")
                return 2
            from skeleton.app.local_ai_replay import replay_local_improvement

            try:
                evidence = replay_local_improvement(
                    args.replay_improvement, args.compare_model,
                    args.candidate_model, args.train_corpus, args.eval_corpus,
                    protected_suite=args.protect_suite,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai reproduction rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(evidence, sort_keys=True, ensure_ascii=False))
            else:
                print("Native model improvement reproduced: " + evidence["candidate_model_digest"])
                print("Recorded artifact SHA256: " + evidence["replayed_artifact_sha256"])
                print("No deployment promotion or independent quality certification")
            return 0
        if args.benchmark_suite:
            if (
                not args.model or args.prompt or args.inspect_model
                or args.compare_model or args.improve_model or args.train_corpus
                or args.eval_corpus or args.output_model or args.load_chat
                or args.save_chat or args.protect_suite or args.replay_improvement
            ):
                print("local-ai --benchmark-suite requires --model and optional --candidate-model only")
                return 2
            from skeleton.app.local_ai_benchmark import benchmark_native_models

            try:
                result = benchmark_native_models(
                    args.benchmark_suite, baseline=args.model,
                    candidate=args.candidate_model,
                    excluded_training_text=args.exclude_train_corpus,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai benchmark rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            else:
                print("suite digest: " + result["suite_digest"])
                print("cases/categories: "
                      + str(result["case_count"]) + "/" + str(result["category_count"]))
                print("baseline perplexity: " + f"{result['baseline']['overall_perplexity']:.3f}")
                if result["candidate"] is not None:
                    print("candidate perplexity: " + f"{result['candidate']['overall_perplexity']:.3f}")
                    print("all categories protected: "
                          + ("yes" if result["passes_local_regression_gate"] else "no"))
                print("No general quality certification or automatic model promotion")
            return 0 if result["passes_local_regression_gate"] is not False else 1

        if args.exclude_train_corpus:
            print("--exclude-train-corpus requires --benchmark-suite")
            return 2
        if args.protect_suite and not args.improve_model and not args.replay_improvement:
            print("--protect-suite requires incremental --improve-model")
            return 2
        if args.compare_model or args.candidate_model:
            if (
                not args.compare_model or not args.candidate_model or not args.eval_corpus
                or args.improve_model or args.train_corpus or args.output_model
                or args.model or args.prompt or args.load_chat or args.save_chat
                or args.inspect_model or args.benchmark_suite
            ):
                print("local-ai comparison requires --compare-model, --candidate-model, --eval-corpus only")
                return 2
            from skeleton.app.local_ai_improvement import compare_local_models

            try:
                verdict = compare_local_models(
                    args.compare_model, args.candidate_model, args.eval_corpus,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai comparison rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(verdict.to_dict(), ensure_ascii=False, sort_keys=True))
            else:
                print("Baseline held-out perplexity: " + f"{verdict.baseline_perplexity:.3f}")
                print("Candidate held-out perplexity: " + f"{verdict.candidate_perplexity:.3f}")
                print("Improvement: " + ("yes" if verdict.improves else "no"))
                print("No weight mutation, no release promotion")
            # A comparison is a release gate, not a best-effort status query.
            return 0 if verdict.improves else 1
        if args.improve_model:
            if (
                not args.train_corpus or not args.eval_corpus or not args.output_model
                or args.model or args.prompt or args.inspect_model
                or args.load_chat or args.save_chat
                or args.compare_model or args.candidate_model or args.benchmark_suite or args.replay_improvement
            ):
                print("local-ai improvement requires --improve-model, --train-corpus, --eval-corpus and --output-model only")
                return 2
            from skeleton.app.local_ai_improvement import improve_local_model

            try:
                receipt = improve_local_model(
                    args.improve_model, args.train_corpus, args.eval_corpus,
                    args.output_model, epochs=args.epochs,
                    protected_suite=args.protect_suite,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai candidate rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True))
            else:
                print("Native candidate checkpoint written: " + str(args.output_model))
                print("held-out perplexity: "
                      + f"{receipt.baseline_perplexity:.3f} -> {receipt.accepted_perplexity:.3f}")
                print("parent weights untouched; not an independent quality certification")
            return 0
        if args.train_corpus:
            if (
                not args.output_model or args.model or args.prompt
                or args.inspect_model or args.load_chat or args.save_chat
                or args.eval_corpus or args.improve_model
                or args.compare_model or args.candidate_model or args.benchmark_suite
            ):
                print("local-ai training requires --train-corpus and --output-model without chat/inference options")
                return 2
            from skeleton.app.local_ai_training import train_local_text

            try:
                receipt = train_local_text(args.train_corpus, args.output_model, epochs=args.epochs)
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai training rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
            else:
                print("Trained bounded CPU checkpoint: " + str(args.output_model))
                print("model digest: " + receipt.model_digest)
                print("training steps: " + str(receipt.training_steps))
                print("quality: not independently certified; not foundation-model weights")
            return 0
        if args.output_model or args.eval_corpus:
            print("--output-model/--eval-corpus require local training or improvement")
            return 2
        if args.inspect_model:
            if not args.model or args.prompt or args.load_chat or args.save_chat:
                print("local-ai --inspect-model requires only --model")
                return 2
            try:
                report = inspect_local_model(load_native_checkpoint(args.model))
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai model rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            else:
                print("model: " + str(report["model_id"]))
                print("digest: " + str(report["model_digest"]))
                print("context: " + str(report["max_context_tokens"]) + " tokens")
                print("output limit: " + str(report["max_output_tokens"]) + " tokens")
                print("native model bytes: " + str(report["model_bytes"]))
                print("model quality: not independently certified")
            return 0
        if bool(args.model) != bool(args.prompt):
            print("local-ai headless inference requires both --model and --prompt")
            return 2
        if (args.load_chat or args.save_chat) and not args.model:
            print("local-ai chat import/export requires --model and --prompt")
            return 2
        if args.model:
            import asyncio

            try:
                session = OfflineAISession(load_native_checkpoint(args.model))
                if args.load_chat:
                    session.import_transcript(args.load_chat)
                answer = asyncio.run(session.ask(args.prompt, max_output_tokens=args.max_output_tokens))
                chat_digest = session.export_transcript(args.save_chat) if args.save_chat else None
            except (ValueError, RuntimeError, OSError) as exc:
                print("local-ai request rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps({
                    "schema_version": 1,
                    "text": answer.text,
                    "model_digest": answer.model_digest,
                    "execution_receipt_digest": answer.execution_receipt_digest,
                    "input_tokens": answer.input_tokens,
                    "output_tokens": answer.output_tokens,
                    "conversation_turns": len(session.history) // 2,
                    "chat_sha256": chat_digest,
                }, ensure_ascii=False, sort_keys=True))
            else:
                print(answer.text)
            return 0
        return run_offline_ai()

    if command in {"preload", "setup", "install"}:
        from skeleton.app.installer import run_setup_command

        return run_setup_command(command, args)


    root = find_repo_root()
    manifest = load_manifest()

    if command == "up":
        if bool(args.production) and bool(args.hot):
            print("--production and --hot are mutually exclusive")
            return 2
        checks = preflight(root, runtime=True, manifest=manifest)
        if not checks_ok(checks):
            for check in checks:
                if not check.ok and check.required:
                    print(f"[FAIL] {check.message}")
            print("application start aborted: runtime preflight failed")
            return 1
        mode = "production" if bool(args.production) else "development"
        exit_code = _run_compose(
            compose_command(
                "up",
                manifest=manifest,
                full=bool(args.full),
                build=not bool(args.no_build),
                hot=bool(args.hot),
            ),
            root,
            env_overrides=manifest.mode_env(mode),
        )
        if exit_code or bool(args.no_verify):
            return exit_code

        from skeleton.app.health import probes_ok, wait_for_application

        try:
            results = wait_for_application(
                manifest=manifest,
                full=bool(args.full),
                timeout=3.0,
                attempts=int(args.verify_attempts),
                delay=float(args.verify_delay),
            )
        except ValueError as exc:
            print(f"invalid startup verification budget: {exc}")
            return 2

        for result in results:
            status = result.status if result.status is not None else "-"
            print(
                f"[{'PASS' if result.ok else 'FAIL'}] "
                f"{result.service:<10} status={status} {result.url} {result.detail}"
            )
        if probes_ok(results):
            print("application start: ready")
            return 0
        print("application start: services launched but readiness verification failed")
        return 1
    if command == "smoke":
        from skeleton.app.health import probes_ok, wait_for_application

        timeout = float(args.timeout)
        attempts = int(args.attempts)
        delay = float(args.delay)
        if timeout <= 0:
            print("smoke timeout must be greater than zero")
            return 2
        try:
            results = wait_for_application(
                manifest=manifest,
                full=bool(args.full),
                timeout=timeout,
                attempts=attempts,
                delay=delay,
            )
        except ValueError as exc:
            print(f"invalid smoke budget: {exc}")
            return 2
        ok = probes_ok(results)
        if bool(args.as_json):
            print(
                json.dumps(
                    {
                        "ok": ok,
                        "full": bool(args.full),
                        "results": [result.to_dict() for result in results],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            for result in results:
                status = result.status if result.status is not None else "-"
                print(
                    f"[{'PASS' if result.ok else 'FAIL'}] "
                    f"{result.service:<10} status={status} {result.url} {result.detail}"
                )
            print("application smoke: healthy" if ok else "application smoke: unhealthy")
        return 0 if ok else 1
    if command == "down":
        return _run_compose(compose_command("down", manifest=manifest), root)
    if command == "ps":
        return _run_compose(compose_command("ps", manifest=manifest), root)
    if command == "logs":
        return _run_compose(
            compose_command(
                "logs",
                manifest=manifest,
                follow=bool(args.follow),
                service=str(args.service or ""),
            ),
            root,
        )
    if command == "config":
        return _run_compose(compose_command("config", manifest=manifest), root)

    raise AssertionError(f"unhandled app command: {command}")
