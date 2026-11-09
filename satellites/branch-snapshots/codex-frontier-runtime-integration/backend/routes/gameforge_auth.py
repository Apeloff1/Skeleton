"""
routes/gameforge_auth.py — JWT auth + RBAC (viewer < editor < admin).

Guards sensitive Studio/Vault operations. Enforcement is gated by
GAMEFORGE_AUTH_ENFORCE (default "0" = open dev mode; "1" = enforce) so existing
flows keep working until you switch it on for production.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])

Role = Literal["viewer", "editor", "admin"]
ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 240

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

SEED_ADMIN_EMAIL = "admin@gameforge.io"
SEED_ADMIN_PASSWORD = "GameForge#Admin2026"


def _secret() -> str:
    return os.getenv("GAMEFORGE_JWT_SECRET", "dev-insecure-secret-change-me")


def _enforced() -> bool:
    return os.getenv("GAMEFORGE_AUTH_ENFORCE", "0") == "1"


def _users():
    from core.databases import get_sync_db
    return get_sync_db()["gameforge_users"]


def _sessions():
    from core.databases import get_sync_db
    return get_sync_db()["user_sessions"]


EMERGENT_SESSION_API = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


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
    payload = {"sub": sub, "role": role, "iat": int(now.timestamp()),
               "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp())}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def seed_admin():
    """Idempotently create the default admin + ensure indexes."""
    try:
        users = _users()
        users.create_index("email", unique=True)
        sessions = _sessions()
        sessions.create_index("session_token", unique=True)
        # TTL index — Mongo auto-purges expired Google sessions.
        sessions.create_index("expires_at", expireAfterSeconds=0)
        if not users.find_one({"email": SEED_ADMIN_EMAIL}):
            users.insert_one({"email": SEED_ADMIN_EMAIL, "password_hash": hash_password(SEED_ADMIN_PASSWORD),
                              "role": "admin", "disabled": False, "auth": "password",
                              "created_at": datetime.now(timezone.utc)})
    except Exception:  # noqa: BLE001
        pass


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


def get_current_user(token: Annotated[Optional[str], Depends(oauth2_scheme)]):
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
            return _users().find_one({"email": sess.get("email"), "disabled": {"$ne": True}},
                                     {"_id": 0, "password_hash": 0})
    except Exception:  # noqa: BLE001
        pass
    # 2) JWT (email/password login).
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
        email, role = payload.get("sub"), payload.get("role")
        if not email or role not in ROLE_RANK:
            return None
    except JWTError:
        return None
    return _users().find_one({"email": email, "disabled": {"$ne": True}}, {"_id": 0, "password_hash": 0})


def require_role(min_role: Role):
    """Dependency: enforce a minimum role when GAMEFORGE_AUTH_ENFORCE=1.
    In open dev mode (default) it records identity but never blocks."""
    def dep(user=Depends(get_current_user)):
        if not _enforced():
            return user or {"email": "anonymous", "role": "admin", "dev_mode": True}
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required",
                                headers={"WWW-Authenticate": "Bearer"})
        if ROLE_RANK[user["role"]] < ROLE_RANK[min_role]:
            raise HTTPException(status_code=403, detail=f"Requires role >= {min_role}")
        return user
    return dep


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn):
    seed_admin()
    users = _users()
    if users.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=400, detail="Email already registered")
    users.insert_one({"email": body.email.lower(), "password_hash": hash_password(body.password),
                      "role": "viewer", "disabled": False, "created_at": datetime.now(timezone.utc)})
    return {"access_token": create_access_token(sub=body.email.lower(), role="viewer"), "role": "viewer"}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn):
    seed_admin()
    user = _users().find_one({"email": body.email.lower(), "disabled": {"$ne": True}})
    if not user:
        verify_password(body.password, DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(sub=user["email"], role=user["role"]), "role": user["role"]}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"ok": True, "authenticated": bool(user), "enforced": _enforced(),
            "user": user or {"role": "anonymous"}}


class SessionIn(BaseModel):
    session_id: str


@router.post("/session", response_model=TokenOut)
async def google_session(body: SessionIn):
    """Exchange an Emergent OAuth session_id for a persistent session token.

    The frontend passes the one-time `session_id` from the redirect. We verify
    it with Emergent's session-data API (single consumption here — the frontend
    never calls it directly), upsert the user by email, persist the returned
    `session_token` (7-day TTL) and hand it back as the bearer token.
    """
    import httpx
    seed_admin()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(EMERGENT_SESSION_API, headers={"X-Session-ID": body.session_id})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Auth provider unreachable: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    data = r.json()
    email = (data.get("email") or "").lower()
    session_token = data.get("session_token")
    if not email or not session_token:
        raise HTTPException(status_code=401, detail="Malformed session response")

    users = _users()
    existing = users.find_one({"email": email})
    if existing:
        role = existing.get("role", "viewer")
        users.update_one({"email": email}, {"$set": {
            "name": data.get("name"), "picture": data.get("picture"),
            "last_login": datetime.now(timezone.utc)}})
    else:
        role = "viewer"
        users.insert_one({"email": email, "role": role, "auth": "google", "disabled": False,
                          "name": data.get("name"), "picture": data.get("picture"),
                          "created_at": datetime.now(timezone.utc)})

    now = datetime.now(timezone.utc)
    _sessions().update_one(
        {"session_token": session_token},
        {"$set": {"session_token": session_token, "email": email,
                  "expires_at": now + timedelta(days=7), "created_at": now}},
        upsert=True)
    return {"access_token": session_token, "role": role}


@router.post("/logout")
def logout(token: Annotated[Optional[str], Depends(oauth2_scheme)]):
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
def set_role(body: SetRoleIn, admin=Depends(require_role("admin"))):
    """Admin-only: promote/demote a user (e.g. a Google-provisioned viewer)."""
    res = _users().update_one({"email": body.email.lower()}, {"$set": {"role": body.role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "email": body.email.lower(), "role": body.role}


@router.get("/users")
def list_users(admin=Depends(require_role("admin"))):
    """Admin-only: list users + roles for the role-management panel."""
    rows = list(_users().find({}, {"_id": 0, "password_hash": 0}).limit(200))
    return {"ok": True, "users": rows}
