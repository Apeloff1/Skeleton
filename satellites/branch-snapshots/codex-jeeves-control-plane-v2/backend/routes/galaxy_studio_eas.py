"""
Galaxy Studio — EAS proxy sub-router.

Extracted from routes/galaxy_studio.py (Feb 2026, Phase-2 decomposition) so
the main monolith shrinks and EAS-specific concerns can be tested / replaced
independently. Both endpoints are pure subprocess proxies — they do not touch
any of the in-memory build state owned by the main galaxy_studio module, so
the extraction is safe and side-effect-free.

Mounted from routes/galaxy_studio.py via ``router.include_router(...)``
without an additional prefix so the public paths stay identical
(``/api/galaxy-studio/eas/whoami``, ``/api/galaxy-studio/eas/build-status/{id}``).
"""

from __future__ import annotations
import os
import json
import subprocess

from fastapi import APIRouter
from dotenv import load_dotenv

# Sub-router — NO prefix so the parent's "/api/galaxy-studio" prefix applies.
router = APIRouter(tags=["galaxy-studio"])

load_dotenv()  # one-shot, idempotent across imports


def _read_eas_token() -> str:
    """Defensive re-read of EXPO_TOKEN — supports hot-swap during a long-lived
    process where the operator may have updated the .env file."""
    try:
        load_dotenv(override=False)
    except Exception:
        pass
    return os.environ.get("EXPO_TOKEN", "")


def _eas_env(token: str) -> dict[str, str]:
    env = os.environ.copy()
    env["EXPO_TOKEN"] = token
    return env


@router.get("/eas/whoami")
async def eas_whoami() -> dict:
    """Check EAS authentication status using the configured EXPO_TOKEN.

    Returns ``{status, account, email, cli_version, mocked}`` so the frontend
    can show a green pill when the real cloud compile is available.
    """
    token = _read_eas_token()
    if not token:
        return {
            "status": "no_token",
            "mocked": True,
            "message": "EXPO_TOKEN missing. Real EAS compile disabled; fallback ZIP only.",
        }
    env = _eas_env(token)
    try:
        res = subprocess.run(
            ["eas", "whoami", "--non-interactive"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        ver_res = subprocess.run(
            ["eas", "--version"], env=env, capture_output=True, text=True, timeout=10,
        )
        cli_version = "?"
        if ver_res.returncode == 0:
            raw = (ver_res.stdout or ver_res.stderr or "").strip()
            for tok in raw.split():
                if tok.startswith("eas-cli/"):
                    cli_version = tok.split("/", 1)[1]
                    break
            if cli_version == "?" and raw:
                cli_version = raw.split()[0]
        if res.returncode != 0:
            return {
                "status": "auth_failed",
                "mocked": True,
                "cli_version": cli_version,
                "message": (res.stderr or res.stdout or "").strip()[-400:],
            }
        out = (res.stdout or "").strip()
        lines = [
            ln for ln in out.split("\n")
            if ln and "eas-cli@" not in ln
            and "upgrade" not in ln.lower()
            and "outdated" not in ln.lower()
        ]
        # Expected output format:
        #   galaxystudio (authenticated using EXPO_TOKEN)
        #   raymond.rendalsvik@gmail.com
        account = lines[0].split(" ")[0] if lines else ""
        email = lines[1].strip() if len(lines) >= 2 else ""
        return {
            "status": "authenticated",
            "mocked": False,
            "account": account,
            "email": email,
            "cli_version": cli_version,
            "message": f"EAS cloud compile ready. Signed in as {account}.",
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "mocked": True, "message": "eas whoami timed out"}
    except FileNotFoundError:
        return {
            "status": "cli_missing",
            "mocked": True,
            "message": "eas CLI not installed on backend host. Install via npm i -g eas-cli.",
        }
    except Exception as e:
        return {"status": "error", "mocked": True, "message": str(e)[:300]}


@router.get("/eas/build-status/{eas_build_id}")
async def eas_build_status(eas_build_id: str) -> dict:
    """Proxy to ``eas build:view --json`` so the frontend can poll a real EAS
    build without a dedicated Jeeves build record."""
    token = _read_eas_token()
    if not token:
        return {"status": "no_token", "message": "EXPO_TOKEN missing."}
    env = _eas_env(token)
    try:
        res = subprocess.run(
            ["eas", "build:view", eas_build_id, "--json", "--non-interactive"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        if res.returncode != 0:
            return {
                "status": "view_failed",
                "eas_build_id": eas_build_id,
                "error": (res.stderr or "")[-400:],
            }
        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError:
            return {"status": "parse_error", "raw": (res.stdout or "")[:400]}
        artifacts = (data or {}).get("artifacts", {}) or {}
        return {
            "status": (data or {}).get("status", "unknown"),
            "eas_build_id": eas_build_id,
            "platform": (data or {}).get("platform"),
            "profile": (data or {}).get("buildProfile"),
            "artifact_url": artifacts.get("buildUrl") or artifacts.get("applicationArchiveUrl"),
            "logs_url": (data or {}).get("logsUrl"),
            "expo_dashboard": f"https://expo.dev/accounts/galaxystudio/builds/{eas_build_id}",
            "started_at": (data or {}).get("createdAt"),
            "completed_at": (data or {}).get("completedAt"),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "eas_build_id": eas_build_id}
    except Exception as e:
        return {"status": "error", "eas_build_id": eas_build_id, "error": str(e)[:300]}


__all__ = ["router", "eas_build_status"]
