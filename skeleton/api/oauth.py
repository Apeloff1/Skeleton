"""GitHub OAuth — token intake for the house, not a third-party wrapper.

Register at https://github.com/settings/applications/new with the
fields in `oauth_card()`. Local callback is the FastAPI route below.
Device-flow and classic PAT remain valid; this is the web-app path.

Env:
  SKELETON_GITHUB_CLIENT_ID
  SKELETON_GITHUB_CLIENT_SECRET
  SKELETON_OAUTH_REDIRECT   (optional override)
"""
from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

AUTHORIZE = "https://github.com/login/oauth/authorize"
ACCESS = "https://github.com/login/oauth/access_token"
USER = "https://api.github.com/user"
DEFAULT_PORT = 8001
DEFAULT_REDIRECT = f"http://127.0.0.1:{DEFAULT_PORT}/api/v1/auth/github/callback"
SCOPES = "repo read:user"


def oauth_card() -> Dict[str, str]:
    """Exact strings for GitHub Developer Settings → New OAuth App."""
    return {
        "application_name": "Skeleton Cortex",
        "homepage_url": "https://github.com/Apeloff1/Skeleton",
        "url": "https://github.com/Apeloff1/Skeleton",
        "application_description": (
            "Tutolage Skeleton — Jeeves neocortex and GameForge. "
            "Interchangeable PFC/midbrain/hemisphere/neo LMs. "
            "OAuth exists so the hive can write tracts back to the canonical repo."
        ),
        "authorization_callback_url": DEFAULT_REDIRECT,
        "authorization_callback_url_alt": f"http://localhost:{DEFAULT_PORT}/api/v1/auth/github/callback",
        "register": "https://github.com/settings/applications/new",
        "pat_faster": "https://github.com/settings/tokens/new?scopes=repo&description=Skeleton%20Cortex%20push",
        "scopes": SCOPES,
    }


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or default)


def redirect_uri() -> str:
    return _env("SKELETON_OAUTH_REDIRECT", DEFAULT_REDIRECT)


def client_id() -> str:
    return _env("SKELETON_GITHUB_CLIENT_ID")


def authorize_url(*, state: Optional[str] = None) -> Dict[str, str]:
    st = state or secrets.token_urlsafe(24)
    q = urllib.parse.urlencode({
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "scope": SCOPES,
        "state": st,
        "allow_signup": "false",
    })
    return {"url": f"{AUTHORIZE}?{q}", "state": st, "redirect_uri": redirect_uri()}


def exchange_code(code: str) -> Dict[str, Any]:
    """Trade the callback `code` for an access token. Never logs the secret."""
    cid, secret = client_id(), _env("SKELETON_GITHUB_CLIENT_SECRET")
    if not cid or not secret:
        return {"ok": False, "error": "missing_client", "hint": "set SKELETON_GITHUB_CLIENT_ID/SECRET"}
    body = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": secret,
        "code": code,
        "redirect_uri": redirect_uri(),
    }).encode("utf-8")
    req = urllib.request.Request(
        ACCESS, data=body, method="POST",
        headers={"Accept": "application/json", "User-Agent": "skeleton-cortex"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": "http", "status": int(exc.code)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}
    token = str(payload.get("access_token") or "")
    if not token:
        return {"ok": False, "error": payload.get("error") or "no_token", "desc": payload.get("error_description")}
    who = _whoami(token)
    return {
        "ok": True,
        "token_type": payload.get("token_type") or "bearer",
        "scope": payload.get("scope") or SCOPES,
        "login": who.get("login"),
        "user_id": who.get("id"),
        # caller must persist; we do not write secrets to disk here
        "has_token": True,
        "token_prefix": token[:6] + "…",
        "access_token": token,
    }


def _whoami(token: str) -> Dict[str, Any]:
    req = urllib.request.Request(
        USER, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                       "User-Agent": "skeleton-cortex", "X-GitHub-Api-Version": "2022-11-28"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}
