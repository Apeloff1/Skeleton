"""
routes/gameforge_auth.py — JWT auth + RBAC (viewer < editor < admin).

Guards sensitive Studio/Vault operations. Security-sensitive configuration is
resolved through ``core.auth_security`` so production defaults fail closed,
local development uses an ephemeral JWT secret, and bootstrap admin credentials
exist only when explicitly configured.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, EmailStr, Field

from core.auth_security import (
    auth_enforced,
    resolve_jwt_secret,
    resolve_seed_admin,
    resolve_session_api,
)

log = logging.getLogger("routes.gameforge_auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

Role = Literal["viewer", "editor", "admin"]
ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 240
_LEGACY_PUBLIC_SEED_EMAIL = "admin@gameforge.io"
_seed_initialized = False

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _secret() -> str:
    return resolve_jwt_secret()


def _enforced() -> bool:
    return auth_enforced()


def _users():
    from core.databases import get_sync_db

    return get_sync_db()["gameforge_users"]


def _sessions():
    from core.databases import get_sync_db

    return get_sync_db()["user_sessions"]


def hash_password(p: str) -> str:
    return _bcrypt.hashpw(p.encode()[:72], _bcrypt.gensalt(rounds=12)).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return _bcrypt.checkpw(p.encode()[:72], h.encode())
    except Exception:  # noqa: BLE001
        return False


DUMMY_HASH = hash_password("dummy-password-for-timing-safety")


def create_access_token(*, sub: str, role: Role) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def seed_admin() -> None:
    """Initialize auth indexes and migrate legacy bootstrap state once per worker.

    Production-like environments disable the retired public bootstrap account
    unless an operator explicitly configures that same email with a new strong
    password. Explicit bootstrap credentials are upserted and password-rotated,
    so deployments upgraded from the old seed cannot retain the retired hash.
    """
    global _seed_initialized
    if _seed_initialized:
        return

    seed = resolve_seed_admin()
    try:
        users = _users()
        users.create_index("email", unique=True)
        sessions = _sessions()
        sessions.create_index("session_token", unique=True)
        sessions.create_index("expires_at", expireAfterSeconds=0)

        if _enforced() and (seed is None or seed.email != _LEGACY_PUBLIC_SEED_EMAIL):
            users.update_one(
                {
                    "email": _LEGACY_PUBLIC_SEED_EMAIL,
                    "auth": "password",
                },
                {
                    "$set": {
                        "disabled": True,
                        "security_migration": "legacy_public_seed_disabled",
                    }
                },
            )

        if seed is not None:
            existing = users.find_one({"email": seed.email})
            existing_hash = existing.get("password_hash") if existing else None
            fields = {
                "role": "admin",
                "disabled": False,
                "auth": "password",
            }
            if not isinstance(existing_hash, str) or not verify_password(
                seed.password,
                existing_hash,
            ):
                fields["password_hash"] = hash_password(seed.password)

            users.update_one(
                {"email": seed.email},
                {
                    "$set": fields,
                    "$setOnInsert": {
                        "email": seed.email,
                        "created_at": datetime.now(timezone.utc),
                    },
                },
                upsert=True,
            )

        _seed_initialized = True
    except Exception:  # noqa: BLE001
        log.exception("auth bootstrap initialization failed")
        if _enforced():
            raise


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]):
    if not token:
        return None
    # 1) Google session token (opaque) — look up in user_sessions.
    try:
        sess = _sessions().find_one({"session_token": token})
        if sess:
            exp = sess.get("expires_at")
            if exp is not None:
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    return None
            return _users().find_one(
                {"email": sess.get("email"), "disabled": {"$ne": True}},
                {"_id": 0, "password_hash": 0},
            )
    except Exception:  # noqa: BLE001
        pass
    # 2) JWT (email/password login).
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
        email, role = payload.get("sub"), payload.get("role")
        if not email or role not in ROLE_RANK:
            return None
    except InvalidTokenError:
        return None
    return _users().find_one(
        {"email": email, "disabled": {"$ne": True}},
        {"_id": 0, "password_hash": 0},
    )


def require_role(min_role: Role):
    """Dependency enforcing a minimum role when auth policy requires it.

    Local development remains open unless explicitly configured otherwise;
    production-like APP_ENV/ENVIRONMENT values enforce authentication by default.
    """

    def dep(user=Depends(get_current_user)):
        if not _enforced():
            return user or {"email": "anonymous", "role": "admin", "dev_mode": True}
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if ROLE_RANK[user["role"]] < ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=403,
                detail=f"Requires role >= {min_role}",
            )
        return user

    return dep


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn):
    seed_admin()
    users = _users()
    if users.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=400, detail="Email already registered")
    users.insert_one(
        {
            "email": body.email.lower(),
            "password_hash": hash_password(body.password),
            "role": "viewer",
            "disabled": False,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return {
        "access_token": create_access_token(sub=body.email.lower(), role="viewer"),
        "role": "viewer",
    }


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn):
    seed_admin()
    user = _users().find_one(
        {"email": body.email.lower(), "disabled": {"$ne": True}}
    )
    if not user:
        verify_password(body.password, DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "access_token": create_access_token(sub=user["email"], role=user["role"]),
        "role": user["role"],
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {
        "ok": True,
        "authenticated": bool(user),
        "enforced": _enforced(),
        "user": user or {"role": "anonymous"},
    }


class SessionIn(BaseModel):
    session_id: str


@router.post("/session", response_model=TokenOut)
async def google_session(body: SessionIn):
    """Exchange an OAuth session_id for a persistent session token."""
    import httpx

    seed_admin()
    session_api = resolve_session_api()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                session_api,
                headers={"X-Session-ID": body.session_id},
            )
    except Exception:  # noqa: BLE001
        log.exception("auth provider session exchange failed")
        raise HTTPException(status_code=502, detail="Auth provider unreachable") from None
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    data = response.json()
    email = (data.get("email") or "").lower()
    session_token = data.get("session_token")
    if not email or not session_token:
        raise HTTPException(status_code=401, detail="Malformed session response")

    users = _users()
    existing = users.find_one({"email": email})
    if existing:
        role = existing.get("role", "viewer")
        users.update_one(
            {"email": email},
            {
                "$set": {
                    "name": data.get("name"),
                    "picture": data.get("picture"),
                    "last_login": datetime.now(timezone.utc),
                }
            },
        )
    else:
        role = "viewer"
        users.insert_one(
            {
                "email": email,
                "role": role,
                "auth": "google",
                "disabled": False,
                "name": data.get("name"),
                "picture": data.get("picture"),
                "created_at": datetime.now(timezone.utc),
            }
        )

    now = datetime.now(timezone.utc)
    _sessions().update_one(
        {"session_token": session_token},
        {
            "$set": {
                "session_token": session_token,
                "email": email,
                "expires_at": now + timedelta(days=7),
                "created_at": now,
            }
        },
        upsert=True,
    )
    return {"access_token": session_token, "role": role}


@router.post("/logout")
def logout(token: Annotated[str | None, Depends(oauth2_scheme)]):
    """Revoke a Google session token (JWTs are stateless — client just drops)."""
    if token:
        try:
            _sessions().delete_one({"session_token": token})
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True}


class SetRoleIn(BaseModel):
    email: EmailStr
    role: Role


@router.post("/set-role")
def set_role(body: SetRoleIn, _admin=Depends(require_role("admin"))):
    """Admin-only: promote/demote a user (e.g. a Google-provisioned viewer)."""
    res = _users().update_one(
        {"email": body.email.lower()},
        {"$set": {"role": body.role}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "email": body.email.lower(), "role": body.role}


@router.get("/users")
def list_users(_admin=Depends(require_role("admin"))):
    """Admin-only: list users + roles for the role-management panel."""
    rows = list(_users().find({}, {"_id": 0, "password_hash": 0}).limit(200))
    return {"ok": True, "users": rows}
