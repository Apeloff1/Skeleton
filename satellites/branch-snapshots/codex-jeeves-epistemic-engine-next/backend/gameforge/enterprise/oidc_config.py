from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass
class OIDCSettings:
    issuer: str | None
    audience: str | None
    jwks_url: str | None
    dev_open: bool
    api_token_configured: bool

    @property
    def enabled(self) -> bool:
        return bool(self.issuer and self.jwks_url)

    @property
    def production_ready(self) -> bool:
        return self.enabled and not self.dev_open

    def as_dict(self) -> dict:
        return {
            "issuer": self.issuer,
            "audience": self.audience,
            "jwks_url": self.jwks_url,
            "enabled": self.enabled,
            "dev_open": self.dev_open,
            "api_token_configured": self.api_token_configured,
            "production_ready": self.production_ready,
        }


def load_oidc_settings() -> OIDCSettings:
    return OIDCSettings(
        issuer=os.getenv("GAMEFORGE_OIDC_ISSUER"),
        audience=os.getenv("GAMEFORGE_OIDC_AUDIENCE"),
        jwks_url=os.getenv("GAMEFORGE_OIDC_JWKS_URL"),
        dev_open=os.getenv("GAMEFORGE_DEV_OPEN", "1") == "1",
        api_token_configured=bool(os.getenv("GAMEFORGE_API_TOKEN")),
    )
