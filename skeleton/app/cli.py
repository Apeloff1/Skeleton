"""CLI for the unified Skeleton application assembly."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from skeleton.app.assembly import (
    CHROMA_FULL_PROFILE_BLOCKED,
    checks_ok,
    compose_command,
    find_repo_root,
    load_manifest,
    manifest_payload,
    preflight,
    runtime_manifest,
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

    doctor = sub.add_parser(
        "doctor", help="show redacted install, service and AI readiness with actionable fixes"
    )
    doctor.add_argument(
        "--live", action="store_true", help="probe existing endpoints; never invoke AI or start a crawler"
    )
    doctor.add_argument("--timeout", type=float, default=3.0, help="per-probe timeout, at most 10 seconds")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    doctor.add_argument(
        "--studio", action="store_true",
        help="inspect actual local SDK/core prerequisites separately from server readiness",
    )
    doctor.add_argument(
        "--auth-token-file", type=Path,
        help="private existing bearer-token file for authenticated --studio --live server readiness",
    )

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
    up.add_argument(
        "--verify-attempts", type=int, default=60,
        help="whole-application readiness attempts (default: 60 for cold dependency-ordered startup)",
    )
    up.add_argument("--verify-delay", type=float, default=2.0)

    local_ai = sub.add_parser("local-ai", help="run native AI locally, without Docker or provider credentials")
    local_ai.add_argument("--model", help="native content-addressed checkpoint for headless inference")
    local_ai.add_argument("--gguf-model", help="explicit local GGUF open-weight artifact for llama.cpp inference")
    local_ai.add_argument("--llama-executable", help="explicit local llama.cpp executable (not downloaded)")

    local_ai.add_argument("--inspect-model", action="store_true", help="validate model weights and report offline runtime limits")
    local_ai.add_argument("--prepare-dataset", help="flat folder of explicit UTF-8 .txt documents")
    local_ai.add_argument("--dataset-output", help="new directory for disjoint train/validation and identity manifest")
    local_ai.add_argument("--improve-dataset", help="verified dataset folder for held-out checkpoint continuation")
    local_ai.add_argument("--verify-dataset", help="check published dataset hashes, split contract and canonical manifest")
    local_ai.add_argument("--verify-sources", help="optional original source folder for strict source-to-dataset verification")
    local_ai.add_argument("--validation-percent", type=int, default=25, help="source-document validation split percent (10–50)")
    local_ai.add_argument("--split-seed", type=int, default=41, help="reproducible source-document split seed")
    local_ai.add_argument("--self-check", action="store_true", help="verify bundled offline native inference, CPU training and benchmarking")
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
    local_ai.add_argument("--epochs", type=int, default=None, help="bounded native CPU training passes (1-4)")

    local_ai.add_argument("--load-chat", help="restore verified turns from explicit model-bound local transcript")
    local_ai.add_argument("--save-chat", help="atomically export model-bound local transcript after inference")

    local_ai.add_argument("--prompt", help="headless text request (requires --model)")
    local_ai.add_argument("--max-output-tokens", type=int, default=None)
    local_ai.add_argument("--json", action="store_true", dest="as_json", help="print a bound inference receipt")
    prepare = sub.add_parser("prepare-local-model", help="pin an existing local GGUF and llama.cpp executable")
    prepare.add_argument("--executable", type=Path, required=True, help="local llama.cpp CLI executable")
    prepare.add_argument("--model", type=Path, required=True, help="local GGUF weights")
    prepare.add_argument("--output", type=Path, required=True, help="new manifest file; never overwritten")
    prepare.add_argument("--model-id", help="optional display identifier")
    prepare.add_argument("--context-size", type=int, default=4096)
    prepare.add_argument("--threads", type=int)
    prepare.add_argument("--gpu-layers", type=int, default=0)
    prepare.add_argument("--timeout", type=float, default=120.0)
    prepare.add_argument(
        "--runtime-profile",
        choices=("raw", "llama-completion-chat", "qwen3-completion-chat"),
        default="raw",
        help="operator-selected prompt/output protocol for the pinned local executable",
    )
    prepare.add_argument("--json", action="store_true", dest="as_json")
    sub.add_parser(
        "audit-signed-library-relocation", add_help=False,
        help="verify signed game relocation without policy or replay rollback",
    )
    sub.add_parser(
        "audit-offline-library-relocation", add_help=False,
        help="verify original-game installation relocation without replay loss",
    )
    sub.add_parser(
        "mixed-library-handoff", add_help=False,
        help="publish or inspect a pinned mixed original-game receipt",
    )
    sub.add_parser(
        "mixed-library-continuity-handoff", add_help=False,
        help="publish or inspect a pinned mixed replay progression receipt",
    )
    sub.add_parser(
        "audit-mixed-library-epoch-relocation", add_help=False,
        help="verify multi-generation original-game relocation without replay loss",
    )
    sub.add_parser(
        "audit-mixed-library-epoch-receipts", add_help=False,
        help="reverify an ordered series of independently pinned game handoffs",
    )
    sub.add_parser(
        "mixed-library-checkpoint-handoff", add_help=False,
        help="publish or independently inspect a private checkpoint-chain replay receipt",
    )
    sub.add_parser(
        "audit-mixed-library-epoch-successor", add_help=False,
        help="verify a pinned original-game epoch handoff strictly extends another",
    )
    sub.add_parser(
        "mixed-library-epoch-handoff", add_help=False,
        help="publish or inspect a pinned multi-epoch original-game receipt",
    )
    sub.add_parser(
        "audit-mixed-library-epochs", add_help=False,
        help="replay and verify 2-6 signed/unsigned library generations",
    )
    sub.add_parser(
        "audit-mixed-library-continuity", add_help=False,
        help="verify that mixed signed/unsigned private replays advance without forks",
    )
    sub.add_parser(
        "audit-mixed-library-relocation", add_help=False,
        help="verify mixed signed/unsigned game library relocation and replay",
    )
    sub.add_parser(
        "audit-mixed-game-library", add_help=False,
        help="audit a bounded mixed signed/unsigned original-game catalog",
    )
    sub.add_parser(
        "audit-signed-game-library", add_help=False,
        help="audit independently pinned signer histories across installed games",
    )
    sub.add_parser(
        "audit-offline-game-library", add_help=False,
        help="audit 1-8 independently pinned original game installations and saves",
    )
    sub.add_parser(
        "delivery-assurance", add_help=False,
        help="verify installed game, archive and save custody (delivery-assurance --help)",
    )
    sub.add_parser(
        "inspect-original-provenance", add_help=False,
        help="inspect original browser/Godot source claim inventory without rights certification",
    )
    sub.add_parser(
        "recover-policy-chain-signed-install", add_help=False,
        help="recover quarantined signed game under pinned signer history",
    )
    sub.add_parser(
        "migrate-policy-chain-signed-progress", add_help=False,
        help="migrate signed original game and save under pinned signer history",
    )
    sub.add_parser(
        "install-policy-chain-signed-source", add_help=False,
        help="install signed original game under pinned signer history",
    )
    sub.add_parser(
        "policy-chain-delivery-assurance", add_help=False,
        help="verify pinned signer history, installed game and private replay",
    )
    sub.add_parser(
        "inspect-trust-policy-chain", add_help=False,
        help="inspect independently pinned multi-epoch signer revocation history",
    )
    sub.add_parser(
        "inspect-trust-policy-transition", add_help=False,
        help="inspect independently pinned signer rotation and revocation transition",
    )
    sub.add_parser(
        "recover-policy-signed-install", add_help=False,
        help="recover quarantined original game from policy-authorized signed source",
    )
    sub.add_parser(
        "policy-signed-delivery-assurance", add_help=False,
        help="verify pinned policy, source signature, installed game and private replay",
    )
    sub.add_parser(
        "migrate-policy-signed-progress", add_help=False,
        help="migrate original private replay under independently pinned signer policy",
    )
    sub.add_parser(
        "verify-policy-signed-source", add_help=False,
        help="verify Ed25519 source against an independently pinned local trust policy",
    )
    sub.add_parser(
        "install-policy-signed-source", add_help=False,
        help="install verified signed source under an independently pinned trust policy",
    )
    sub.add_parser(
        "install-signed-source", add_help=False,
        help="verify detached source signature before no-clobber game installation",
    )
    sub.add_parser(
        "migrate-signed-progress", add_help=False,
        help="verify signed source, migrate pinned private progress, replay and reconcile",
    )
    sub.add_parser(
        "signed-delivery-assurance", add_help=False,
        help="verify signed source archive, installed game and saved replay",
    )
    sub.add_parser(
        "verify-archive-signature", add_help=False,
        help="verify detached Ed25519 original source archive signature",
    )
    sub.add_parser(
        "recover-install", add_help=False,
        help="reinstall pinned offline source while preserving quarantine (recover-install --help)",
    )
    sub.add_parser(
        "inspect-uncertain-offline-receipt", add_help=False,
        help="read-only quarantine triage of an independently pinned offline receipt",
    )
    sub.add_parser("first-playable-jobfile", add_help=False,
                   help="run original playable cohort from independently pinned private job file")
    sub.add_parser("first-playable-batch-triage", add_help=False,
                   help="read-only quarantine inspection of interrupted playable deliveries")
    sub.add_parser("first-playable-batch", add_help=False,
                   help="publish or independently reverify 2-8 original playable deliveries")
    sub.add_parser("first-playable-delivery", add_help=False,
                   help="exercise original source, fresh install, interactive save and pinned delivery acceptance")
    sub.add_parser("consumer-first-run-readiness", add_help=False,
                   help="read-only two-pass installed playable evidence with explicit release holds")
    sub.add_parser("consumer-first-run-cohort", add_help=False,
                   help="read-only pinned 2-8 game consumer first-run replay; release blocked")
    sub.add_parser("studio-journey", add_help=False,
                   help="build and replay-verify a real original browser/Godot game (studio-journey --help)")
    sub.add_parser("play-dialogue", add_help=False,
                   help="play and save a source-bound offline dialogue (play-dialogue --help)")
    sub.add_parser("play-combat", add_help=False,
                   help="play and replay-verify a deterministic offline encounter (play-combat --help)")
    sub.add_parser("chat", add_help=False, help="open durable native/GGUF terminal chat (chat --help)")
    sub.add_parser("serve-local-ai", add_help=False, help="open the authenticated offline AI workspace (serve-local-ai --help)")
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

    sub.add_parser("config", help="validate Compose without printing rendered credentials")

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
    manifest = runtime_manifest()
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
        print()
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
    # An inherited Compose setting must not remove an older Chroma container
    # that is now an orphan and may own the only copy of writable /data.
    env["COMPOSE_REMOVE_ORPHANS"] = "0"
    completed = subprocess.run(list(command), cwd=root, check=False, env=env)
    return int(completed.returncode)


def run_app_cli(argv: Sequence[str] | None = None) -> int:
    """Run the application assembly CLI and return a process-style exit code."""

    arguments = list(argv or ())
    # The same pinned Jeeves candidate optimizer owns multidomain specialization.
    if arguments and arguments[0] == "training-modules":
        from skeleton.ai.training.jeeves_parallel_mirrors import main as training_main
        return training_main(arguments[1:])
    if arguments and arguments[0] == "cinematic-sim":
        from skeleton.ai.training.jeeves_cinematic_simulation import main as cinema_main
        return cinema_main(arguments[1:])
    if arguments and arguments[0] == "adaptive-sim":
        from skeleton.ai.training.jeeves_adaptive_sim_training import main as adaptive_main
        return adaptive_main(arguments[1:])
    if arguments and arguments[0] == "boomerang-queue":
        from skeleton.ai.training.jeeves_boomerang_queue import main as boomerang_main
        return boomerang_main(arguments[1:])
    # Delegate parsing to the existing owners, including their complete help.
    if arguments and arguments[0] == "inspect-original-provenance":
        from skeleton.app.offline_original_content_provenance import main as provenance_main
        return provenance_main(arguments[1:])
    if arguments and arguments[0] == "recover-policy-chain-signed-install":
        from skeleton.app.offline_policy_chain_recovery import main as chain_recovery_main
        return chain_recovery_main(arguments[1:])
    if arguments and arguments[0] == "migrate-policy-chain-signed-progress":
        from skeleton.app.offline_policy_chain_progress import main as chain_progress_main
        return chain_progress_main(arguments[1:])
    if arguments and arguments[0] == "install-policy-chain-signed-source":
        from skeleton.app.offline_policy_chain_install import main as chain_install_main
        return chain_install_main(arguments[1:])
    if arguments and arguments[0] == "policy-chain-delivery-assurance":
        from skeleton.app.offline_policy_chain_delivery import main as chain_delivery_main
        return chain_delivery_main(arguments[1:])
    if arguments and arguments[0] == "inspect-trust-policy-chain":
        from skeleton.app.offline_trust_policy_chain import main as policy_chain_main
        return policy_chain_main(arguments[1:])
    if arguments and arguments[0] == "inspect-trust-policy-transition":
        from skeleton.app.offline_trust_policy_transition import main as policy_transition_main
        return policy_transition_main(arguments[1:])
    if arguments and arguments[0] == "recover-policy-signed-install":
        from skeleton.app.offline_policy_signed_install_recovery import main as policy_recover_main
        return policy_recover_main(arguments[1:])
    if arguments and arguments[0] == "policy-signed-delivery-assurance":
        from skeleton.app.offline_policy_signed_delivery import main as policy_delivery_main
        return policy_delivery_main(arguments[1:])
    if arguments and arguments[0] == "migrate-policy-signed-progress":
        from skeleton.app.offline_policy_signed_progress_migration import main as policy_migrate_main
        return policy_migrate_main(arguments[1:])
    if arguments and arguments[0] == "verify-policy-signed-source":
        from skeleton.app.offline_source_trust_policy import main as policy_verify_main
        return policy_verify_main(arguments[1:])
    if arguments and arguments[0] == "install-policy-signed-source":
        from skeleton.app.offline_policy_signed_install import main as policy_install_main
        return policy_install_main(arguments[1:])
    if arguments and arguments[0] == "install-signed-source":
        from skeleton.app.offline_signed_source_install import main as signed_install_main
        return signed_install_main(arguments[1:])
    if arguments and arguments[0] == "migrate-signed-progress":
        from skeleton.app.offline_signed_progress_migration import main as migrate_signed_main
        return migrate_signed_main(arguments[1:])
    if arguments and arguments[0] == "signed-delivery-assurance":
        from skeleton.app.offline_signed_delivery import main as signed_delivery_main
        return signed_delivery_main(arguments[1:])
    if arguments and arguments[0] == "source-signing-request":
        from skeleton.app.offline_source_signing_request import main as source_signing_request_main
        return source_signing_request_main(arguments[1:])
    if arguments and arguments[0] == "verify-archive-signature":
        from skeleton.app.offline_archive_signature import main as signature_main
        return signature_main(arguments[1:])
    if arguments and arguments[0] == "recover-signed-progress":
        from skeleton.app.offline_signed_quarantine_progress import main as signed_progress_recovery_main
        return signed_progress_recovery_main(arguments[1:])
    if arguments and arguments[0] == "recover-signed-install":
        from skeleton.app.offline_signed_install_recovery import main as signed_recovery_main
        return signed_recovery_main(arguments[1:])
    if arguments and arguments[0] == "recover-install":
        from skeleton.app.offline_install_recovery import main as recovery_main
        return recovery_main(arguments[1:])
    if arguments and arguments[0] == "audit-signed-library-relocation":
        from skeleton.app.offline_signed_game_library_relocation import main as signed_relocation_main
        return signed_relocation_main(arguments[1:])
    if arguments and arguments[0] == "audit-offline-library-relocation":
        from skeleton.app.offline_game_library_relocation import main as relocation_main
        return relocation_main(arguments[1:])
    if arguments and arguments[0] == "mixed-library-handoff":
        from skeleton.app.offline_mixed_game_library_handoff import main as mixed_handoff_main
        return mixed_handoff_main(arguments[1:])
    if arguments and arguments[0] == "mixed-library-continuity-handoff":
        from skeleton.app.offline_mixed_game_library_continuity_handoff import main as continuity_handoff_main
        return continuity_handoff_main(arguments[1:])
    if arguments and arguments[0] == "audit-mixed-library-epoch-relocation":
        from skeleton.app.offline_mixed_library_epoch_relocation import main as epoch_relocation_main
        return epoch_relocation_main(arguments[1:])
    if arguments and arguments[0] == "inspect-uncertain-offline-receipt":
        from skeleton.app.offline_uncertain_receipt_inspection import main as uncertain_main
        return uncertain_main(arguments[1:])
    if arguments and arguments[0] == "audit-mixed-library-epoch-receipts":
        from skeleton.app.offline_mixed_library_epoch_receipt_chain import main as receipt_chain_main
        return receipt_chain_main(arguments[1:])
    if arguments and arguments[0] == "mixed-library-checkpoint-handoff":
        from skeleton.app.offline_mixed_library_checkpoint_handoff import main as checkpoint_handoff_main
        return checkpoint_handoff_main(arguments[1:])
    if arguments and arguments[0] == "audit-mixed-library-epoch-successor":
        from skeleton.app.offline_mixed_library_epoch_successor import main as successor_main
        return successor_main(arguments[1:])
    if arguments and arguments[0] == "mixed-library-epoch-handoff":
        from skeleton.app.offline_mixed_library_epoch_handoff import main as epoch_handoff_main
        return epoch_handoff_main(arguments[1:])
    if arguments and arguments[0] == "audit-mixed-library-epochs":
        from skeleton.app.offline_mixed_library_epoch_chain import main as epochs_main
        return epochs_main(arguments[1:])
    if arguments and arguments[0] == "audit-mixed-library-continuity":
        from skeleton.app.offline_mixed_game_library_continuity import main as continuity_main
        return continuity_main(arguments[1:])
    if arguments and arguments[0] == "audit-mixed-library-relocation":
        from skeleton.app.offline_mixed_game_library_relocation import main as mixed_relocation_main
        return mixed_relocation_main(arguments[1:])
    if arguments and arguments[0] == "audit-mixed-game-library":
        from skeleton.app.offline_mixed_game_library_audit import main as mixed_library_main
        return mixed_library_main(arguments[1:])
    if arguments and arguments[0] == "audit-signed-game-library":
        from skeleton.app.offline_signed_game_library_audit import main as signed_library_main
        return signed_library_main(arguments[1:])
    if arguments and arguments[0] == "audit-offline-game-library":
        from skeleton.app.offline_game_library_audit import main as library_audit_main
        return library_audit_main(arguments[1:])
    if arguments and arguments[0] == "delivery-assurance":
        from skeleton.app.offline_delivery_assurance import main as assurance_main
        return assurance_main(arguments[1:])
    if arguments and arguments[0] == "first-playable-jobfile":
        from skeleton.app.offline_first_playable_jobfile import main as jobfile_main
        return jobfile_main(arguments[1:])
    if arguments and arguments[0] == "first-playable-batch-triage":
        from skeleton.app.offline_first_playable_batch_triage import main as triage_main
        return triage_main(arguments[1:])
    if arguments and arguments[0] == "first-playable-batch":
        from skeleton.app.offline_first_playable_batch import main as batch_main
        return batch_main(arguments[1:])
    if arguments and arguments[0] == "first-playable-delivery":
        from skeleton.app.offline_first_playable_delivery import main as delivery_main
        return delivery_main(arguments[1:])
    if arguments and arguments[0] == "consumer-first-run-readiness":
        from skeleton.app.consumer_first_run_readiness import main as readiness_main
        return readiness_main(arguments[1:])
    if arguments and arguments[0] == "consumer-first-run-cohort":
        from skeleton.app.consumer_first_run_cohort import main as cohort_readiness_main
        return cohort_readiness_main(arguments[1:])
    if arguments and arguments[0] == "studio-journey":
        from skeleton.app.studio_journey import main as journey_main
        return journey_main(arguments[1:])
    if arguments and arguments[0] == "play-dialogue":
        from skeleton.app.dialogue_cli import main as dialogue_main
        return dialogue_main(arguments[1:])
    if arguments and arguments[0] == "play-combat":
        from skeleton.app.combat_cli import main as combat_main
        return combat_main(arguments[1:])
    if arguments and arguments[0] == "chat":
        from skeleton.app.offline_chat_cli import main as chat_main
        return chat_main(arguments[1:])
    if arguments and arguments[0] == "serve-local-ai":
        from skeleton.app.offline_http import main as serve_main
        return serve_main(arguments[1:])
    if arguments and arguments[0] == "local-ai":
        from skeleton.app.offline_cli import _parser as offline_parser, main as offline_main

        # The standalone shell owns workspace, backup, local-library and
        # qualification modes. Delegate their complete parsing/validation;
        # native training/benchmarking and ordinary inference keep this CLI.
        shared = {"--model", "--prompt", "--max-output-tokens", "--json", "--help", "-h"}
        shell_options = {
            option for action in offline_parser()._actions
            for option in action.option_strings
        } - shared
        if any(argument.partition("=")[0] in shell_options for argument in arguments[1:]):
            return offline_main(arguments[1:])
    args = _parser().parse_args(arguments)
    command = args.command or "status"

    if command == "prepare-local-model":
        from skeleton.ai.runtime.inference.deployment import (
            create_local_model_deployment,
        )

        try:
            model = create_local_model_deployment(
                args.output,
                executable_path=args.executable,
                model_path=args.model,
                model_id=args.model_id,
                context_size=args.context_size,
                threads=args.threads,
                gpu_layers=args.gpu_layers,
                timeout_seconds=args.timeout,
                runtime_profile=args.runtime_profile,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            if args.as_json:
                print(json.dumps({"ok": False, "error": str(exc)}))
            else:
                print("Local model preparation failed:", str(exc))
            return 1
        if args.as_json:
            print(json.dumps({"ok": True, "manifest": str(model.manifest_path),
                              "model_sha256": model.model_sha256,
                              "executable_sha256": model.executable_sha256,
                              "runtime_executed": False, "model_qualified": False}))
        else:
            print("Local model manifest:", model.manifest_path)
            print("Model SHA-256:", model.model_sha256)
            print("Files pinned. No model execution or quality qualification was performed.")
            print("Start chat: python -m skeleton app chat --gguf-deployment <manifest> --interactive")
        return 0
    if command == "status":
        return _print_status(
            bool(getattr(args, "as_json", False)),
            live=bool(getattr(args, "live", False)),
            full=bool(getattr(args, "full", False)),
            timeout=float(getattr(args, "timeout", 3.0)),
        )
    if command == "check":
        return _print_checks(bool(args.runtime), bool(args.as_json))
    if command == "doctor":
        from skeleton.app.first_install import first_install_report

        try:
            report = first_install_report(
                live=bool(args.live), timeout=args.timeout,
                studio=bool(args.studio), auth_token_file=args.auth_token_file,
            )
        except (OSError, ValueError, TypeError) as exc:
            print("doctor could not inspect the application: " + type(exc).__name__)
            return 2
        if args.as_json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print("Host prerequisites: " + ("ready" if report["platform_ready"] else "blocked"))
            print("Runtime configuration: " + ("ready" if report["configuration_ready"] else "blocked"))
            print(
                "Application services: "
                + (
                    "not probed"
                    if report["services_ready"] is None
                    else "ready" if report["services_ready"] else "unavailable"
                )
            )
            ai = report["ai"]
            print(
                "AI: "
                + (
                    "not probed"
                    if ai["available"] is None
                    else "available" if ai["available"] else "unavailable"
                )
                + " ("
                + str(ai["configuration"])
                + ")"
            )
            print("Product: " + report["endpoints"]["product"])
            if args.studio:
                studio_report = report["studio"]
                local = studio_report["local_host"]
                print("Studio host inventory: " + ("observed" if local.get("observed") else "unavailable"))
                print("Studio server inventory: " + ("observed" if studio_report["server"].get("observed") else "not observed"))
                print("Native target prerequisites and Dragon runtime details: use --json.")
            for step in report["next_steps"]:
                print("Next: " + step)
        ok = (
            report["platform_ready"]
            and report["configuration_ready"]
            and report["services_ready"] is not False
        )
        return 0 if ok else 1
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
        from skeleton.app.local_ai import (
            OfflineAISession,
            inspect_local_model,
            load_native_checkpoint,
            run_offline_ai,
        )

        if args.improve_dataset:
            if (
                not args.improve_model or not args.output_model
                or args.prepare_dataset or args.dataset_output or args.verify_dataset
                or args.train_corpus or args.eval_corpus
                or args.model or args.prompt or args.inspect_model
                or args.gguf_model or args.llama_executable or args.self_check
                or args.compare_model or args.candidate_model or args.benchmark_suite
                or args.exclude_train_corpus or args.replay_improvement
                or args.load_chat or args.save_chat
                or args.max_output_tokens is not None
                or args.validation_percent != 25 or args.split_seed != 41
            ):
                print("--improve-dataset requires --improve-model and --output-model; optional --epochs, --verify-sources and --protect-suite")
                return 2
            from skeleton.app.local_ai_dataset import improve_native_dataset

            try:
                result = improve_native_dataset(
                    args.improve_model, args.improve_dataset, args.output_model,
                    epochs=args.epochs if args.epochs is not None else 1, original_sources=args.verify_sources,
                    protected_suite=args.protect_suite,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("verified dataset improvement rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(result, sort_keys=True, ensure_ascii=False))
            else:
                receipt = result["improvement"]
                print("Native candidate checkpoint written: " + str(args.output_model))
                print("Dataset ID: " + result["dataset"]["dataset_id"])
                print("held-out perplexity: "
                      + f"{receipt['baseline_perplexity']:.3f} -> {receipt['accepted_perplexity']:.3f}")
                print("Parent checkpoint retained; no independent quality certification")
            return 0

        if args.verify_dataset or args.verify_sources:
            if (
                not args.verify_dataset or args.prepare_dataset or args.dataset_output
                or args.model or args.prompt or args.inspect_model
                or args.gguf_model or args.llama_executable or args.self_check
                or args.train_corpus or args.output_model or args.improve_model
                or args.compare_model or args.candidate_model or args.eval_corpus
                or args.benchmark_suite or args.exclude_train_corpus
                or args.protect_suite or args.replay_improvement
                or args.load_chat or args.save_chat
                or args.epochs is not None or args.max_output_tokens is not None
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
                or args.gguf_model or args.llama_executable or args.self_check
                or args.train_corpus or args.output_model or args.improve_model
                or args.compare_model or args.candidate_model or args.eval_corpus
                or args.benchmark_suite or args.exclude_train_corpus
                or args.protect_suite or args.replay_improvement
                or args.load_chat or args.save_chat
                or args.verify_dataset or args.verify_sources
                or args.epochs is not None or args.max_output_tokens is not None
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
        if args.self_check:
            if any((
                args.model, args.gguf_model, args.llama_executable,
                args.inspect_model, args.train_corpus, args.improve_model,
                args.compare_model, args.candidate_model, args.eval_corpus,
                args.benchmark_suite, args.exclude_train_corpus, args.protect_suite,
                args.replay_improvement, args.output_model, args.prompt,
                args.load_chat, args.save_chat,
                args.epochs is not None, args.max_output_tokens is not None,
            )):
                print("local-ai --self-check does not accept model, dataset or training options")
                return 2
            from skeleton.app.local_ai_acceptance import run_offline_acceptance

            result = run_offline_acceptance()
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            else:
                for check in result["checks"]:
                    print(("[PASS] " if check["passed"] else "[FAIL] ") + str(check["name"]))
                print("Offline native self-check: " + ("PASS" if result["passed"] else "FAIL"))
                print("Model quality, GGUF weights and enterprise release: not certified")
            return 0 if result["passed"] else 1

        if args.gguf_model or args.llama_executable:
            if (
                not args.gguf_model or not args.llama_executable or not args.prompt
                or args.model or args.inspect_model or args.train_corpus
                or args.improve_model or args.compare_model or args.candidate_model
                or args.eval_corpus or args.benchmark_suite or args.exclude_train_corpus
                or args.protect_suite or args.replay_improvement or args.output_model
                or args.load_chat or args.save_chat or args.epochs is not None
            ):
                print("GGUF inference requires --gguf-model, --llama-executable and --prompt only")
                return 2
            from skeleton.app.local_ai_gguf import generate_local_gguf_sync

            try:
                evidence = generate_local_gguf_sync(
                    args.llama_executable, args.gguf_model, args.prompt,
                    max_output_tokens=(
                        args.max_output_tokens if args.max_output_tokens is not None
                        else 128
                    ),
                )
            except (ValueError, RuntimeError, OSError) as exc:
                print("local GGUF request rejected: " + type(exc).__name__ + ": " + str(exc))
                return 1
            if args.as_json:
                print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
            else:
                print(evidence["text"])
            return 0

        # Never accept tuning switches that a mode would silently ignore.
        # A replay always uses epochs pinned inside its original receipt;
        # inspection, evaluation and inference do not train any weights.
        if args.epochs is not None and (
            not args.train_corpus
            or args.replay_improvement
            or args.compare_model
            or (args.candidate_model and not args.improve_model)
            or args.benchmark_suite
        ):
            print("--epochs applies only to local training or continued training")
            return 2
        if args.max_output_tokens is not None and (
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
                    args.output_model, epochs=args.epochs if args.epochs is not None else 1,
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
                receipt = train_local_text(args.train_corpus, args.output_model, epochs=args.epochs if args.epochs is not None else 1)
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
                answer = asyncio.run(session.ask(args.prompt, max_output_tokens=args.max_output_tokens if args.max_output_tokens is not None else 8))
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
        if bool(args.full):
            print(CHROMA_FULL_PROFILE_BLOCKED)
            return 1
        if bool(args.production) and bool(args.hot):
            print("--production and --hot are mutually exclusive")
            return 2
        # Invalid verification budgets must never start containers first.
        if args.verify_attempts < 1 or not 0 <= args.verify_delay <= 60:
            print("startup verification requires positive attempts and delay from 0 to 60 seconds")
            return 2
        checks = preflight(root, runtime=True, manifest=manifest)
        if not checks_ok(checks):
            for check in checks:
                if not check.ok and check.required:
                    print(f"[FAIL] {check.message}")
            print("application start aborted: runtime preflight failed")
            return 1
        from skeleton.app.preloader import inspect_host

        host = inspect_host(root, require_pip=False)
        if not host.ready:
            for check in host.checks:
                if check.required and not check.ok:
                    print(f"[FAIL] {check.detail}; {check.remediation}")
            return 1
        manifest = runtime_manifest(manifest, root=root)
        mode = "production" if bool(args.production) else "development"
        try:
            startup_command = compose_command(
                "up",
                manifest=manifest,
                full=bool(args.full),
                build=not bool(args.no_build),
                hot=bool(args.hot),
            )
        except ValueError as exc:
            print(str(exc))
            return 1
        exit_code = _run_compose(
            startup_command,
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
            print("application services: ready; AI availability is reported separately by app doctor --live")
            return 0
        print("application start: services launched but readiness verification failed")
        return 1
    if command == "smoke":
        from skeleton.app.health import probes_ok, wait_for_application

        manifest = runtime_manifest(manifest, root=root)
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
