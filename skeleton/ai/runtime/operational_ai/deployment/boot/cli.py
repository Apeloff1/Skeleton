"""Read-only startup diagnosis and explicitly requested initial principal bind.

No network calls, model inference, implicit migrations, or synthesized model
weights. Returns a redacted error type, never a private database path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .identity import PrincipalBinding, establish_binding, inspect_binding
from .readiness import inspect_readiness
from ..install.doctor import inspect_installed_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strict offline AI principal and readiness custody")
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("bind", "inspect", "doctor"):
        sub = commands.add_parser(name)
        sub.add_argument("--model-root", type=Path, required=True)
        sub.add_argument("--state-dir", type=Path, required=True)
        sub.add_argument("--tenant", required=True)
        sub.add_argument("--user", required=True)
        if name == "doctor":
            sub.add_argument("--memory-key-file", type=Path, required=True)
        if name == "bind":
            sub.add_argument("--approve-new-state", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "doctor":
            result = inspect_readiness(args.model_root, args.state_dir,
                args.memory_key_file, tenant=args.tenant, user=args.user).to_record()
        else:
            model = inspect_installed_model(args.model_root)
            identity = PrincipalBinding(args.tenant, args.user,
                                        model.model_sha256, model.model_sha256)
            if args.action == "bind":
                if not args.approve_new_state:
                    raise ValueError("new state binding requires explicit approval")
                result = establish_binding(args.state_dir, identity)
            else:
                result = inspect_binding(args.state_dir, identity)
            result["release_certified"] = False
        print(json.dumps(result, sort_keys=True))
        return 0
    except (RuntimeError, ValueError, OSError, ImportError) as exc:
        print(json.dumps({"status":"blocked", "reason":type(exc).__name__}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
