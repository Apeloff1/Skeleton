"""
Skeleton API — OAuth utilities for GitHub integration

Provides:
- oauth_card: OAuth app registration instructions
- authorize_url: Generate GitHub authorization URL
- exchange_code: Exchange OAuth code for access token
- client_id: Get configured client ID
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def client_id() -> str:
    """Get the configured GitHub OAuth client ID."""
    return os.getenv("SKELETON_GITHUB_CLIENT_ID", "")


def client_secret() -> str:
    """Get the configured GitHub OAuth client secret."""
    return os.getenv("SKELETON_GITHUB_CLIENT_SECRET", "")


def oauth_card() -> Dict[str, Any]:
    """Return the exact strings to paste into GitHub → New OAuth App."""
    return {
        "app_name": "Skeleton Platform",
        "homepage_url": "https://skeleton.dev",
        "authorization_callback_url": "https://skeleton.dev/auth/github/callback",
        "scopes": ["repo", "read:user", "read:org"],
        "instructions": [
            "1. Go to GitHub → Settings → Developer settings → OAuth Apps → New OAuth App",
            "2. Fill in the fields above",
            "3. Generate a client secret",
            "4. Set SKELETON_GITHUB_CLIENT_ID and SKELETON_GITHUB_CLIENT_SECRET",
        ],
    }


def authorize_url(redirect_uri: Optional[str] = None, scope: str = "repo,read:user") -> Dict[str, Any]:
    """Generate GitHub authorization URL."""
    cid = client_id()
    if not cid:
        return {"error": "SKELETON_GITHUB_CLIENT_ID not set"}
    
    redirect = redirect_uri or "https://skeleton.dev/auth/github/callback"
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={cid}"
        f"&redirect_uri={redirect}"
        f"&scope={scope}"
    )
    
    return {
        "url": url,
        "client_id": cid[:4] + "..." + cid[-4:] if len(cid) > 8 else cid,
        "scope": scope,
    }


def exchange_code(code: str) -> Dict[str, Any]:
    """Exchange OAuth authorization code for access token.
    
    Note: This is a stub. In production, this would make a POST
    request to https://github.com/login/oauth/access_token
    """
    secret = client_secret()
    if not secret:
        return {"error": "SKELETON_GITHUB_CLIENT_SECRET not set"}
    
    # Stub: in production, make actual OAuth token exchange
    return {
        "access_token": "gho_stub_token",
        "token_type": "bearer",
        "scope": "repo,read:user",
        "note": "This is a stub. Implement actual token exchange in production.",
    }
