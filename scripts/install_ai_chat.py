#!/usr/bin/env python3
"""Configure, start, and prove a real hosted Jeeves chat installation.

This is an operator-only first-install transaction. It does not invent provider
responses, bypass local-model guards, publish an API endpoint or embed secrets
in a mobile build. The optional live acceptance is deliberately a separate
explicit authorization, because it sends one message to the hosted provider.
"""

from __future__ import annotations

import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.app.assembly import find_repo_root
from skeleton.app.installer import InstallReceipt, install_application
from skeleton.app.setup_runtime import ensure_runtime_environment
from scripts.ai_chat_installed_smoke import (
    ChatApi,
    ProbeFailure,
    backend_origin,
    exercise,
    interactive_login,
    private_bearer_token,
    readiness,
)
from scripts.configure_ai_chat_hosted import (
    ActivationError,
    activate_hosted_ai,
    checked_key,
    checked_model,
    private_provider_key,
)


class InstallationBlocked(RuntimeError):
    """A bounded nonsecret operator-facing installation blocker."""


def _stage(name: str, success: bool, **data) -> None:
    print(json.dumps({"phase": name, "ok": success, **data}, sort_keys=True, separators=(",", ":")), flush=True)


def _receipt(receipt: InstallReceipt) -> dict[str, object]:
    # Only phase names, success flags and required flags are emitted; installer
    # text may contain paths and must not be passed to external telemetry.
    return {
        "phases": [
            {"name": phase.name, "ok": phase.ok, "required": phase.required}
            for phase in receipt.phases
        ],
        "service_health_only": True,
    }


def _validate_options(args: argparse.Namespace) -> None:
    if not args.apply and (
        args.start or args.exercise or args.key_file is not None
        or args.prompt_key or args.admin_password_file is not None
        or args.admin_email is not None or args.allow_switch_from_local
        or args.replace_existing_key
    ):
        raise InstallationBlocked("No changes were applied: sensitive or live actions require --apply.")
    if args.exercise and not args.start:
        raise InstallationBlocked("--exercise needs --start so a qualified backend is running.")
    if args.exercise and not args.base_url:
        raise InstallationBlocked("--exercise needs --base-url pointing at the real installed backend.")
    if args.exercise and not (args.login_email or args.token_file):
        raise InstallationBlocked("--exercise needs --login-email or --token-file for a real account.")
    if args.token_file and args.login_email:
        raise InstallationBlocked("Choose either --login-email or --token-file, not both.")
    if (args.login_email or args.token_file or args.base_url or args.allow_loopback_http) and not args.exercise:
        raise InstallationBlocked("Account and network parameters may only accompany explicit --exercise.")
    if args.allow_loopback_http and args.base_url and not args.exercise:
        raise InstallationBlocked("Loopback HTTP is permitted only for an explicit local test.")
    if args.admin_email and not args.admin_password_file:
        raise InstallationBlocked("Account bootstrap requires --admin-password-file with --admin-email.")
    if args.admin_password_file and not args.admin_email:
        raise InstallationBlocked("--admin-password-file requires --admin-email.")
    if args.timeout < 10 or args.timeout > 600:
        raise InstallationBlocked("--timeout must be between 10 and 600 seconds.")
    if args.exercise and args.base_url:
        backend_origin(args.base_url, allow_loopback_http=args.allow_loopback_http)
    checked_model(args.model)


def _hosted_key(args: argparse.Namespace) -> str | None:
    if args.key_file is not None:
        return private_provider_key(args.key_file)
    if args.prompt_key:
        return checked_key(getpass("Server-side provider key (not echoed): "))
    return None  # Existing approved server-side key may be reused.


