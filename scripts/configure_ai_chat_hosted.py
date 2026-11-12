#!/usr/bin/env python3
"""Owner-only hosted AI chat activation in the existing private Skeleton .env.

The command never sends a request to a model provider and never claims that
hosted inference is working. A completed model turn must be observed separately.
"""

from __future__ import annotations

import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.app.assembly import find_repo_root
from skeleton.app.setup_runtime import (
    _atomic_write,
    _is_placeholder,
    _parse_env,
    _read_existing_env,
    _replace_env_value,
    _setup_process_lock,
)

_KEY = re.compile(r"sk-[A-Za-z0-9_-]{12,500}\Z")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_LOCAL_CONFIG = ("AI_LOCAL_MODEL_PATH", "AI_LOCAL_DEPLOYMENT_PATH", "AI_LOCAL_MODEL_CATALOG_PATH")


class ActivationError(ValueError):
    """A bounded nonsecret configuration error."""


def private_provider_key(path: Path) -> str:
    """Read a stable owner-private single-link key file without pathname following."""
    if path.is_symlink():
        raise ActivationError("The provider key file must not be a symlink.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ActivationError("The provider key file could not be opened.") from None
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        try:
            named = os.lstat(path)
        except OSError:
            raise ActivationError("The provider key file disappeared.") from None
        if not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(named.st_mode) or (
            before.st_dev, before.st_ino
        ) != (named.st_dev, named.st_ino) or before.st_size > 1024 or (
            os.name != "nt" and (before.st_nlink != 1 or bool(before.st_mode & 0o077))
        ):
            raise ActivationError("The provider key must be a bounded private regular file (chmod 600).")
        raw = handle.read(1025)
        after = os.lstat(path)
        if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ActivationError("The provider key file changed while being read.")
    if len(raw) > 1024:
        raise ActivationError("The provider key file is too large.")
    try:
        value = raw.decode("ascii").strip()
    except UnicodeError:
        raise ActivationError("The provider key must be printable ASCII.") from None
    return checked_key(value)


def checked_key(value: str) -> str:
    if not _KEY.fullmatch(value):
        raise ActivationError("The provider key format is invalid; no credentials were stored.")
    return value


def checked_model(value: str) -> str:
    if not _MODEL.fullmatch(value):
        raise ActivationError("The model ID is invalid; use a supported provider model name.")
    return value


def activate_hosted_ai(
    root: Path,
    *,
    model: str,
    key: str | None = None,
    allow_switch_from_local: bool = False,
    replace_existing_key: bool = False,
) -> dict[str, object]:
    """Atomically configure a real hosted model without altering other host secrets."""
    model = checked_model(model)
    root = Path(root).resolve()
    env_path = root / ".env"
    if not env_path.exists():
        raise ActivationError("No private .env exists. Run the canonical Skeleton app installer/setup first.")
    if key is not None:
        key = checked_key(key)
    with _setup_process_lock(root):
        try:
            text, _ = _read_existing_env(env_path, private=True)
        except (OSError, UnicodeError, ValueError):
            raise ActivationError("The installed private .env cannot be safely read.") from None
        values = _parse_env(text)
        active = values.get("AI_PROVIDER", "").strip().lower()
        existing_key = values.get("OPENAI_API_KEY", "").strip()
        if _is_placeholder(existing_key):
            existing_key = ""
        local_model_present = any(values.get(name, "").strip() for name in _LOCAL_CONFIG)
        if active and active not in {"local", "openai"}:
            raise ActivationError("Existing nonlocal provider selection must be migrated explicitly.")
        if (active == "local" and local_model_present) and not allow_switch_from_local:
            raise ActivationError(
                "A local deployment is configured. Use --allow-switch-from-local "
                "only if the installation owner intentionally chooses hosted inference."
            )
        if existing_key and key and key != existing_key and not replace_existing_key:
            raise ActivationError(
                "The provider key already exists. Use --replace-existing-key to rotate deliberately."
            )
        selected_key = key or existing_key
        if not selected_key:
            raise ActivationError("No provider key supplied. Use --key-file or a private interactive prompt.")
        checked_key(selected_key)
        amended = _replace_env_value(text, "AI_PROVIDER", "openai")
        amended = _replace_env_value(amended, "AI_MODEL", model)
        amended = _replace_env_value(amended, "OPENAI_API_KEY", selected_key)
        if len(amended.encode("utf-8")) > 256 * 1024:
            raise ActivationError("The configured private .env would exceed the input limit.")
        changed = amended != text
        if changed:
            _atomic_write(env_path, amended)
    return {
        "ok": True,
        "configuration_changed": changed,
        "provider": "openai",
        "model": model,
        "backend_restart_required": changed,
        "real_inference_verified": False,
        "local_guard_bypassed": False,
        "next": "Recreate the engine with canonical app installer commands, then run scripts/ai_chat_installed_smoke.py --exercise.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="Skeleton installation root containing private .env")
    parser.add_argument("--model", required=True, help="an approved real OpenAI provider model ID")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--key-file", type=Path, help="private provider key file (mode 0600 on POSIX)")
    source.add_argument("--prompt-key", action="store_true", help="prompt privately for provider key")
    parser.add_argument("--allow-switch-from-local", action="store_true", help="explicitly switch away from a configured local model")
    parser.add_argument("--replace-existing-key", action="store_true", help="rotate an existing provider key")
    parser.add_argument("--apply", action="store_true", help="explicitly commit the validated private .env update")
    args = parser.parse_args(argv)
    try:
        model = checked_model(args.model)
        if not args.apply:
            print(json.dumps({
                "ok": True, "applied": False, "provider": "openai", "model": model,
                "next": "Pass --apply to configure the private host environment; no credentials have been read or stored.",
            }))
            return 0
        key = private_provider_key(args.key_file) if args.key_file else (
            checked_key(getpass("Server-side OpenAI API key (hidden): ")) if args.prompt_key else None
        )
        report = activate_hosted_ai(
            args.root or find_repo_root(), model=model, key=key,
            allow_switch_from_local=args.allow_switch_from_local,
            replace_existing_key=args.replace_existing_key,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ActivationError, OSError, ValueError) as exc:
        # Never print raw exceptions from host files or provider; these can
        # contain local pathnames, secret values and even attacker-controlled text.
        message = str(exc) if isinstance(exc, ActivationError) else "Hosted provider configuration failed safely."
        print(json.dumps({"ok": False, "error": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
