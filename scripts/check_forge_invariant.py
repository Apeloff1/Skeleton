#!/usr/bin/env python3
"""Fail loudly when documented env/config disagrees with Skeleton settings defaults.

Port of hyperforge-cockpit-sota/scripts/check-auth-invariant.mjs pattern:
compare two resolved views of the same flags and exit non-zero on divergence.

Here we compare:
  - **documented** forge-relevant keys from .env.example / frontend/.env.example
  - **settings** defaults (and env overrides) from skeleton.config

Exit codes:
  0  agree (or only informational skips)
  1  diverged
  2  could not observe / load settings
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Keys we treat as forge-path / auth-adjacent invariants.
# Map: documented env name -> (settings accessor description, expected default or None)
DOCUMENTED_KEYS = (
    "EXPO_PUBLIC_BACKEND_URL",
    "EXPO_PUBLIC_SKELETON_URL",
    "JWT_SECRET",
    "MONGO_URL",
    "CORS_ORIGINS",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def compare_invariant(*, documented: dict[str, str], runtime: dict[str, Any]) -> dict[str, Any]:
    """Compare documented template values against runtime/settings-derived values.

    Divergence rules (fail closed on real mismatches):
    - If a key is documented AND present in runtime with a conflicting meaning, status=diverged.
    - Missing observation on either side alone is indeterminate (exit 2 when all indeterminate).
    """
    issues: list[str] = []
    oks: list[str] = []
    indeterminates: list[str] = []

    # Port URLs: Skeleton API settings port vs documented frontend URLs
    api_port = runtime.get("api_port")
    backend_doc = documented.get("EXPO_PUBLIC_BACKEND_URL", "")
    skeleton_doc = documented.get("EXPO_PUBLIC_SKELETON_URL", "")

    def _port_from_url(url: str) -> int | None:
        m = re.search(r":(\d+)(?:/|$)", url)
        return int(m.group(1)) if m else None

    if api_port is None:
        indeterminates.append("[forge-invariant] could not read API port from settings")
    else:
        # Backend URL should target legacy/settings API port when documented.
        bp = _port_from_url(backend_doc)
        if not backend_doc:
            indeterminates.append("[forge-invariant] EXPO_PUBLIC_BACKEND_URL missing from env examples")
        elif bp is None:
            issues.append(f"[forge-invariant] EXPO_PUBLIC_BACKEND_URL has no port: {backend_doc!r}")
        elif bp != int(api_port):
            # Soft: document mismatch between frontend backend URL and settings API port
            issues.append(
                f"[forge-invariant] EXPO_PUBLIC_BACKEND_URL port {bp} != settings API port {api_port}"
            )
        else:
            oks.append(f"[forge-invariant] backend URL port matches settings API port {api_port}")

        # Skeleton URL should be present and distinct when hexagonal client is wired
        sp = _port_from_url(skeleton_doc) if skeleton_doc else None
        if not skeleton_doc:
            issues.append(
                "[forge-invariant] EXPO_PUBLIC_SKELETON_URL missing from frontend/.env.example "
                "(Skeleton client needs a documented base URL)"
            )
        elif sp is None:
            issues.append(f"[forge-invariant] EXPO_PUBLIC_SKELETON_URL has no port: {skeleton_doc!r}")
        elif sp == int(api_port) and skeleton_doc == backend_doc:
            issues.append(
                "[forge-invariant] EXPO_PUBLIC_SKELETON_URL is identical to BACKEND_URL; "
                "hexagonal Skeleton client should not silently share the legacy base"
            )
        else:
            oks.append(f"[forge-invariant] Skeleton URL documented at port {sp}")

    # Auth: JWT_SECRET must not remain the template placeholder in production-like env
    env_name = str(runtime.get("environment", "development")).lower()
    jwt = documented.get("JWT_SECRET", "")
    if not jwt:
        indeterminates.append("[forge-invariant] JWT_SECRET not documented in .env.example")
    elif env_name in {"production", "staging"} and jwt in {
        "change-me-to-a-long-random-string",
        "change-me",
        "secret",
    }:
        issues.append(
            f"[forge-invariant] JWT_SECRET is a placeholder while environment={env_name}"
        )
    else:
        oks.append("[forge-invariant] JWT_SECRET documentation present")

    # CORS documented vs settings
    cors_doc = documented.get("CORS_ORIGINS")
    cors_rt = runtime.get("cors_origins")
    if cors_doc is None or cors_rt is None:
        indeterminates.append("[forge-invariant] could not compare CORS_ORIGINS")
    else:
        oks.append("[forge-invariant] CORS documentation and settings both observed")

    if issues:
        return {"status": "diverged", "message": "\n".join(issues + oks), "issues": issues}
    if not oks and indeterminates:
        return {
            "status": "indeterminate",
            "message": "\n".join(indeterminates),
            "issues": indeterminates,
        }
    return {
        "status": "ok",
        "message": "\n".join(oks) or "[forge-invariant] ok",
        "issues": [],
    }


def load_runtime() -> dict[str, Any]:
    """Load settings-derived runtime view; prefer skeleton.config, fall back to env."""
    runtime: dict[str, Any] = {
        "environment": os.environ.get("SKELETON_ENVIRONMENT")
        or os.environ.get("SKL_ENVIRONMENT")
        or "development",
        "api_port": None,
        "cors_origins": None,
    }
    # Ensure repo root importable
    sys.path.insert(0, str(ROOT))
    try:
        from skeleton.config import get_settings  # type: ignore

        settings = get_settings()
        # SkeletonSettings / dual trees
        api = getattr(settings, "api", None) or getattr(settings, "server", None)
        if api is not None:
            runtime["api_port"] = getattr(api, "port", None)
            runtime["cors_origins"] = getattr(api, "cors_origins", None)
        runtime["environment"] = str(
            getattr(getattr(settings, "environment", None), "value", None)
            or getattr(settings, "environment", runtime["environment"])
        )
    except Exception as exc:  # noqa: BLE001 — report as indeterminate upstream
        runtime["_error"] = str(exc)
        # last-resort env
        for key in ("SKELETON_API_PORT", "SKL_SERVER_PORT"):
            if key in os.environ:
                runtime["api_port"] = int(os.environ[key])
                break
    return runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    args = parser.parse_args(argv)

    documented: dict[str, str] = {}
    documented.update(_parse_env_file(ROOT / ".env.example"))
    documented.update(_parse_env_file(ROOT / "frontend" / ".env.example"))

    runtime = load_runtime()
    if runtime.get("_error") and runtime.get("api_port") is None:
        msg = f"[forge-invariant] could not load settings: {runtime['_error']}"
        print(msg, file=sys.stderr)
        return 2

    result = compare_invariant(documented=documented, runtime=runtime)
    if args.json:
        import json

        print(json.dumps(result, indent=2))
    else:
        stream = sys.stdout if result["status"] == "ok" else sys.stderr
        print(result["message"], file=stream)

    if result["status"] == "ok":
        return 0
    if result["status"] == "diverged":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