def configure_and_start(
    args: argparse.Namespace,
    *,
    setup: Callable = ensure_runtime_environment,
    configure: Callable = activate_hosted_ai,
    installer: Callable = install_application,
    client_factory: Callable = ChatApi,
) -> int:
    """Ordered host-only workflow; no success claim without independent inference.

    Dependencies are injectable for source-level tests only. Real acceptance
    always calls the installed backend using the authenticated product API.
    """
    _validate_options(args)
    root = Path(args.root).resolve() if args.root is not None else find_repo_root()
    if not args.apply:
        _stage("planned", True, model=args.model, provider="openai",
               applied=False, started=False, inference_verified=False)
        return 0
    # Validate and read the key before any host mutation. The secret itself
    # is kept in-process and never logged or passed in command arguments.
    key = _hosted_key(args)
    setup(root, admin_email=args.admin_email, admin_password_file=args.admin_password_file)
    _stage("host-setup", True, provider_secrets_logged=False)
    config = configure(
        root,
        model=args.model,
        key=key,
        allow_switch_from_local=args.allow_switch_from_local,
        replace_existing_key=args.replace_existing_key,
    )
    if config.get("provider") != "openai" or config.get("local_guard_bypassed") is not False:
        raise InstallationBlocked("The activated provider did not preserve the guarded runtime contract.")
    _stage("hosted-provider", True, provider="openai", model=args.model,
           changed=bool(config.get("configuration_changed")), inference_verified=False)
    receipt = installer(
        root, install_python=not args.skip_python, start=args.start, production=True,
        admin_email=args.admin_email, admin_password_file=args.admin_password_file,
    )
    _stage("installed-services", bool(receipt.ok), **_receipt(receipt))
    if not receipt.ok:
        raise InstallationBlocked(
            "The canonical installer did not qualify every required phase. "
            "Inspect app doctor --live, backend and engine logs; do not release."
        )
    if not args.start:
        _stage("complete", True, installed=True, started=False, inference_verified=False,
               next="Run this command with --start, then explicitly --exercise with a real account.")
        return 0

    _stage("services-started", True, inference_verified=False)
    if not args.exercise:
        _stage("complete", True, installed=True, started=True, inference_verified=False,
               next="Run scripts/ai_chat_installed_smoke.py --exercise to qualify a real response.")
        return 0

    # A real deployment can have green liveness with a missing model or an
    # authentication/tenant failure. Treat these as an incomplete installation.
    origin = backend_origin(args.base_url, allow_loopback_http=args.allow_loopback_http)
    api = client_factory(origin, "")
    token = private_bearer_token(args.token_file) if args.token_file else interactive_login(api, args.login_email)
    api.token = token
    verdict = readiness(api)
    _stage("chat-readiness", bool(verdict["ready"]), checks=verdict["checks"],
           model_count=verdict["model_count"], inference_verified=False)
    if not verdict["ready"]:
        raise InstallationBlocked("AI chat is not ready: engine, durable storage or a selectable model remains unavailable.")
    proof = exercise(
        api, verdict, seconds=args.timeout,
        prompt="Answer in one short sentence confirming this is a real installed Jeeves chat turn.",
    )
    if not all(proof.get(key) is True for key in ("persisted", "replay_verified")) or proof.get("model_receipts", 0) < 1:
        raise InstallationBlocked("AI chat did not provide complete canonical persistence and provider proof.")
    _stage("complete", True, installed=True, started=True,
           inference_verified=True, thread_id=proof["thread_id"],
           answer_characters=proof["answer_characters"],
           provider_receipts=proof["model_receipts"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="canonical Skeleton checkout containing the host-only .env")
    parser.add_argument("--model", required=True, help="real approved OpenAI model ID; never a placeholder")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--key-file", type=Path, help="owner-private API key file, 0600 on POSIX")
    source.add_argument("--prompt-key", action="store_true", help="prompt for a secret without echo or argv exposure")
    parser.add_argument("--apply", action="store_true", help="explicitly write private configuration")
    parser.add_argument("--start", action="store_true", help="run canonical production installer and start services")
    parser.add_argument("--skip-python", action="store_true", help="only if Python dependencies are installed already")
    parser.add_argument("--admin-email", help="optional existing installation owner bootstrap account")
    parser.add_argument("--admin-password-file", type=Path, help="private account bootstrap password file")
    parser.add_argument("--allow-switch-from-local", action="store_true", help="explicitly switch local configuration to hosted")
    parser.add_argument("--replace-existing-key", action="store_true", help="explicitly rotate an existing hosted key")
    parser.add_argument("--exercise", action="store_true", help="opt into exactly one real hosted AI turn")
    parser.add_argument("--base-url", help="the backend origin reachable by the installed client")
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument("--login-email", help="authenticate privately through a hidden account password prompt")
    identity.add_argument("--token-file", type=Path, help="use an existing private real-account bearer token file")
    parser.add_argument("--allow-loopback-http", action="store_true", help="HTTP permitted only to local loopback for diagnostic test")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    try:
        return configure_and_start(args)
    except (ActivationError, ProbeFailure, InstallationBlocked) as exc:
        _stage("blocked", False, reason=str(exc), inference_verified=False)
        return 2
    except (OSError, ValueError, RuntimeError):
        # Avoid echoing sensitive environment values, subprocess arguments,
        # filesystem paths, credentials or provider-generated text.
        _stage("blocked", False, reason="The installation could not be completed safely; inspect local diagnostics.", inference_verified=False)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
