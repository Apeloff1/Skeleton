from __future__ import annotations
import hmac
import os
from dataclasses import dataclass, field
from typing import List, Optional

from fastapi import Header, HTTPException


@dataclass
class Principal:
    user_id: str
    email: Optional[str] = None
    tenant_ids: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    auth_method: str = "token"


class AuthService:
    def __init__(self):
        # Never let an accidentally inherited development default enable
        # anonymous administrator access outside explicit local development.
        environment = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development"))
        self.production = environment.strip().lower() in {
            "production", "prod", "staging", "stage", "preview",
        }
        self.dev_open = (
            not self.production
            and os.getenv("GAMEFORGE_DEV_OPEN", "0") == "1"
        )
        configured_token = os.getenv("GAMEFORGE_API_TOKEN", "")
        # The historical "dev" fallback is not an authentication secret.
        self.api_token = (
            configured_token
            if configured_token and (
                not self.production or configured_token != "dev"
            )
            else None
        )
        self.oidc = None  # set by oidc module if configured

    async def resolve(
        self,
        authorization: Optional[str] = None,
        x_user_id: Optional[str] = None,
    ) -> Principal:
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            if (
                self.api_token is not None
                and len(token) <= 2048
                and hmac.compare_digest(token, self.api_token)
            ):
                return Principal(
                    # The x-user-id header is controlled by the requester.
                    # Production service tokens are their own identities,
                    # never arbitrary principals supplied in HTTP headers.
                    user_id="api-token-user" if self.production else (x_user_id or "api-token-user"),
                    roles=["admin", "operator"],
                    auth_method="api_token",
                )
            if self.oidc is not None:
                return await self._validate_oidc(token)
            if self.dev_open:
                return Principal(
                    user_id=x_user_id or "dev-user",
                    roles=["owner", "admin", "operator"],
                    auth_method="dev_open",
                )
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        if self.dev_open:
            return Principal(
                user_id=x_user_id or "dev-user",
                roles=["owner", "admin", "operator"],
                auth_method="dev_open",
            )
        raise HTTPException(status_code=401, detail="Authorization required")

    async def _validate_oidc(self, token: str) -> Principal:
        claims = await self.oidc.validate(token)
        user_id = (
            claims.get("sub")
            or claims.get("oid")
            or claims.get("email")
            or claims.get("preferred_username")
        )
        tenants = (
            claims.get("tenants")
            or claims.get("tenant_ids")
            or claims.get("groups")
            or claims.get("https://gameforge.local/tenants")
            or []
        )
        if isinstance(tenants, str):
            tenants = [tenants]
        roles = (
            claims.get("roles")
            or (claims.get("realm_access") or {}).get("roles")
            or claims.get("https://gameforge.local/roles")
            or ["operator"]
        )
        if isinstance(roles, str):
            roles = [roles]
        if not isinstance(user_id, str) or not user_id.strip():
            raise HTTPException(status_code=401, detail="Invalid identity token")
        return Principal(
            user_id=user_id,
            email=claims.get("email"),
            tenant_ids=list(tenants),
            roles=list(roles),
            auth_method="oidc",
        )


AUTH = AuthService()


async def get_principal(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Principal:
    return await AUTH.resolve(authorization, x_user_id)
