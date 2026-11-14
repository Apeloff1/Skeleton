#!/usr/bin/env python3
"""Install Jeeves as a real, pinned, LOCAL-ONLY text model (never OpenAI).

Model files are operator-owned and never fabricated, downloaded or copied.
The existing native llama.cpp GGUF runtime performs optional live inference.
Docker Compose binds the exact approved model and binary read-only. The trusted
engine guard, database, authenticated chat and receipt validators remain in
force: successful Docker startup NEVER counts as a successful model response.

Multimodal capabilities may supply advisory sources, but no remote or other
model may become the primary Jeeves text generator. The UI is a client of a
local/on-premises host; a phone is not itself running the native model.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.configure_ai_chat import main as configure_private_chat
from scripts.ai_chat_installed_smoke import (
    ChatApi, ProbeFailure, backend_origin, exercise, interactive_login,
    private_bearer_token, readiness,
)
from skeleton.ai.jeeves_local_policy import (
    JeevesLocalPolicyError, require_local_configuration,
)
from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeployment, LocalModelDeploymentError,
    qualify_local_model_deployment_sync,
)
from skeleton.app.setup_runtime import _parse_env, _read_existing_env


class InstallationBlocked(RuntimeError):
    """A nonsecret local-only installation or qualification failure."""


def _stage(name: str, ok: bool, **metadata: object) -> None:
    print(json.dumps(
        {"phase": name, "ok": ok, **metadata},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ), flush=True)


def _validate(args: argparse.Namespace) -> None:
    if (args.start or args.exercise or args.force or args.admin_email
            or args.admin_password_file) and not args.apply:
        raise InstallationBlocked("Host configuration or startup needs explicit --apply.")
    if args.exercise and (not args.start or not args.base_url):
        raise InstallationBlocked("One live application turn requires --start and --base-url.")
    if args.exercise and not (args.token_file or args.login_email):
        raise InstallationBlocked("Live application inference requires --token-file or --login-email.")
    if args.token_file and args.login_email:
        raise InstallationBlocked("Select one real-account authentication method.")
    if (args.base_url or args.token_file or args.login_email or args.allow_loopback_http) and not args.exercise:
        raise InstallationBlocked("Account and network options require explicit --exercise.")
    if bool(args.admin_email) != bool(args.admin_password_file):
        raise InstallationBlocked("Administrator bootstrap needs both email and private password file.")
    if args.timeout not in range(10, 601):
        raise InstallationBlocked("Completion timeout must be 10 to 600 seconds.")
    if args.base_url:
        backend_origin(args.base_url, allow_loopback_http=args.allow_loopback_http)
    if not args.deployment:
        raise InstallationBlocked("Jeeves requires an existing local deployment manifest.")
    if args.env_file.name != ".env" and not (
        args.env_file.name.startswith(".env.") and not args.env_file.name.endswith(".example")
    ):
        raise InstallationBlocked("Choose a private .env or .env.* runtime file.")


def _compose_command(env_file: Path, action: str) -> list[str]:
    if action not in {"config", "up"}:
        raise ValueError("unknown Compose action")
    override = Path(str(env_file) + ".compose.json")
    cmd = [
        "docker", "compose", "--project-directory", str(ROOT),
        "--env-file", str(env_file), "-f", str(ROOT / "docker-compose.yml"),
        "-f", str(override),
    ]
    if action == "config":
        return cmd + ["config", "--quiet"]
    return cmd + ["up", "-d", "--build", "mongo", "skeleton", "backend", "frontend"]


def _run_compose(
    env_file: Path,
    *,
    runner: Callable = subprocess.run,
) -> None:
    """Validate exactly this private Compose epoch and start the intended stack.

    stdout/stderr may expose interpolated provider and database secrets, so
    neither command is logged or returned. The validated environment is
    re-fingerprinted before/after; a changed source invalidates acceptance.
    """
    def snapshot() -> str:
        import hashlib
        raw, _ = _read_existing_env(env_file, private=True)
        if len(raw) > 256 * 1024:
            raise InstallationBlocked("Private runtime file exceeds its bound.")
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    original = snapshot()
    for action, timeout in (("config", 60), ("up", 1800)):
        if snapshot() != original:
            raise InstallationBlocked("Private environment changed during Compose admission.")
        try:
            proc = runner(
                _compose_command(env_file, action), cwd=ROOT, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                text=True, timeout=timeout,
                env={**os.environ, "COMPOSE_REMOVE_ORPHANS": "0"},
            )
        except (OSError, subprocess.SubprocessError):
            raise InstallationBlocked("Docker Compose could not complete local startup.") from None
        if snapshot() != original:
            raise InstallationBlocked("Private environment changed during Compose startup.")
        if proc.returncode != 0:
            raise InstallationBlocked(
                "Docker Compose " + action + " failed; inspect local service logs and guard state."
            )


def _private_configured(env_file: Path) -> None:
    """Check the result of the *actual* private operator configuration."""
    raw, _ = _read_existing_env(env_file, private=True)
    values = _parse_env(raw)
    try:
        source = require_local_configuration(values)
    except JeevesLocalPolicyError as exc:
        raise InstallationBlocked(str(exc)) from None
    if source != "AI_LOCAL_DEPLOYMENT_PATH":
        raise InstallationBlocked("Jeeves needs a single pinned local GGUF deployment.")
    if values.get("AI_LOCAL_GUARD_REQUIRED") not in {"1", "true"}:
        raise InstallationBlocked("Jeeves requires the protected local inference guard.")
    if any(values.get(key, "").strip() for key in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY")):
        raise InstallationBlocked("The primary Jeeves process may not carry hosted API credentials.")


def build(
    args: argparse.Namespace,
    *,
    deployment_loader: Callable = LocalModelDeployment.load,
    configurator: Callable = configure_private_chat,
    local_qualifier: Callable = qualify_local_model_deployment_sync,
    runner: Callable = subprocess.run,
    api_factory: Callable = ChatApi,
) -> int:
    _validate(args)
    source = Path(args.deployment).expanduser().resolve(strict=True)
    manifest = deployment_loader(source)
    if manifest.model_id != "jeeves" or manifest.runtime_kind != "llama.cpp-cli":
        raise InstallationBlocked("Jeeves requires a genuine digest-pinned local llama.cpp deployment with model_id=jeeves.")
    _stage(
        "model-source", True, provider="local", model_id=manifest.model_id,
        model_sha256=manifest.model_sha256, runtime_sha256=manifest.executable_sha256,
        network_required=False, inference_verified=False,
    )

    if args.live_local:
        # This invokes the *real* pinned subprocess on this host. It is
        # independent from backend/phone readiness and never a fake completion.
        receipt = local_qualifier(
            source, prompt="Write one short sentence as the local Jeeves model.",
            max_output_tokens=32,
        )
        if (
            receipt.get("schema_version") != "skeleton.local_model.qualification.v1"
            or receipt.get("status") != "qualified" or receipt.get("provider") != "local"
            or receipt.get("network_required") is not False
            or receipt.get("model_id") != "jeeves"
            or receipt.get("model_sha256") != manifest.model_sha256
            or receipt.get("executable_sha256") != manifest.executable_sha256
            or not isinstance(receipt.get("receipt_digest"), str)
            or len(receipt["receipt_digest"]) != 64
        ):
            raise InstallationBlocked("The local model returned no bound, completed inference receipt.")
        _stage(
            "live-local-inference", True, provider="local", model_id="jeeves",
            model_sha256=manifest.model_sha256,
            response_receipt=receipt["receipt_digest"], inference_verified=True,
            application_chat_verified=False,
        )

    if getattr(args, "live_local_suite", False):
        # Independent REAL localhost acceptance: two model generations, a
        # complete SQLite/server restart and exact historical replay.
        # It is not a substitute for the protected multi-service guard.
        from scripts.qualify_jeeves_live_local import qualify_jeeves_live_local
        from skeleton.app.local_ai import load_gguf_deployment
        loaded = load_gguf_deployment(source)
        if loaded.model_id != "jeeves" or loaded.model_digest != manifest.model_sha256:
            raise InstallationBlocked("Advanced local qualification loaded a different model identity.")
        accepted = qualify_jeeves_live_local(
            loaded, timeout_seconds=args.timeout, output_tokens=16,
        )
        if (
            accepted.get("qualified") is not True
            or accepted.get("model_digest") != manifest.model_sha256
            or accepted.get("actual_model_turns") != 2
            or accepted.get("durable_recovery_verified") is not True
            or accepted.get("read_only_replay_verified") is not True
            or accepted.get("hosted_provider_used") is not False
            or accepted.get("protected_backend_verified") is not False
        ):
            raise InstallationBlocked("Two-turn local inference, restart or recovery failed.")
        _stage(
            "advanced-local-live", True, model_id="jeeves",
            model_sha256=manifest.model_sha256,
            real_model_turns=accepted["actual_model_turns"],
            sqlite_restart_recovered=True, historical_replay_verified=True,
            measured_turn_metrics=accepted["turn_metrics"],
            inference_verified=True, application_chat_verified=False,
        )

    env_file = Path(args.env_file).expanduser().absolute()
    cmd = [
        "--env-file", str(env_file), "--provider", "local",
        "--local-deployment", str(source), "--jeeves-primary",
    ]
    if args.force:
        cmd.append("--force")
    if args.admin_email:
        cmd.extend(["--admin-email", args.admin_email,
                    "--admin-password-file", str(args.admin_password_file)])
    if not args.apply:
        cmd.append("--dry-run")
    # The canonical configurator validates all real GGUF, binary, platform and
    # library pins. No internet access or model acquisition is performed.
    outcome = configurator(cmd)
    if outcome != 0:
        raise InstallationBlocked("Local Jeeves configuration was rejected; no hosted fallback was attempted.")
    if not args.apply:
        _stage("dry-run", True, applied=False, model="jeeves",
               started=False, application_chat_verified=False)
        return 0
    _private_configured(env_file)
    _stage("local-configured", True, provider="local", model_id="jeeves",
           protected_inference_required=True, remote_fallback=False,
           inference_verified=False)
    if not args.start:
        return 0

    _run_compose(env_file, runner=runner)
    # Docker 'up' only proves the orchestration command returned successfully.
    _stage("compose-started", True, model_id="jeeves",
           inference_verified=False, application_chat_verified=False)
    if not args.exercise:
        return 0

    api = api_factory(
        backend_origin(args.base_url, allow_loopback_http=args.allow_loopback_http), "",
    )
    api.token = (
        private_bearer_token(args.token_file)
        if args.token_file else interactive_login(api, args.login_email)
    )
    snapshot = readiness(api)
    _stage("application-readiness", snapshot["ready"],
           model_count=snapshot["model_count"], inference_verified=False)
    if not snapshot["ready"]:
        raise InstallationBlocked(
            "Trusted local model, guarded engine or canonical storage is not ready."
        )
    proof = exercise(
        api, snapshot, seconds=args.timeout,
        prompt="Reply in one sentence using only the installed local Jeeves model.",
    )
    if not (proof.get("persisted") is True and proof.get("replay_verified") is True
            and isinstance(proof.get("model_receipts"), int)
            and proof["model_receipts"] > 0):
        raise InstallationBlocked("Jeeves local reply was not independently persisted and replayed.")
    _stage("complete", True, provider="local", model_id="jeeves",
           inference_verified=True, application_chat_verified=True,
           canonical_thread_id=proof["thread_id"], provider_receipts=proof["model_receipts"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", type=Path, required=True, help="operator-owned digest-pinned llama.cpp/GGUF manifest with model_id=jeeves")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="private Compose environment (default: repo .env)")
    parser.add_argument("--apply", action="store_true", help="explicit private Compose configuration write")
    parser.add_argument("--force", action="store_true", help="explicitly reconcile existing private configuration without rotating persistent identities")
    parser.add_argument("--start", action="store_true", help="validate and start local Compose engine, backend and frontend")
    parser.add_argument("--live-local", action="store_true", help="execute real offline llama.cpp on this host, verifying a bound completion receipt")
    parser.add_argument("--live-local-suite", action="store_true", help="two real offline model turns across authenticated localhost HTTP, durable SQLite restart and replay")
    parser.add_argument("--admin-email", help="optional pre-approved operator email")
    parser.add_argument("--admin-password-file", type=Path, help="optional owner-private password file")
    parser.add_argument("--exercise", action="store_true", help="one real authenticated canonical application chat completion")
    parser.add_argument("--base-url", help="real installed backend HTTPS origin (or permitted loopback HTTP for local testing)")
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument("--token-file", type=Path, help="private real-account bearer token file")
    auth.add_argument("--login-email", help="private interactive account login")
    parser.add_argument("--allow-loopback-http", action="store_true", help="only for real loopback-host testing")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    try:
        return build(args)
    except (InstallationBlocked, ProbeFailure) as exc:
        _stage("blocked", False, reason=str(exc), inference_verified=False)
        return 2
    except (OSError, ValueError, TypeError, LocalModelDeploymentError, RuntimeError):
        # Never stringify filesystem, credential or model-internal exceptions.
        _stage("blocked", False, reason="Jeeves local model source, deployment or runtime could not be qualified.", inference_verified=False)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
