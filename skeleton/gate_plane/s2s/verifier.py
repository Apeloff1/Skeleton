"""Registry-bound, replay-windowed token verification.

:class:`RegistryVerifier` extends Pack F's :class:`TokenVerifier` without
changing it. After the base checks (header, kid, MAC, audience, issuer
allow-list, lifetime, exp/nbf with leeway, jti revocation) it adds:

1. **Identity** - the issuer must be registered and enabled in the
   :class:`ServiceRegistry` (unknown callers are rejected when the registry
   is strict) and allowed to address this audience.
2. **Scope ceiling** - token scopes are clamped to the identity's ceiling;
   stripped scopes are reported on :attr:`RegistryVerifiedToken.stripped`.
3. **Replay window** - ``iat`` must be no older than ``max_age_s`` and no
   further in the future than ``clock_skew_s``; the ``jti`` is recorded in
   the injected :class:`~skeleton.gate_plane.s2s.nonce.NonceStore` under
   scope ``"s2s:<service>"`` with a TTL covering the rest of the token's
   life plus skew. A second sighting inside that TTL is ``REPLAYED``.

Identity checks run before the nonce is recorded, so rejected callers can
never burn nonces for legitimate ones.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, FrozenSet, Iterable, Optional

from skeleton.gate_plane.s2s.clock import Clock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.nonce import NonceStore, is_nonce_store, s2s_scope
from skeleton.gate_plane.s2s.registry import ServiceIdentity, ServiceRegistry
from skeleton.gate_plane.s2s.tokens import (
    DEFAULT_LEEWAY_S,
    MAX_TTL_S,
    TokenError,
    TokenErrorCode,
    TokenVerifier,
    VerifiedToken,
)

DEFAULT_MAX_AGE_S = 600.0
DEFAULT_CLOCK_SKEW_S = 30.0
MIN_NONCE_TTL_S = 1.0


@dataclass(frozen=True)
class RegistryVerifiedToken(VerifiedToken):
    """A :class:`VerifiedToken` whose scopes were clamped to the registry ceiling."""

    identity: Optional[ServiceIdentity] = None
    stripped: FrozenSet[str] = frozenset()
    nonce_scope: Optional[str] = None


class RegistryVerifier(TokenVerifier):
    def __init__(
        self,
        audience: str,
        keyring: KeyRing,
        *,
        registry: ServiceRegistry,
        nonce_store: Optional[Any] = None,
        clock: Optional[Clock] = None,
        leeway_s: float = DEFAULT_LEEWAY_S,
        max_lifetime_s: float = MAX_TTL_S,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        clock_skew_s: float = DEFAULT_CLOCK_SKEW_S,
        trusted_issuers: Optional[Iterable[str]] = None,
        revoked_jtis: Optional[Any] = None,
        accept_pending: bool = False,
        require_nonce_store: bool = True,
    ) -> None:
        super().__init__(
            audience,
            keyring,
            clock=clock,
            leeway_s=leeway_s,
            max_lifetime_s=max_lifetime_s,
            trusted_issuers=trusted_issuers,
            replay_cache=None,  # replay handled by the shared NonceStore below
            revoked_jtis=revoked_jtis,
            accept_pending=accept_pending,
        )
        if not isinstance(registry, ServiceRegistry):
            raise TypeError("registry must be a ServiceRegistry")
        if nonce_store is None and require_nonce_store:
            raise ValueError("nonce_store required (pass require_nonce_store=False to disable replay protection)")
        if nonce_store is not None and not is_nonce_store(nonce_store):
            raise TypeError("nonce_store must implement check_and_record(scope, nonce, ts, ttl_s)")
        if max_age_s <= 0 or max_age_s > MAX_TTL_S:
            raise ValueError("max_age_s must be in (0, MAX_TTL_S]")
        if clock_skew_s < 0 or clock_skew_s > 300:
            raise ValueError("clock_skew_s must be within [0, 300]")
        self.registry = registry
        self.nonce_store: Optional[NonceStore] = nonce_store
        self.max_age_s = float(max_age_s)
        self.clock_skew_s = float(clock_skew_s)

    def verify(self, token: str) -> RegistryVerifiedToken:
        base = super().verify(token)
        claims = base.claims
        ident = self.registry.get(claims.iss)
        if ident is None:
            if self.registry.strict:
                raise TokenError(TokenErrorCode.BAD_ISSUER, f"unregistered:{claims.iss}")
        else:
            if not ident.enabled:
                raise TokenError(TokenErrorCode.BAD_ISSUER, f"disabled:{claims.iss}")
            if not ident.may_address(claims.aud):
                raise TokenError(TokenErrorCode.BAD_AUDIENCE, f"{claims.iss}->{claims.aud}")

        now = self.clock.now()
        if now - claims.iat > self.max_age_s + self.clock_skew_s:
            raise TokenError(TokenErrorCode.EXPIRED, f"iat older than replay window ({self.max_age_s}s)")
        if claims.iat > now + self.clock_skew_s:
            raise TokenError(TokenErrorCode.NOT_YET_VALID, "iat in the future beyond clock skew")

        stripped: FrozenSet[str] = frozenset()
        if ident is not None:
            kept = ident.clamp_scopes(claims.scopes)
            stripped = frozenset(claims.scopes) - kept
            if stripped:
                claims = replace(claims, scopes=kept)

        nonce_scope: Optional[str] = None
        if self.nonce_store is not None:
            nonce_scope = s2s_scope(claims.iss)
            # ts is the token's issue time; retain until exp + leeway + skew.
            ttl = max(MIN_NONCE_TTL_S, (claims.exp + self.leeway_s + self.clock_skew_s) - claims.iat)
            # NonceStoreFull propagates: the gate answers 503 (fail closed).
            if not self.nonce_store.check_and_record(nonce_scope, claims.jti, claims.iat, ttl):
                raise TokenError(TokenErrorCode.REPLAYED, claims.jti)

        return RegistryVerifiedToken(
            kid=base.kid,
            claims=claims,
            key_state=base.key_state,
            identity=ident,
            stripped=stripped,
            nonce_scope=nonce_scope,
        )


__all__ = [
    "DEFAULT_CLOCK_SKEW_S",
    "DEFAULT_MAX_AGE_S",
    "MIN_NONCE_TTL_S",
    "RegistryVerifiedToken",
    "RegistryVerifier",
]
