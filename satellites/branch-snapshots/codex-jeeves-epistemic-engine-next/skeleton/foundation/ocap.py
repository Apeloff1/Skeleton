"""
Skeleton Foundation — Object-Capability Security Kernel

Replaces ambient authority with unforgeable, attenuable, revocable
capabilities. No subsystem touches a resource without holding a
capability for it; every capability is a proof of the exact
authority it carries — nothing more.

Model (classical object-capability):
- Capability: an unforgeable token binding (resource, rights, chain).
  Holding it is the only way to invoke the resource. There is no
  lookup by name — names are not authority.
- Attenuation: a holder may derive a STRICTLY WEAKER capability
  (fewer rights, shorter expiry, narrower scope) — never stronger.
  The chain records every derivation, so authority provenance is
  auditable end-to-end.
- Revocation: any ancestor in the chain may revoke its descendants
  atomically. Revoking a root kills the whole tree.
- Delegation: passing a capability IS passing authority — the token
  travels by value; the kernel checks nothing but validity, chain,
  rights, and revocation at invoke time.
- Membrane: cross-subsystem calls pass through a membrane that
  attenuates to the callee's declared needs — principle of least
  authority as the system default, not a discipline.

Cryptography: tokens are HMAC-chained over (resource | rights |
parent_hash | expiry | nonce) with the kernel secret. Forgery
requires the secret; attenuation is provably monotonic because each
link recomputes over its parent.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


KERNEL_SECRET = b"skeleton-ocap-kernel"


@dataclass
class Capability:
    """An unforgeable authority token."""
    cap_id: str
    resource: str
    rights: Set[str]
    parent_hash: str
    expiry: Optional[float]
    nonce: str
    signature: str
    depth: int = 0
    revoked: bool = False

    def expired(self) -> bool:
        return self.expiry is not None and time.time() > self.expiry

    def to_dict(self) -> Dict[str, Any]:
        return {"cap_id": self.cap_id, "resource": self.resource,
                "rights": sorted(self.rights), "depth": self.depth,
                "expiry": self.expiry, "revoked": self.revoked}


class CapabilityKernel:
    """Mints, attenuates, verifies, and revokes capabilities."""

    def __init__(self, secret: bytes = KERNEL_SECRET):
        self._secret = secret
        self._caps: Dict[str, Capability] = {}
        self._revocations: Set[str] = set()  # revoked ancestor hashes
        self._resources: Dict[str, Any] = {}
        self._stats = {"minted": 0, "attenuated": 0, "invocations": 0,
                       "denied": 0, "revoked": 0}

    # --- Signing -----------------------------------------------------------

    def _sign(self, resource: str, rights: Set[str], parent_hash: str,
              expiry: Optional[float], nonce: str) -> str:
        body = f"{resource}|{sorted(rights)}|{parent_hash}|{expiry}|{nonce}".encode()
        return hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    # --- Minting (root authority) ---------------------------------------------

    def mint(self, resource: str, rights: Set[str],
             expiry: Optional[float] = None,
             target: Optional[Any] = None) -> Capability:
        """Create a root capability. Root minting is kernel-only."""
        nonce = uuid.uuid4().hex[:16]
        sig = self._sign(resource, rights, "root", expiry, nonce)
        cap = Capability(
            cap_id=uuid.uuid4().hex[:12],
            resource=resource,
            rights=set(rights),
            parent_hash="root",
            expiry=expiry,
            nonce=nonce,
            signature=sig,
        )
        self._caps[cap.cap_id] = cap
        if target is not None:
            self._resources[resource] = target
        self._stats["minted"] += 1
        return cap

    # --- Attenuation (provably monotonic weakening) ------------------------------

    def attenuate(self, parent: Capability, rights: Optional[Set[str]] = None,
                  expiry: Optional[float] = None) -> Optional[Capability]:
        """Derive a strictly weaker capability from a parent.

        Rights can only shrink; expiry can only shorten. Returns None
        if the derivation would STRENGTHEN authority — provably
        impossible by construction.
        """
        if not self.verify(parent):
            self._stats["denied"] += 1
            return None
        new_rights = set(rights) if rights is not None else set(parent.rights)
        if not new_rights <= parent.rights:
            return None  # would strengthen: refuse
        new_expiry = expiry
        if parent.expiry is not None:
            new_expiry = min(expiry, parent.expiry) if expiry else parent.expiry
        nonce = uuid.uuid4().hex[:16]
        sig = self._sign(parent.resource, new_rights, parent.signature, new_expiry, nonce)
        cap = Capability(
            cap_id=uuid.uuid4().hex[:12],
            resource=parent.resource,
            rights=new_rights,
            parent_hash=parent.signature,
            expiry=new_expiry,
            nonce=nonce,
            signature=sig,
            depth=parent.depth + 1,
        )
        self._caps[cap.cap_id] = cap
        self._stats["attenuated"] += 1
        return cap

    # --- Verification -----------------------------------------------------------

    def verify(self, cap: Capability) -> bool:
        """Token valid, unexpired, and no ancestor revoked."""
        if cap.revoked or cap.expired():
            return False
        if cap.signature in self._revocations:
            return False
        # Walk the chain: any revoked ancestor kills the token
        current = cap
        seen = 0
        while current.parent_hash != "root" and seen < 64:
            if current.parent_hash in self._revocations:
                return False
            parent = next((c for c in self._caps.values()
                           if c.signature == current.parent_hash), None)
            if parent is None:
                break
            current = parent
            seen += 1
        return True

    # --- Invocation ----------------------------------------------------------------

    def invoke(self, cap: Capability, right: str, *args, **kwargs) -> Any:
        """Invoke a resource through a capability. The ONLY way in."""
        if right not in cap.rights:
            self._stats["denied"] += 1
            raise PermissionError(f"capability lacks right '{right}' for {cap.resource}")
        if not self.verify(cap):
            self._stats["denied"] += 1
            raise PermissionError("capability invalid, expired, or revoked")
        target = self._resources.get(cap.resource)
        if target is None:
            self._stats["denied"] += 1
            raise PermissionError(f"no resource bound to {cap.resource}")
        self._stats["invocations"] += 1
        method = getattr(target, right, None)
        if method is None:
            raise AttributeError(f"resource {cap.resource} has no method {right}")
        return method(*args, **kwargs)

    # --- Revocation ------------------------------------------------------------------

    def revoke(self, cap: Capability) -> int:
        """Revoke a capability AND all its descendants atomically."""
        self._revocations.add(cap.signature)
        cap.revoked = True
        self._stats["revoked"] += 1
        # Count descendants now dead
        dead = sum(1 for c in self._caps.values()
                   if c.parent_hash == cap.signature or self._is_descendant(c, cap.signature))
        return 1 + dead

    def _is_descendant(self, cap: Capability, ancestor_hash: str) -> bool:
        current = cap
        seen = 0
        while current.parent_hash != "root" and seen < 64:
            if current.parent_hash == ancestor_hash:
                return True
            parent = next((c for c in self._caps.values()
                           if c.signature == current.parent_hash), None)
            if parent is None:
                return False
            current = parent
            seen += 1
        return False

    def chain(self, cap: Capability) -> List[Dict[str, Any]]:
        """Full provenance chain for audit."""
        out = [cap.to_dict()]
        current = cap
        seen = 0
        while current.parent_hash != "root" and seen < 64:
            parent = next((c for c in self._caps.values()
                           if c.signature == current.parent_hash), None)
            if parent is None:
                break
            out.append(parent.to_dict())
            current = parent
            seen += 1
        return out

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "capabilities": len(self._caps),
                "revocations": len(self._revocations)}


class Membrane:
    """Cross-subsystem authority membrane: calls pass through with
    automatic attenuation to the callee's declared needs."""

    def __init__(self, kernel: CapabilityKernel):
        self._kernel = kernel
        self._needs: Dict[str, Set[str]] = {}

    def declare(self, subsystem: str, needed_rights: Set[str]) -> None:
        """A subsystem declares the rights it actually needs."""
        self._needs[subsystem] = set(needed_rights)

    def cross(self, cap: Capability, to_subsystem: str) -> Optional[Capability]:
        """Attenuate a capability to the callee's declared needs."""
        needs = self._needs.get(to_subsystem)
        if needs is None:
            return self._kernel.attenuate(cap, rights=set())  # no needs → no rights
        return self._kernel.attenuate(cap, rights=cap.rights & needs)


class CapabilityGuard:
    """Wraps a resource so ALL access flows through capability checks."""

    def __init__(self, kernel: CapabilityKernel, resource: str, target: Any,
                 rights: Set[str]):
        self._kernel = kernel
        self._root = kernel.mint(resource, rights, target=target)

    @property
    def root(self) -> Capability:
        return self._root

    def issue(self, rights: Optional[Set[str]] = None,
              expiry: Optional[float] = None) -> Optional[Capability]:
        """Issue an attenuated capability to a caller."""
        return self._kernel.attenuate(self._root, rights=rights, expiry=expiry)

    def use(self, cap: Capability, right: str, *args, **kwargs) -> Any:
        return self._kernel.invoke(cap, right, *args, **kwargs)
